"""Download only one run's S3 artifacts, preserving the object directory structure."""

import json
import math
import re
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit
from zipfile import BadZipFile, ZipFile

from lib.pipelines import remote_call
from lib.sample import OPTIMIZATION_PIPELINE, read_json, relative_path, require, write_json
from lib.storage import s3_client


def artifact_location(run, pipeline_name: str, run_id: str, env: dict) -> tuple[str, str]:
    runtime = getattr(run, "runtime_config", None)
    root = getattr(runtime, "pipeline_root", None)
    if not root:
        spec = getattr(run, "pipeline_spec", None)
        root = spec.get("defaultPipelineRoot") if isinstance(spec, dict) else None
    bucket = env.get("AWS_S3_BUCKET", "").strip() or env.get("RHOAI_TEST_ARTIFACTS_BUCKET", "").strip()
    base = ""
    if root:
        uri = urlsplit(root)
        require(uri.scheme == "s3" and bool(uri.netloc), "Run artifact root must be an s3:// URI")
        require(not uri.query and not uri.fragment, "Run artifact root has unexpected URI parameters")
        bucket = bucket or uri.netloc
        base = uri.path.strip("/")
    bucket = bucket or env.get("INPUT_DATA_BUCKET_NAME", "").strip()
    require(bool(bucket) and "/" not in bucket and ":" not in bucket, "Set AWS_S3_BUCKET")
    prefix = "/".join(part for part in (base, pipeline_name, run_id) if part)
    relative_path(prefix)
    return bucket, prefix + "/"


def object_keys(client, bucket: str, prefix: str) -> list[str]:
    keys = []
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            require(key.startswith(prefix), "S3 returned an object outside the selected run")
            if not key.endswith("/"):
                relative_path(key[len(prefix) :])
                keys.append(key)
    return sorted(set(keys))


def select_best_pattern(client, bucket: str, keys: list[str], metric: str) -> dict:
    evaluator, separator, name = metric.partition(":")
    if not separator:
        name, evaluator = metric, None
    rankings = []
    for key in keys:
        if not key.endswith("/pattern.json") or "rag_patterns" not in PurePosixPath(key).parts:
            continue
        response = client.get_object(Bucket=bucket, Key=key)
        with response["Body"] as stream:
            pattern = json.load(stream)
        metrics = pattern.get("evaluation", {}).get("metrics", [])
        matches = [
            item
            for item in metrics
            if item.get("name") == name and (evaluator is None or item.get("evaluator") == evaluator)
        ]
        marked = [item for item in matches if item.get("optimization_metric") is True]
        matches = marked or matches
        require(len(matches) <= 1, "Ambiguous optimization metric in pattern; specify its evaluator")
        if not matches:
            continue
        result = matches[0]
        score = result.get("scores", {}).get("mean")
        if type(score) not in (int, float) or not math.isfinite(score):
            continue
        rankings.append(
            {
                "name": pattern.get("name") or PurePosixPath(key).parent.name,
                "score": score,
                "metric": result["name"],
                "evaluator": result.get("evaluator"),
                "pattern_key": key,
            }
        )
    require(bool(rankings), f"No patterns have a finite score for optimization metric {metric}")
    require(
        len({item["evaluator"] for item in rankings}) == 1,
        "Optimization scores use different evaluators; specify an evaluator-qualified metric",
    )
    rankings.sort(key=lambda item: (-item["score"], item["name"], item["pattern_key"]))
    kits = [key for key in keys if key.endswith("/starter_kit.zip")]
    require(len(kits) == 1, "Expected one starter_kit.zip for this optimization run")
    return {**rankings[0], "starter_kit_key": kits[0], "rankings": rankings}


def match_starter_kit(best: dict, path: Path) -> dict:
    """Use the product kit's named pattern when several patterns share the best score."""
    try:
        with ZipFile(path) as archive:
            heading = archive.read("starter_kit/README.md").decode("utf-8").splitlines()[0]
    except (BadZipFile, KeyError, UnicodeError, IndexError):
        raise ValueError("Cannot identify the pattern in the product starter_kit.zip README") from None
    match = re.fullmatch(r"# Agentic RAG Starter Kit: `(.+)`", heading.strip())
    require(match is not None, "Unrecognized product starter-kit README; cannot verify its pattern")
    candidates = [
        row for row in best["rankings"] if row["name"] == match[1] and row["score"] == best["score"]
    ]
    require(len(candidates) == 1, "Starter kit does not identify a highest-scoring pattern for this metric")
    return {**best, **candidates[0]}


def download_object(client, bucket: str, key: str, path: Path) -> None:
    """Replace an artifact only after its transfer completes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, prefix=".download-", delete=False) as stream:
        temporary = Path(stream.name)
    try:
        client.download_file(bucket, key, str(temporary))
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def download_objects(
    client, bucket: str, prefix: str, destination: Path, keys: list[str] | None = None
) -> int:
    count = 0
    destination.mkdir(parents=True, exist_ok=True)
    if keys is None:
        keys = object_keys(client, bucket, prefix)
    for key in keys:
        require(key.startswith(prefix), "S3 returned an object outside the selected run")
        if key.endswith("/"):
            continue
        suffix = relative_path(key[len(prefix) :])
        path = destination / suffix
        require(path.resolve().is_relative_to(destination.resolve()), "Artifact path leaves download folder")
        download_object(client, bucket, key, path)
        count += 1
    require(count > 0, "No run artifacts found; check AWS_S3_BUCKET and the run's S3 location")
    return count


def download_run_artifacts(client, env: dict, directory: Path) -> None:
    receipt_path = directory / "receipt.json"
    receipt = read_json(receipt_path)
    run_id = receipt["run_id"]
    destination = directory / "artifacts"
    receipt["artifact_download"] = {"state": "DOWNLOADING"}
    write_json(receipt_path, receipt)
    try:
        run = remote_call("artifact location lookup", client.get_run, run_id=run_id)
        bucket, prefix = artifact_location(run, receipt["pipeline_name"], run_id, env)
        receipt["artifact_download"].update(bucket=bucket, prefix=prefix)
        write_json(receipt_path, receipt)
        storage = s3_client(env)
        if receipt.get("kind") == "optimization" or receipt["pipeline_name"] == OPTIMIZATION_PIPELINE:
            keys = object_keys(storage, bucket, prefix)
            metric = read_json(directory / "params.json")["optimization_metric"]
            best = select_best_pattern(storage, bucket, keys, metric)
            download_object(storage, bucket, best["starter_kit_key"], destination / "starter_kit.zip")
            best = match_starter_kit(best, destination / "starter_kit.zip")
            receipt["artifact_download"]["best_pattern"] = best
            write_json(receipt_path, receipt)
            pattern_prefix = best["pattern_key"].rsplit("/", 1)[0] + "/"
            selected_keys = [key for key in keys if key.startswith(pattern_prefix)]
            count = 1 + download_objects(
                storage, bucket, pattern_prefix, destination / "best-pattern", selected_keys
            )
            task_prefix = best["pattern_key"].rsplit("/rag_patterns/", 1)[0] + "/"
            leaderboard_keys = [
                key
                for key in keys
                if key.startswith(task_prefix)
                and PurePosixPath(key[len(task_prefix) :]).parts[0] in {"leaderboard", "leaderboard_html"}
            ]
            require(len(leaderboard_keys) <= 1, "Multiple leaderboard files found for the optimization task")
            if leaderboard_keys:
                download_object(storage, bucket, leaderboard_keys[0], destination / "leaderboard.html")
                count += 1
                receipt["artifact_download"]["leaderboard_key"] = leaderboard_keys[0]
            else:
                print("No product leaderboard artifact found; check the run's outputs in the pipeline UI")
            print(f"Best pattern: {best['name']}; {best['evaluator']}:{best['metric']}={best['score']}")
            print(f"Pattern file: {destination / 'best-pattern/pattern.json'}")
        else:
            count = download_objects(storage, bucket, prefix, destination)
    except Exception as exc:
        receipt["artifact_download"]["state"] = "FAILED"
        write_json(receipt_path, receipt)
        # Our validation messages are safe; storage/API exception bodies may contain private values.
        reason = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        raise RuntimeError(
            f"Run {run_id} succeeded, but artifact download failed ({reason}). Check S3 settings and access; "
            f"retry with --download-run {directory.name}. The experiment will not be resubmitted."
        ) from None
    receipt["artifact_download"].update(state="SUCCEEDED", files=count)
    write_json(receipt_path, receipt)
    print(f"Downloaded {count} artifact files to {destination}")
