"""Build an audio allowlist and stage it with checksum verification."""

import hashlib
import io
import json
import mimetypes

from lib.sample import load_sample, local_path, render_config_questions, require


def s3_client(env: dict):
    """Use dotenv credentials without exporting or persisting them."""
    import boto3

    kwargs = {
        "endpoint_url": env.get("AWS_ENDPOINT_URL_S3") or env.get("AWS_S3_ENDPOINT"),
        "region_name": env.get("AWS_DEFAULT_REGION") or "us-east-1",
    }
    for variable, argument in (
        ("AWS_ACCESS_KEY_ID", "aws_access_key_id"),
        ("AWS_SECRET_ACCESS_KEY", "aws_secret_access_key"),
        ("AWS_SESSION_TOKEN", "aws_session_token"),
    ):
        if env.get(variable):
            kwargs[argument] = env[variable]
    return boto3.client("s3", **kwargs)


def upload_plan(config: dict) -> list[dict]:
    require(
        config.get("test_data_bucket_name", config["bucket"]) == config["bucket"]
        and config["test_data_secret_name"] == config["input_data_secret_name"],
        "Uploads require the same input and benchmark bucket and Connection",
    )
    files, benchmark = load_sample(config["input_data_keys"][0], config["test_data_key"])
    rendered = render_config_questions(benchmark, config)
    benchmark_bytes = (json.dumps(rendered, ensure_ascii=False, indent=2) + "\n").encode()
    # Reference text remains local.
    plan = [
        {
            "key": f["object_key"],
            "path": local_path(f["path"]),
            "sha256": f["sha256"],
            "bytes": f["bytes"],
        }
        for f in files
    ]
    plan.append(
        {
            "key": config["test_data_key"],
            "body": benchmark_bytes,
            "sha256": hashlib.sha256(benchmark_bytes).hexdigest(),
            "bytes": len(benchmark_bytes),
        }
    )
    return plan


def stage(client, bucket: str, audio_directory: str, plan: list[dict]) -> None:
    """Preflight all objects before writing; refuse stale corpus objects and conflicting uploads."""
    from botocore.exceptions import ClientError

    audio_prefix = audio_directory.rstrip("/") + "/"
    expected = {item["key"] for item in plan if item["key"].startswith(audio_prefix)}
    paginator = client.get_paginator("list_objects_v2")
    actual = {
        obj["Key"]
        for page in paginator.paginate(Bucket=bucket, Prefix=audio_prefix)
        for obj in page.get("Contents", [])
    }
    require(
        not actual - expected,
        "Unexpected objects in audio prefix; choose a fresh prefix: " + str(actual - expected),
    )
    pending = []
    for item in plan:
        try:
            response = client.get_object(Bucket=bucket, Key=item["key"])
        except ClientError as exc:
            if exc.response["Error"]["Code"] not in ("NoSuchKey", "404"):
                raise
            pending.append(item)
            continue
        with response["Body"] as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest == item["sha256"]:
            print(f"Already verified: {item['key']}")
        else:
            raise ValueError(f"Different object already exists: {item['key']}; choose a fresh prefix")
    for item in pending:
        content_type = mimetypes.guess_type(item["key"])[0] or "application/octet-stream"
        with item["path"].open("rb") if "path" in item else io.BytesIO(item["body"]) as body:
            # Conditional creation prevents an intervening writer being overwritten by default.
            client.put_object(
                Bucket=bucket,
                Key=item["key"],
                Body=body,
                ContentType=content_type,
                Metadata={"sha256": item["sha256"]},
                IfNoneMatch="*",
            )
        response = client.get_object(Bucket=bucket, Key=item["key"])
        with response["Body"] as stream:
            require(
                hashlib.file_digest(stream, "sha256").hexdigest() == item["sha256"],
                "Remote checksum mismatch",
            )
        print(f"Uploaded and verified: {item['key']}")
