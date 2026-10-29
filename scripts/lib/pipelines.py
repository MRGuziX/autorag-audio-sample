"""Validate and submit managed versions or local KFP packages with durable receipts."""

import json
from datetime import UTC, datetime
from pathlib import Path

from lib.sample import pipeline_spec_body, read_json, require, sha256, validate_pipeline_params, write_json


def read_package(path: Path, name: str) -> tuple[dict, bytes]:
    """Read a compiled KFP YAML, retaining the separate Kubernetes platform document."""
    import yaml
    from google.protobuf import json_format
    from kfp.pipeline_spec import pipeline_spec_pb2

    require(path.is_file(), f"Pipeline package does not exist: {path}")
    require(path.suffix.lower() in {".yaml", ".yml"}, "Pipeline path must point to compiled .yaml or .yml")
    content = path.read_bytes()
    try:
        documents = list(yaml.safe_load_all(content))
    except yaml.YAMLError:
        raise ValueError(f"Invalid pipeline YAML: {path}") from None
    require(
        1 <= len(documents) <= 2 and all(isinstance(doc, dict) for doc in documents),
        "Expected a KFP v2 pipeline document and optional platform document",
    )
    body = documents[0]
    require(body.get("pipelineInfo", {}).get("name") == name, f"Local package must define {name}")
    require(bool(body.get("deploymentSpec")), "Local package has no executable deploymentSpec")
    platform = documents[1] if len(documents) == 2 else None
    if platform is not None:
        require(bool(platform.get("platforms")), "Second YAML document must contain platform settings")
    # Use the same protobuf schemas as the SDK before making any cluster requests.
    try:
        json_format.ParseDict(body, pipeline_spec_pb2.PipelineSpec())
        if platform is not None:
            json_format.ParseDict(platform, pipeline_spec_pb2.PlatformSpec())
    except (json_format.ParseError, TypeError, ValueError):
        raise ValueError(f"Package is not a valid KFP v2 pipeline/platform spec: {path}") from None
    spec = {"pipeline_spec": body, "platform_spec": platform} if platform is not None else body
    return spec, content


def remote_call(operation: str, function, **kwargs):
    try:
        return function(**kwargs)
    except Exception as exc:
        # API exception bodies/headers may contain private endpoints. Do not print them.
        status = getattr(exc, "status", "unknown")
        raise RuntimeError(
            f"KFP {operation} failed ({type(exc).__name__}, HTTP {status}); inspect locally"
        ) from None


def get_spec(client, pipeline_id: str, version_id: str) -> dict:
    version = remote_call(
        "version lookup", client.get_pipeline_version, pipeline_id=pipeline_id, pipeline_version_id=version_id
    )
    spec = version.pipeline_spec
    require(isinstance(spec, dict), "Server did not return a KFP v2 PipelineSpec object")
    return spec


def discover_endpoint(routes: list[dict], dspa: dict) -> str:
    name, uid = dspa["metadata"]["name"], dspa["metadata"]["uid"]
    candidates = []
    for route in routes:
        metadata, spec = route["metadata"], route.get("spec", {})
        owned = any(owner.get("uid") == uid for owner in metadata.get("ownerReferences", []))
        pipeline_route = spec.get("to", {}).get("name") == f"ds-pipeline-{name}"
        pipeline_route = pipeline_route or metadata["name"] == f"ds-pipeline-{name}"
        if owned and pipeline_route and spec.get("host"):
            require(bool(spec.get("tls")), "Pipeline route must enable TLS")
            require(
                spec.get("path", "/") in (None, "", "/"), "Set RHOAI_KFP_URL for a custom pipeline route path"
            )
            candidates.append("https://" + spec["host"])
    require(len(candidates) == 1, "Cannot identify one DSPA pipeline API route; set RHOAI_KFP_URL explicitly")
    return candidates[0]


def all_items(client, method_name: str, field: str, **kwargs) -> list:
    items, cursor, seen = [], "", set()
    while True:
        page = remote_call(
            "discovery", getattr(client, method_name), page_size=100, page_token=cursor, **kwargs
        )
        items.extend(getattr(page, field, None) or [])
        cursor = getattr(page, "next_page_token", None)
        if not cursor:
            return items
        require(cursor not in seen, "Pipeline API returned a repeated pagination cursor")
        seen.add(cursor)


def pin_pipeline(client, namespace: str, name: str, pipeline_id=None, version_id=None) -> tuple[dict, dict]:
    if not pipeline_id:
        matches = [
            p
            for p in all_items(client, "list_pipelines", "pipelines", namespace=namespace)
            if p.display_name == name
        ]
        require(
            len(matches) == 1,
            f"Specify the pipeline ID for {name}; exact-name discovery found {len(matches)}",
        )
        pipeline_id = matches[0].pipeline_id
    if not version_id:
        versions = all_items(
            client,
            "list_pipeline_versions",
            "pipeline_versions",
            pipeline_id=pipeline_id,
            sort_by="created_at desc",
        )
        require(bool(versions), f"No installed versions for {name}")
        version_id = versions[0].pipeline_version_id
    spec = get_spec(client, pipeline_id, version_id)
    body = pipeline_spec_body(spec)
    require(
        body.get("pipelineInfo", {}).get("name") == name,
        f"Selected version is not {name}; actual name: {body.get('pipelineInfo', {}).get('name')!r}",
    )
    require(bool(body.get("deploymentSpec")), "Installed version has no executable deploymentSpec")
    return {"pipeline_id": pipeline_id, "version_id": version_id}, spec


def submit(
    client,
    *,
    kind: str,
    name: str,
    pinned: dict,
    experiment_id: str,
    run_name: str,
    directory: Path,
    timeout: int,
    namespace: str,
    endpoint: str,
    pattern_sha256: str | None = None,
    package_path: Path | None = None,
) -> str:
    """Check the selected source, reserve a receipt, submit once and wait."""
    receipt_path = directory / "receipt.json"
    require(not receipt_path.exists(), "Receipt already exists; inspect that run before submitting another")
    params_path, spec_path = directory / "params.json", directory / "spec.json"
    params, exported = read_json(params_path), read_json(spec_path)
    if package_path is not None:
        require(sha256(package_path) == pinned["package_sha256"], "Local package snapshot changed; review it")
        installed, _ = read_package(package_path, name)
        source = {"pipeline_package_path": str(package_path)}
    else:
        installed = get_spec(client, pinned["pipeline_id"], pinned["version_id"])
        source = {"pipeline_id": pinned["pipeline_id"], "version_id": pinned["version_id"]}
    require(
        pipeline_spec_body(installed).get("pipelineInfo", {}).get("name") == name,
        f"Wrong pipeline; expected {name}",
    )
    require(installed == exported, "Pipeline spec differs from inspected spec; start a new run after review")
    validate_pipeline_params(params, installed, name)
    receipt = {
        "schema_version": 2,
        "namespace": namespace,
        "endpoint": endpoint,
        "kind": kind,
        "pipeline_name": name,
        "pipeline_id": pinned["pipeline_id"],
        "pipeline_version_id": pinned["version_id"],
        "run_name": run_name,
        "requested_at": datetime.now(UTC).isoformat(),
        "params_sha256": sha256(params_path),
        "spec_sha256": sha256(spec_path),
        "state": "SUBMITTING",
        "run_id": None,
        "pipeline_source": "local" if package_path is not None else "managed",
    }
    if package_path is not None:
        receipt.update(package_path=pinned["package_path"], package_sha256=pinned["package_sha256"])
    if pattern_sha256 is not None:
        receipt.update(pattern_sha256=pattern_sha256, collection_name=params["collection_name"])
    # Reserve before the remote mutation; never retry an uncertain submission automatically.
    with receipt_path.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2)
    try:
        result = remote_call(
            "submission (outcome may be uncertain; check run name before retrying)",
            client.run_pipeline,
            experiment_id=experiment_id,
            job_name=run_name,
            params=params,
            **source,
            enable_caching=False,
        )
    except RuntimeError:
        receipt["state"] = "SUBMISSION_UNCERTAIN"
        write_json(receipt_path, receipt)
        raise
    receipt.update(run_id=result.run_id, state=getattr(result, "state", None) or "SUBMITTED")
    write_json(receipt_path, receipt)
    print(f"Submitted run {result.run_id}; receipt: {receipt_path}")
    result = remote_call(
        "wait (run may still be active; use receipt to check)",
        client.wait_for_run_completion,
        run_id=receipt["run_id"],
        timeout=timeout,
        sleep_duration=10,
    )
    receipt.update(state=result.state, checked_at=datetime.now(UTC).isoformat())
    write_json(receipt_path, receipt)
    require(result.state == "SUCCEEDED", f"Run finished with state {result.state}; see receipt")
    return receipt["run_id"]
