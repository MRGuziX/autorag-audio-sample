"""Run audio optimization or indexing on OpenShift from a single .env file."""

import argparse
import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from dotenv import dotenv_values
from lib.artifacts import download_run_artifacts
from lib.indexing import prepare
from lib.openshift import context_info, oc
from lib.pipelines import all_items, discover_endpoint, pin_pipeline, read_package, remote_call, submit
from lib.sample import (
    INDEXING_PIPELINE,
    OPTIMIZATION_PIPELINE,
    ROOT,
    cli,
    non_placeholder,
    optimization_params,
    read_json,
    require,
    validate_config,
    validate_pipeline_params,
    write_json,
)
from lib.storage import s3_client, stage, upload_plan


def read_env(path: Path) -> dict[str, str]:
    require(path.is_file(), f"Missing {path}; copy .env.example to .env and fill it in")
    # Treat dotenv as data, never execute shell commands. Explicit shell values take precedence.
    values = {
        key: value for key, value in dotenv_values(path, interpolate=False).items() if value is not None
    }
    return {**values, **os.environ}


def flag(env: dict, name: str, default: bool = False) -> bool:
    value = env.get(name, str(default)).strip().lower()
    require(value in {"true", "false"}, f"{name} must be true or false")
    return value == "true"


def model_list(env: dict, name: str) -> list[str]:
    raw = env.get(name, "").strip()
    non_placeholder(raw, name)
    if raw.startswith("["):
        try:
            values = json.loads(raw)
        except json.JSONDecodeError:
            raise ValueError(f"{name} must be a JSON array or comma-separated model IDs") from None
    else:
        values = [value.strip() for value in raw.split(",")]
    require(isinstance(values, list) and bool(values), f"{name} must be a nonempty model list")
    for value in values:
        non_placeholder(value, name)
    return values


def configuration(env: dict) -> dict:
    """Match AutoX CI variable names; use the same dataset paths for execution and uploads."""
    mapping = {
        "bucket": "INPUT_DATA_BUCKET_NAME",
        "input_data_secret_name": "INPUT_DATA_SECRET_NAME",
        "maas_secret_name": "MAAS_SECRET_NAME",
        "db_secret_name": "VECTOR_DB_SECRET_NAME",
    }
    config = {}
    for field, name in mapping.items():
        value = env.get(name, "").strip()
        non_placeholder(value, name)
        config[field] = value
    try:
        patterns = int(env.get("AUTORAG_MAX_RAG_PATTERNS", "4"))
    except ValueError:
        raise ValueError("AUTORAG_MAX_RAG_PATTERNS must be an integer from 4 to 10") from None
    config.update(
        test_data_secret_name=env.get("TEST_DATA_SECRET_NAME", "").strip()
        or config["input_data_secret_name"],
        test_data_bucket_name=env.get("TEST_DATA_BUCKET_NAME", "").strip() or config["bucket"],
        preset=env.get("AUTORAG_PRESET", "speed").strip(),
        embedding_models=model_list(env, "AUTORAG_EMBEDDING_MODELS"),
        generation_models=model_list(env, "AUTORAG_GENERATION_MODELS"),
        optimization_metric=env.get("AUTORAG_OPTIMIZATION_METRIC", "answer_correctness").strip(),
        optimization_max_rag_patterns=patterns,
    )
    raw = env.get("AUTORAG_INPUT_DATA_KEYS", '["data/rag/audio/sample/documents"]').strip()
    try:
        config["input_data_keys"] = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError("AUTORAG_INPUT_DATA_KEYS must be a JSON array with one audio directory") from None
    config["test_data_key"] = env.get("AUTORAG_TEST_DATA_KEY", "data/rag/audio/sample/benchmark.json").strip()
    if flag(env, "AUTORAG_UPLOAD_TEST_DATASETS"):
        require(
            config["test_data_bucket_name"] == config["bucket"]
            and config["test_data_secret_name"] == config["input_data_secret_name"],
            "Uploads require the same input and benchmark bucket and Connection",
        )
    return validate_config(config)


def client_for(env: dict, namespace: str):
    """Use an explicit API token or the current oc login; persist neither."""
    import kfp

    endpoint = env.get("RHOAI_KFP_URL", "").strip()
    access_token = env.get("RHOAI_TOKEN", "").strip()
    require(
        not access_token or endpoint,
        "Set RHOAI_KFP_URL when using RHOAI_TOKEN; otherwise leave both blank and use oc login",
    )
    if not access_token:
        context = context_info(env.get("AUTORAG_OC_CONTEXT") or None)["context"]
        access_token = oc("whoami", "--show-token", context=context)
        require(bool(access_token), "No token in the oc session; run oc login")
        if not endpoint:
            resources = json.loads(
                oc(
                    "get",
                    "datasciencepipelinesapplications",
                    "-o",
                    "json",
                    context=context,
                    namespace=namespace,
                )
            )["items"]
            dspa_name = env.get("RHOAI_DSPA_NAME", "dspa")
            resources = [item for item in resources if item["metadata"]["name"] == dspa_name]
            require(len(resources) == 1, "No matching DSPA; set RHOAI_DSPA_NAME or RHOAI_KFP_URL")
            routes = json.loads(oc("get", "routes", "-o", "json", context=context, namespace=namespace))
            endpoint = discover_endpoint(routes["items"], resources[0])
    require(endpoint.startswith("https://"), "RHOAI_KFP_URL must use HTTPS")
    ca = env.get("KFP_CA_CERT", "").strip()
    if ca:
        require(Path(ca).is_file(), "KFP_CA_CERT must point to an existing CA file")
    require(
        flag(env, "KFP_VERIFY_SSL", True), "TLS verification is required; use KFP_CA_CERT for a private CA"
    )
    return kfp.Client(
        host=endpoint, existing_token=access_token, namespace=namespace, ssl_ca_cert=ca or None
    ), endpoint


def upload(env: dict, config: dict, plan: list[dict]) -> None:
    from botocore.exceptions import BotoCoreError, ClientError

    try:
        stage(s3_client(env), config["bucket"], config["input_data_keys"][0], plan)
    except (BotoCoreError, ClientError) as exc:
        code = (
            exc.response["Error"].get("Code", "unknown")
            if isinstance(exc, ClientError)
            else type(exc).__name__
        )
        raise RuntimeError(f"S3 staging failed ({code}); check storage access before retrying") from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--kind", choices=("optimization", "indexing"), default="optimization")
    parser.add_argument(
        "--download-run", help="Download artifacts for an existing local run name; no submission"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Check local inputs only; no cluster or S3 requests"
    )
    args = parser.parse_args(argv)
    env = read_env(args.env_file)
    download_enabled = flag(env, "DOWNLOAD_ARTIFACTS")
    if args.download_run:
        require(not args.dry_run, "Use --dry-run for experiment validation, or --download-run for downloads")
        require(
            bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", args.download_run))
            and args.download_run not in {".", ".."},
            "Invalid run name",
        )
        directory = ROOT / "work/runs" / args.download_run
        receipt = read_json(directory / "receipt.json")
        require(receipt["state"] == "SUCCEEDED", "Artifact download requires a succeeded run receipt")
        target = read_json(directory / "target.json")
        client, _ = client_for({**env, "RHOAI_KFP_URL": target["endpoint"]}, target["namespace"])
        download_run_artifacts(client, env, directory)
        return
    config = configuration(env)
    namespace = env.get("RHOAI_PROJECT_NAME", "").strip()
    non_placeholder(namespace, "RHOAI_PROJECT_NAME")
    experiment = env.get("AUTORAG_EXPERIMENT_NAME", "autorag-audio-sample").strip()
    non_placeholder(experiment, "AUTORAG_EXPERIMENT_NAME")
    try:
        timeout = int(env.get("RHOAI_PIPELINE_RUN_TIMEOUT", "7200"))
    except ValueError:
        raise ValueError("RHOAI_PIPELINE_RUN_TIMEOUT must be a positive integer in seconds") from None
    require(timeout > 0, "RHOAI_PIPELINE_RUN_TIMEOUT must be positive")
    pattern, collection = None, None
    params = optimization_params(config)
    plan = None
    if args.kind == "indexing":
        non_placeholder(env.get("AUTORAG_PATTERN_FILE"), "AUTORAG_PATTERN_FILE")
        collection = env.get("AUTORAG_COLLECTION_NAME", "").strip()
        non_placeholder(collection, "AUTORAG_COLLECTION_NAME")
        pattern = read_json(Path(env["AUTORAG_PATTERN_FILE"]))
    elif flag(env, "AUTORAG_UPLOAD_TEST_DATASETS"):
        plan = upload_plan(config)
    name = OPTIMIZATION_PIPELINE if args.kind == "optimization" else INDEXING_PIPELINE
    path_variable = (
        "AUTORAG_PIPELINE_PATH" if args.kind == "optimization" else "AUTORAG_INDEXING_PIPELINE_PATH"
    )
    raw_path = env.get(path_variable, "").strip()
    spec, package_content, local_path, bound = None, None, None, None
    if raw_path:
        local_path = Path(raw_path).expanduser()
        if not local_path.is_absolute():
            local_path = args.env_file.resolve().parent / local_path
        local_path = local_path.resolve()
        spec, package_content = read_package(local_path, name)
        if args.kind == "indexing":
            params, bound = prepare(pattern, spec, config, collection)
        validate_pipeline_params(params, spec, name)
    print(f"Project: {namespace}; experiment: {experiment}; pipeline: {args.kind}")
    print(
        f"Pipeline source: local package {local_path}" if local_path else f"Pipeline source: managed {name}"
    )
    print(f"Audio: s3://{config['bucket']}/{params['input_data_keys'][0]}")
    if args.kind == "optimization":
        print(
            f"Dataset upload: enabled; {len(plan)} local files will be verified in S3 before submission"
            if plan is not None
            else "Dataset upload: disabled; using existing S3 objects (AUTORAG_UPLOAD_TEST_DATASETS=false)"
        )
    else:
        print("Dataset upload: skipped for indexing; reusing existing S3 objects")
    if args.kind == "optimization":
        print(f"Benchmark: s3://{params['test_data_bucket_name']}/{params['test_data_key']}")
        print(
            f"Metric: {config['optimization_metric']}; "
            f"max patterns: {config['optimization_max_rag_patterns']}"
        )
    if args.dry_run:
        print(
            "Local configuration valid. No cluster or S3 requests made; "
            "cluster data access and model availability remain unchecked."
        )
        return
    run_name = env.get("AUTORAG_RUN_NAME", "").strip() or (
        f"audio-{args.kind}-{datetime.now(UTC):%Y%m%d-%H%M%S}-{uuid4().hex[:8]}"
    )
    require(bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", run_name)), "Invalid AUTORAG_RUN_NAME")
    directory = ROOT / "work/runs" / run_name
    require(not directory.exists(), f"Run record already exists: {directory}; inspect it before retrying")
    directory.mkdir(parents=True, exist_ok=False)
    print(f"Run records (generated automatically): {directory}")
    package_path = None
    if local_path:
        package_path = directory / "package.yaml"
        package_path.write_bytes(package_content)
        pinned = {
            "source": "local",
            "pipeline_id": None,
            "version_id": None,
            "package_path": str(local_path),
            "package_sha256": hashlib.sha256(package_content).hexdigest(),
        }
    client, endpoint = client_for(env, namespace)
    if local_path is None:
        kind_env = args.kind.upper()
        pinned, spec = pin_pipeline(
            client,
            namespace,
            name,
            env.get(f"AUTORAG_{kind_env}_PIPELINE_ID") or None,
            env.get(f"AUTORAG_{kind_env}_VERSION_ID") or None,
        )
        pinned["source"] = "managed"
        print(f"Pinned {args.kind}: pipeline {pinned['pipeline_id']}, version {pinned['version_id']}")
        if args.kind == "indexing":
            params, bound = prepare(pattern, spec, config, collection)
    if bound is not None:
        write_json(directory / "pattern.bound.json", bound["pattern"])
    validate_pipeline_params(params, spec, name)
    write_json(directory / "spec.json", spec)
    write_json(directory / "params.json", params)
    write_json(directory / "target.json", {"namespace": namespace, "endpoint": endpoint, **pinned})
    if plan is not None:
        upload(env, config, plan)
    experiments = [
        item
        for item in all_items(client, "list_experiments", "experiments", namespace=namespace)
        if item.display_name == experiment
    ]
    require(
        len(experiments) <= 1, "Multiple experiments have this name; set a unique AUTORAG_EXPERIMENT_NAME"
    )
    if not experiments:
        experiments = [
            remote_call("experiment creation", client.create_experiment, name=experiment, namespace=namespace)
        ]
    receipt = directory / "receipt.json"
    print(f"Submitting {run_name}. If interrupted, check {receipt} and the pipelines UI before retrying.")
    run_id = submit(
        client,
        kind=args.kind,
        name=name,
        pinned=pinned,
        experiment_id=experiments[0].experiment_id,
        run_name=run_name,
        directory=directory,
        timeout=timeout,
        package_path=package_path,
    )
    print(f"Completed {args.kind}; run ID: {run_id}")
    print(f"Run details: {endpoint.rstrip('/')}/#/runs/details/{run_id}")
    if download_enabled:
        download_run_artifacts(client, env, directory)


if __name__ == "__main__":
    cli(main)
