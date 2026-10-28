"""Download only one run's S3 artifacts, preserving the object directory structure."""

from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit

from lib.pipelines import remote_call
from lib.sample import read_json, relative_path, require, write_json
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


def download_objects(client, bucket: str, prefix: str, destination: Path) -> int:
    count = 0
    destination.mkdir(parents=True, exist_ok=True)
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            require(key.startswith(prefix), "S3 returned an object outside the selected run")
            if key.endswith("/"):
                continue
            suffix = relative_path(key[len(prefix) :])
            path = destination / suffix
            require(
                path.resolve().is_relative_to(destination.resolve()), "Artifact path leaves download folder"
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            # Replace an artifact only after the transfer completes.
            with NamedTemporaryFile(dir=path.parent, prefix=".download-", delete=False) as stream:
                temporary = Path(stream.name)
            try:
                client.download_file(bucket, key, str(temporary))
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
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
        count = download_objects(s3_client(env), bucket, prefix, destination)
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
