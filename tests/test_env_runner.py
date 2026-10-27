"""One-file workflow: scenario parity, auth, generated records and safe submission boundaries."""

import json
import os
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_experiment as runner  # noqa: E402
from lib.sample import INDEXING_PIPELINE, OPTIMIZATION_PIPELINE, read_json, write_json  # noqa: E402
from test_sample import indexing_pattern  # noqa: E402


def environment():
    return {
        "RHOAI_PROJECT_NAME": "sample-project",
        "RHOAI_KFP_URL": "https://pipeline.example.test",
        "RHOAI_TOKEN": "private-token-do-not-save",
        "INPUT_DATA_BUCKET_NAME": "sample-bucket",
        "INPUT_DATA_SECRET_NAME": "s3-connection",
        "MAAS_SECRET_NAME": "maas",
        "VECTOR_DB_SECRET_NAME": "milvus",
        "AUTORAG_EMBEDDING_MODELS": '["embedding"]',
        "AUTORAG_GENERATION_MODELS": "generation-one,generation-two",
        "AUTORAG_RUN_NAME": "test-run",
    }


def mock_client(kind="optimization"):
    client = Mock()
    name = OPTIMIZATION_PIPELINE if kind == "optimization" else INDEXING_PIPELINE
    body = read_json(ROOT / f"tests/fixtures/{kind}.parameters.json")
    body["deploymentSpec"] = {"executors": {"example": {"container": {"image": "example"}}}}
    client.list_pipelines.return_value = Mock(
        pipelines=[Mock(display_name=name, pipeline_id="pipeline-id")], next_page_token=""
    )
    client.list_pipeline_versions.return_value = Mock(
        pipeline_versions=[Mock(pipeline_version_id="version-id")], next_page_token=""
    )
    client.get_pipeline_version.return_value.pipeline_spec = {
        "pipeline_spec": body,
        "platform_spec": {"platforms": {"kubernetes": {}}},
    }
    client.list_experiments.return_value = Mock(experiments=[], next_page_token="")
    client.create_experiment.return_value = Mock(experiment_id="experiment-id")
    client.run_pipeline.return_value = Mock(run_id="run-id", state="PENDING")
    client.wait_for_run_completion.return_value = Mock(state="SUCCEEDED")
    return client


class EnvRunnerTests(unittest.TestCase):
    def test_defaults_match_tc_p_5_and_support_separate_benchmark_bucket(self):
        env = environment()
        env["TEST_DATA_BUCKET_NAME"] = "benchmark-bucket"
        params = runner.optimization_params(runner.configuration(env))
        self.assertEqual(params["input_data_keys"], ["datasets/rag/audio/documents"])
        self.assertEqual(params["test_data_key"], "datasets/rag/audio/benchmark_data.json")
        self.assertEqual(params["optimization_metric"], "answer_correctness")
        self.assertEqual(params["optimization_max_rag_patterns"], 4)
        self.assertEqual(params["test_data_bucket_name"], "benchmark-bucket")
        self.assertEqual(params["generation_models"], ["generation-one", "generation-two"])
        self.assertNotIn("RHOAI_TOKEN", params)

    def test_env_is_data_and_shell_values_override_without_interpolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("VALUE=file\nLITERAL='$(echo secret) ${VALUE}'\n", encoding="utf-8")
            with patch.dict(os.environ, {"VALUE": "shell"}, clear=True):
                env = runner.read_env(path)
            self.assertEqual(env["VALUE"], "shell")
            self.assertEqual(env["LITERAL"], "$(echo secret) ${VALUE}")

    def test_missing_and_invalid_settings_fail_before_connecting(self):
        for name, value in (
            ("RHOAI_PROJECT_NAME", ""),
            ("AUTORAG_EMBEDDING_MODELS", "[bad json"),
            ("AUTORAG_MAX_RAG_PATTERNS", "3"),
            ("AUTORAG_INPUT_DATA_KEYS", "[]"),
            ("AUTORAG_TEST_DATA_KEY", "datasets/rag/audio/documents/labels.json"),
            ("RHOAI_PIPELINE_RUN_TIMEOUT", "0"),
        ):
            with self.subTest(name=name):
                env = {**environment(), name: value}
                with (
                    patch.object(runner, "read_env", return_value=env),
                    patch.object(runner, "client_for") as client,
                ):
                    with self.assertRaises(ValueError):
                        runner.main(["--dry-run"])
                    client.assert_not_called()

    def test_existing_s3_dry_run_needs_no_cluster_or_local_corpus(self):
        env = {**environment(), "AUTORAG_DATASET_DIR": "samples/missing-local-data"}
        with (
            patch.object(runner, "read_env", return_value=env),
            patch.object(runner, "client_for") as client,
            patch.object(runner, "load_sample") as load_sample,
            patch.object(runner, "upload") as upload,
        ):
            runner.main(["--dry-run"])
            client.assert_not_called()
            load_sample.assert_not_called()
            upload.assert_not_called()

    def test_token_auth_does_not_require_oc(self):
        with patch("kfp.Client") as constructor, patch.object(runner, "oc") as oc:
            runner.client_for(environment(), "sample-project")
            self.assertEqual(constructor.call_args.kwargs["existing_token"], "private-token-do-not-save")
            self.assertEqual(constructor.call_args.kwargs["namespace"], "sample-project")
            oc.assert_not_called()

    def test_blank_token_reuses_oc_login(self):
        env = {**environment(), "RHOAI_TOKEN": ""}
        with (
            patch("kfp.Client") as constructor,
            patch.object(runner, "context_info", return_value={"context": "selected-context"}),
            patch.object(runner, "oc", return_value="session-token") as oc,
        ):
            runner.client_for(env, "sample-project")
            oc.assert_called_once_with("whoami", "--show-token", context="selected-context")
            self.assertEqual(constructor.call_args.kwargs["existing_token"], "session-token")

    def test_blank_endpoint_discovers_only_the_selected_project(self):
        env = {**environment(), "RHOAI_TOKEN": "", "RHOAI_KFP_URL": ""}
        dspa = {"metadata": {"name": "dspa", "uid": "owned"}}
        route = {
            "metadata": {"name": "ds-pipeline-dspa", "ownerReferences": [{"uid": "owned"}]},
            "spec": {"host": "pipeline.example.test", "tls": {"termination": "reencrypt"}},
        }
        with (
            patch("kfp.Client") as constructor,
            patch.object(runner, "context_info", return_value={"context": "selected-context"}),
            patch.object(
                runner,
                "oc",
                side_effect=["session-token", json.dumps({"items": [dspa]}), json.dumps({"items": [route]})],
            ) as oc,
        ):
            runner.client_for(env, "sample-project")
            for call in oc.call_args_list[1:]:
                self.assertEqual(call.kwargs, {"context": "selected-context", "namespace": "sample-project"})
            self.assertEqual(constructor.call_args.kwargs["host"], "https://pipeline.example.test")

    def test_optimization_generates_all_records_and_submits_only_once(self):
        client = mock_client()
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.object(runner, "ROOT", Path(tmp)),
                patch.object(runner, "read_env", return_value=environment()),
                patch.object(runner, "client_for", return_value=(client, "https://pipeline.example.test")),
                patch.object(runner, "upload") as upload,
            ):
                runner.main([])
            directory = Path(tmp) / "work/runs/test-run"
            self.assertEqual(read_json(directory / "receipt.json")["state"], "SUCCEEDED")
            self.assertIn("platform_spec", read_json(directory / "spec.json"))
            for path in directory.iterdir():
                self.assertNotIn("private-token-do-not-save", path.read_text())
            client.create_experiment.assert_called_once_with(
                name="autorag-audio-sample", namespace="sample-project"
            )
            client.run_pipeline.assert_called_once()
            self.assertFalse(client.run_pipeline.call_args.kwargs["enable_caching"])
            upload.assert_not_called()

    def test_uncertain_submission_retains_receipt_and_blocks_fixed_name_retry(self):
        client = mock_client()
        client.run_pipeline.side_effect = ConnectionError("private connection details")
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.object(runner, "ROOT", Path(tmp)),
                patch.object(runner, "read_env", return_value=environment()),
                patch.object(
                    runner, "client_for", return_value=(client, "https://pipeline.example.test")
                ) as connect,
            ):
                with self.assertRaisesRegex(RuntimeError, "outcome may be uncertain"):
                    runner.main([])
                receipt = read_json(Path(tmp) / "work/runs/test-run/receipt.json")
                self.assertEqual(receipt["state"], "SUBMISSION_UNCERTAIN")
                with self.assertRaisesRegex(ValueError, "Run record already exists"):
                    runner.main([])
                self.assertEqual(connect.call_count, 1)
                client.run_pipeline.assert_called_once()

    def test_incompatible_pipeline_contract_prevents_experiment_and_run_creation(self):
        client = mock_client()
        body = client.get_pipeline_version.return_value.pipeline_spec["pipeline_spec"]
        body["root"]["inputDefinitions"]["parameters"].pop("preset")
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.object(runner, "ROOT", Path(tmp)),
                patch.object(runner, "read_env", return_value=environment()),
                patch.object(runner, "client_for", return_value=(client, "https://pipeline.example.test")),
            ):
                with self.assertRaisesRegex(ValueError, "Unknown pipeline parameters"):
                    runner.main([])
            client.create_experiment.assert_not_called()
            client.run_pipeline.assert_not_called()

    def test_platform_change_between_pin_and_submit_prevents_submission(self):
        client = mock_client()
        original = client.get_pipeline_version.return_value.pipeline_spec
        changed = deepcopy(original)
        changed["platform_spec"] = {"platforms": {"kubernetes": {"changed": True}}}
        client.get_pipeline_version.side_effect = [Mock(pipeline_spec=original), Mock(pipeline_spec=changed)]
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.object(runner, "ROOT", Path(tmp)),
                patch.object(runner, "read_env", return_value=environment()),
                patch.object(runner, "client_for", return_value=(client, "https://pipeline.example.test")),
            ):
                with self.assertRaisesRegex(ValueError, "differs from inspected"):
                    runner.main([])
            client.run_pipeline.assert_not_called()
            self.assertFalse((Path(tmp) / "work/runs/test-run/receipt.json").exists())

    def test_wait_timeout_keeps_run_id_and_does_not_resubmit(self):
        client = mock_client()
        client.wait_for_run_completion.side_effect = TimeoutError("wait expired")
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.object(runner, "ROOT", Path(tmp)),
                patch.object(runner, "read_env", return_value=environment()),
                patch.object(runner, "client_for", return_value=(client, "https://pipeline.example.test")),
            ):
                with self.assertRaisesRegex(RuntimeError, "run may still be active"):
                    runner.main([])
            receipt = read_json(Path(tmp) / "work/runs/test-run/receipt.json")
            self.assertEqual(receipt["run_id"], "run-id")
            self.assertEqual(receipt["state"], "PENDING")
            client.run_pipeline.assert_called_once()

    def test_indexing_uses_selected_pattern_and_reuses_existing_experiment(self):
        client = mock_client("indexing")
        client.list_experiments.return_value.experiments = [
            Mock(display_name="autorag-audio-sample", experiment_id="existing-experiment")
        ]
        with tempfile.TemporaryDirectory() as tmp:
            pattern_path = Path(tmp) / "pattern.json"
            write_json(pattern_path, indexing_pattern())
            env = {
                **environment(),
                "AUTORAG_PATTERN_FILE": str(pattern_path),
                "AUTORAG_COLLECTION_NAME": "new_collection",
            }
            with (
                patch.object(runner, "ROOT", Path(tmp)),
                patch.object(runner, "read_env", return_value=env),
                patch.object(runner, "client_for", return_value=(client, "https://pipeline.example.test")),
                patch.object(runner, "upload") as upload,
            ):
                runner.main(["--kind", "indexing"])
            directory = Path(tmp) / "work/runs/test-run"
            params = read_json(directory / "params.json")
            self.assertEqual(params["collection_name"], "new_collection")
            self.assertEqual(params["input_data_keys"], ["datasets/rag/audio/documents"])
            bound = read_json(directory / "pattern.bound.json")
            self.assertEqual(bound["settings"]["store_binding"]["collection_name"], "new_collection")
            client.create_experiment.assert_not_called()
            upload.assert_not_called()

    def test_upload_mode_cannot_modify_existing_ci_paths_or_separate_buckets(self):
        env = {**environment(), "AUTORAG_UPLOAD_TEST_DATASETS": "true"}
        self.assertNotIn("input_data_keys", runner.configuration(env))
        for extra in (
            {"AUTORAG_INPUT_DATA_KEYS": '["datasets/rag/audio/documents"]'},
            {"TEST_DATA_BUCKET_NAME": "different-bucket"},
        ):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                runner.configuration({**env, **extra})

    def test_local_upload_stages_only_audio_and_benchmark_before_submission(self):
        env = {**environment(), "AUTORAG_UPLOAD_TEST_DATASETS": "true"}
        client = mock_client()
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.object(runner, "ROOT", Path(tmp)),
                patch.object(runner, "read_env", return_value=env),
                patch.object(runner, "client_for", return_value=(client, "https://pipeline.example.test")),
                patch.object(runner, "upload") as upload,
            ):
                runner.main([])
            plan = upload.call_args.args[2]
            self.assertEqual(len(plan), 4)
            self.assertEqual(sum("/audio/" in item["key"] for item in plan), 3)
            self.assertEqual(sum(item["key"].endswith("/benchmark.json") for item in plan), 1)
            params = client.run_pipeline.call_args.kwargs["params"]
            self.assertEqual(params["input_data_keys"], ["autorag-audio/sample-v1/audio/"])
            self.assertEqual(params["test_data_key"], "autorag-audio/sample-v1/benchmark.json")

    def test_upload_dry_run_validates_corpus_without_writes_or_requests(self):
        env = {**environment(), "AUTORAG_UPLOAD_TEST_DATASETS": "true"}
        with (
            patch.object(runner, "read_env", return_value=env),
            patch.object(runner, "write_json") as write,
            patch.object(runner, "client_for") as client,
            patch.object(runner, "upload") as upload,
        ):
            runner.main(["--dry-run"])
            write.assert_not_called()
            client.assert_not_called()
            upload.assert_not_called()


if __name__ == "__main__":
    unittest.main()
