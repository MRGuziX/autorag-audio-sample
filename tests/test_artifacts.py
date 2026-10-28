"""Run-scoped downloads, local path handling and download-only recovery."""

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_experiment as runner  # noqa: E402
from lib.artifacts import artifact_location, download_objects, download_run_artifacts  # noqa: E402
from lib.sample import read_json, write_json  # noqa: E402
from lib.storage import s3_client  # noqa: E402
from test_env_runner import environment, mock_client  # noqa: E402


class ArtifactTests(unittest.TestCase):
    def test_run_root_and_optional_bucket_override(self):
        run = SimpleNamespace(runtime_config=SimpleNamespace(pipeline_root="s3://outputs/team"))
        self.assertEqual(
            artifact_location(run, "pipeline", "run-id", {}), ("outputs", "team/pipeline/run-id/")
        )
        self.assertEqual(
            artifact_location(run, "pipeline", "run-id", {"AWS_S3_BUCKET": "other"}),
            ("other", "team/pipeline/run-id/"),
        )
        for root in ("https://storage/path", "s3://outputs/../outside"):
            with self.subTest(root=root), self.assertRaises(ValueError):
                artifact_location(
                    SimpleNamespace(runtime_config=SimpleNamespace(pipeline_root=root)),
                    "pipeline",
                    "run-id",
                    {},
                )

    def test_missing_root_uses_configured_artifact_bucket_or_input_bucket(self):
        run = SimpleNamespace(runtime_config=None, pipeline_spec={})
        for env, bucket in (
            ({"AWS_S3_BUCKET": "artifacts"}, "artifacts"),
            ({"RHOAI_TEST_ARTIFACTS_BUCKET": "ci-artifacts"}, "ci-artifacts"),
            ({"INPUT_DATA_BUCKET_NAME": "input"}, "input"),
        ):
            self.assertEqual(artifact_location(run, "pipeline", "run-id", env), (bucket, "pipeline/run-id/"))

    def test_downloads_paginated_objects_only_from_this_run(self):
        client = Mock()
        prefix = "pipeline/run-id/"
        keys = [prefix + "task/pattern/pattern.json", prefix + "task/notebooks/inference.ipynb"]
        client.get_paginator.return_value.paginate.return_value = [
            {"Contents": [{"Key": prefix}, {"Key": keys[0]}]},
            {"Contents": [{"Key": keys[1]}]},
        ]
        client.download_file.side_effect = lambda bucket, key, path: Path(path).write_text(key)
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            self.assertEqual(download_objects(client, "bucket", prefix, dest), 2)
            self.assertEqual((dest / "task/pattern/pattern.json").read_text(), keys[0])
            self.assertEqual(len(list(dest.rglob("*.ipynb"))), 1)
        client.get_paginator.return_value.paginate.assert_called_once_with(Bucket="bucket", Prefix=prefix)

    def test_empty_or_unsafe_results_fail_without_downloading(self):
        for contents in ([], [{"Key": "pipeline/other-run/file"}], [{"Key": "pipeline/run-id/../escape"}]):
            client = Mock()
            client.get_paginator.return_value.paginate.return_value = [{"Contents": contents}]
            with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
                download_objects(client, "bucket", "pipeline/run-id/", Path(tmp))
            client.download_file.assert_not_called()

    def test_failed_transfer_preserves_completed_file_and_removes_temporary_file(self):
        client = Mock()
        client.get_paginator.return_value.paginate.return_value = [{"Contents": [{"Key": "p/run/file"}]}]

        def fail(bucket, key, path):
            Path(path).write_text("partial")
            raise OSError("transfer interrupted")

        client.download_file.side_effect = fail
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            (dest / "file").write_text("previous complete artifact")
            with self.assertRaises(OSError):
                download_objects(client, "bucket", "p/run/", dest)
            self.assertEqual((dest / "file").read_text(), "previous complete artifact")
            self.assertEqual([p.name for p in dest.iterdir()], ["file"])

    def test_shared_s3_client_uses_dotenv_credentials_without_exporting(self):
        with patch("boto3.client") as constructor:
            s3_client(
                {
                    "AWS_S3_ENDPOINT": "https://storage.example.test",
                    "AWS_ACCESS_KEY_ID": "key",
                    "AWS_SECRET_ACCESS_KEY": "secret",
                    "AWS_SESSION_TOKEN": "session",
                }
            )
        constructor.assert_called_once_with(
            "s3",
            endpoint_url="https://storage.example.test",
            region_name="us-east-1",
            aws_access_key_id="key",
            aws_secret_access_key="secret",
            aws_session_token="session",
        )

    def test_download_failure_keeps_pipeline_success_and_retry_does_not_submit(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "work/runs/existing-run"
            write_json(
                directory / "receipt.json",
                {"state": "SUCCEEDED", "run_id": "run-id", "pipeline_name": "pipeline"},
            )
            write_json(directory / "target.json", {"namespace": "project", "endpoint": "https://kfp.test"})
            client = Mock()
            client.get_run.return_value = SimpleNamespace(runtime_config=None, pipeline_spec={})
            with (
                patch("lib.artifacts.s3_client"),
                patch("lib.artifacts.download_objects", side_effect=OSError),
            ):
                with self.assertRaisesRegex(RuntimeError, "--download-run existing-run"):
                    download_run_artifacts(client, environment(), directory)
            receipt = read_json(directory / "receipt.json")
            self.assertEqual(receipt["state"], "SUCCEEDED")
            self.assertEqual(receipt["artifact_download"]["state"], "FAILED")
            with (
                patch.object(runner, "ROOT", Path(tmp)),
                patch.object(runner, "read_env", return_value=environment()),
                patch.object(runner, "client_for", return_value=(client, "https://kfp.test")),
                patch("lib.artifacts.s3_client"),
                patch("lib.artifacts.download_objects", return_value=3),
            ):
                runner.main(["--download-run", "existing-run"])
            receipt = read_json(directory / "receipt.json")
            self.assertEqual(receipt["artifact_download"]["files"], 3)
            self.assertEqual(receipt["artifact_download"]["state"], "SUCCEEDED")
            client.run_pipeline.assert_not_called()

    def test_flag_controls_automatic_download_after_success(self):
        for enabled in (False, True):
            env = {**environment(), "DOWNLOAD_ARTIFACTS": str(enabled).lower()}
            client = mock_client()
            with (
                tempfile.TemporaryDirectory() as tmp,
                patch.object(runner, "ROOT", Path(tmp)),
                patch.object(runner, "read_env", return_value=env),
                patch.object(runner, "client_for", return_value=(client, "https://kfp.test")),
                patch.object(runner, "download_run_artifacts") as download,
            ):
                runner.main([])
                self.assertEqual(download.call_count, int(enabled))
                self.assertEqual(
                    read_json(Path(tmp) / "work/runs/test-run/receipt.json")["state"], "SUCCEEDED"
                )


if __name__ == "__main__":
    unittest.main()
