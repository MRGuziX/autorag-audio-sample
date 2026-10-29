"""Local compiled packages and managed fallback share the same submission/evidence boundaries."""

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_experiment as runner  # noqa: E402
from lib.pipelines import read_package  # noqa: E402
from lib.sample import OPTIMIZATION_PIPELINE, read_json, write_json  # noqa: E402
from test_env_runner import environment, mock_client  # noqa: E402
from test_sample import indexing_pattern  # noqa: E402


def package(path, kind="optimization"):
    spec = mock_client(kind).get_pipeline_version.return_value.pipeline_spec
    path.write_text(yaml.safe_dump_all([spec["pipeline_spec"], spec["platform_spec"]]), encoding="utf-8")
    return spec


class LocalPipelineTests(unittest.TestCase):
    def test_unset_empty_or_whitespace_path_uses_managed_pipeline(self):
        for value in (None, "", "  "):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as tmp:
                env = environment()
                if value is not None:
                    env["AUTORAG_PIPELINE_PATH"] = value
                client = mock_client()
                with (
                    patch.object(runner, "ROOT", Path(tmp)),
                    patch.object(runner, "read_env", return_value=env),
                    patch.object(
                        runner, "client_for", return_value=(client, "https://pipeline.example.test")
                    ),
                ):
                    runner.main([])
                client.list_pipelines.assert_called_once()
                kwargs = client.run_pipeline.call_args.kwargs
                self.assertEqual(kwargs["pipeline_id"], "pipeline-id")
                self.assertNotIn("pipeline_package_path", kwargs)
                receipt = read_json(Path(tmp) / "work/runs/test-run/receipt.json")
                self.assertEqual(receipt["pipeline_source"], "managed")

    def test_local_yaml_skips_managed_discovery_and_saves_exact_package_and_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "pipeline.yaml"
            spec = package(path)
            content = path.read_bytes()
            client = mock_client()
            env = {
                **environment(),
                "AUTORAG_PIPELINE_PATH": str(path),
                "AUTORAG_OPTIMIZATION_PIPELINE_ID": "ignored-managed-id",
            }
            with (
                patch.object(runner, "ROOT", root),
                patch.object(runner, "read_env", return_value=env),
                patch.object(runner, "client_for", return_value=(client, "https://pipeline.example.test")),
            ):
                runner.main([])
            directory = root / "work/runs/test-run"
            snapshot = directory / "pipeline.yaml"
            self.assertEqual(snapshot.read_bytes(), content)
            self.assertEqual(read_json(directory / "spec.json"), spec)
            client.list_pipelines.assert_not_called()
            client.list_pipeline_versions.assert_not_called()
            client.get_pipeline_version.assert_not_called()
            kwargs = client.run_pipeline.call_args.kwargs
            self.assertEqual(kwargs["pipeline_package_path"], str(snapshot))
            self.assertNotIn("pipeline_id", kwargs)
            self.assertNotIn("version_id", kwargs)
            receipt = read_json(directory / "receipt.json")
            self.assertEqual(receipt["pipeline_source"], "local")
            self.assertEqual(receipt["package_sha256"], hashlib.sha256(content).hexdigest())
            self.assertEqual(receipt["package_path"], str(path.resolve()))
            self.assertIsNone(receipt["pipeline_id"])

    def test_relative_path_uses_env_file_directory_and_dry_run_never_connects(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            package(directory / "pipeline.yaml")
            env = {**environment(), "AUTORAG_PIPELINE_PATH": "pipeline.yaml"}
            with (
                patch.object(runner, "read_env", return_value=env),
                patch.object(runner, "client_for") as client,
            ):
                runner.main(["--env-file", str(directory / ".env"), "--dry-run"])
                client.assert_not_called()
            self.assertFalse((directory / "work").exists())

    def test_invalid_local_packages_fail_before_connection_without_managed_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            valid = directory / "valid.yaml"
            spec = package(valid)
            wrong = directory / "wrong.yaml"
            package(wrong, "indexing")
            malformed = directory / "malformed.yaml"
            malformed.write_text("pipelineInfo: [broken yaml")
            missing_deployment = directory / "missing-deployment.yaml"
            body = spec["pipeline_spec"].copy()
            body.pop("deploymentSpec")
            missing_deployment.write_text(yaml.safe_dump(body))
            incompatible = directory / "incompatible.yaml"
            body = spec["pipeline_spec"]
            body["root"]["inputDefinitions"]["parameters"].pop("preset")
            incompatible.write_text(yaml.safe_dump(body))
            for path in (directory / "absent.yaml", wrong, malformed, missing_deployment, incompatible):
                with self.subTest(path=path.name):
                    env = {**environment(), "AUTORAG_PIPELINE_PATH": str(path)}
                    with (
                        patch.object(runner, "read_env", return_value=env),
                        patch.object(runner, "client_for") as client,
                    ):
                        with self.assertRaises(ValueError):
                            runner.main(["--dry-run"])
                        client.assert_not_called()

    def test_indexing_uses_its_own_path_and_selected_pattern(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "indexing.yaml"
            package(path, "indexing")
            pattern = root / "pattern.json"
            write_json(pattern, indexing_pattern())
            env = {
                **environment(),
                "AUTORAG_PIPELINE_PATH": "/ignored/optimization.yaml",
                "AUTORAG_INDEXING_PIPELINE_PATH": str(path),
                "AUTORAG_PATTERN_FILE": str(pattern),
                "AUTORAG_COLLECTION_NAME": "new_collection",
            }
            client = mock_client("indexing")
            with (
                patch.object(runner, "ROOT", root),
                patch.object(runner, "read_env", return_value=env),
                patch.object(runner, "client_for", return_value=(client, "https://pipeline.example.test")),
            ):
                runner.main(["--kind", "indexing"])
            kwargs = client.run_pipeline.call_args.kwargs
            self.assertIn("pipeline_package_path", kwargs)
            self.assertEqual(kwargs["params"]["collection_name"], "new_collection")
            client.list_pipelines.assert_not_called()

    def test_package_submission_error_keeps_uncertain_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "pipeline.yaml"
            package(path)
            env = {**environment(), "AUTORAG_PIPELINE_PATH": str(path)}
            client = mock_client()
            client.run_pipeline.side_effect = ConnectionError("interrupted")
            with (
                patch.object(runner, "ROOT", root),
                patch.object(runner, "read_env", return_value=env),
                patch.object(runner, "client_for", return_value=(client, "https://pipeline.example.test")),
            ):
                with self.assertRaisesRegex(RuntimeError, "outcome may be uncertain"):
                    runner.main([])
            receipt = read_json(root / "work/runs/test-run/receipt.json")
            self.assertEqual(receipt["state"], "SUBMISSION_UNCERTAIN")
            self.assertEqual(receipt["pipeline_source"], "local")
            client.run_pipeline.assert_called_once()

    def test_sdk_reads_the_same_platform_settings_from_package_snapshot(self):
        from kfp.client.client import _extract_pipeline_yaml

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pipeline.yaml"
            expected = package(path)
            spec, _ = read_package(path, OPTIMIZATION_PIPELINE)
            actual = _extract_pipeline_yaml(str(path)).to_dict()
            self.assertEqual(actual["platform_spec"], expected["platform_spec"])
            self.assertEqual(actual["pipeline_spec"]["pipelineInfo"], spec["pipeline_spec"]["pipelineInfo"])


if __name__ == "__main__":
    unittest.main()
