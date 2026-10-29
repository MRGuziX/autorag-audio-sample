"""Run-scoped downloads, local path handling and download-only recovery."""

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_experiment as runner  # noqa: E402
from lib.artifacts import (  # noqa: E402
    artifact_location,
    download_objects,
    download_run_artifacts,
    match_starter_kit,
    select_best_pattern,
)
from lib.sample import read_json, write_json  # noqa: E402
from lib.storage import s3_client  # noqa: E402
from test_env_runner import environment, mock_client  # noqa: E402


def product_zip(name):
    stream = io.BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr("starter_kit/README.md", f"# Agentic RAG Starter Kit: `{name}`\n")
    return stream.getvalue()


class ArtifactTests(unittest.TestCase):
    def test_download_refreshes_timeout_receipt_and_never_resubmits(self):
        for state in ("SUCCEEDED", "RUNNING", "FAILED"):
            for legacy in (False, True):
                with self.subTest(state=state, legacy=legacy), tempfile.TemporaryDirectory() as tmp:
                    directory = Path(tmp) / "work/runs/timed-out"
                    receipt = {"state": "PENDING", "run_id": "run-id"}
                    target = {"namespace": "project", "endpoint": "https://saved-kfp.test"}
                    if legacy:
                        write_json(directory / "target.json", target)
                    else:
                        receipt.update(target)
                    write_json(directory / "receipt.json", receipt)
                    client = Mock()
                    client.get_run.return_value.state = state
                    with (
                        patch.object(runner, "ROOT", Path(tmp)),
                        patch.object(runner, "read_env", return_value=environment()),
                        patch.object(
                            runner, "client_for", return_value=(client, target["endpoint"])
                        ) as connect,
                        patch.object(runner, "download_run_artifacts") as download,
                    ):
                        if state == "SUCCEEDED":
                            runner.main(["--download-run", "timed-out"])
                            download.assert_called_once_with(client, environment(), directory)
                        else:
                            with self.assertRaisesRegex(ValueError, f"Run state is {state}"):
                                runner.main(["--download-run", "timed-out"])
                            download.assert_not_called()
                    self.assertEqual(read_json(directory / "receipt.json")["state"], state)
                    self.assertEqual(connect.call_args.args[1], "project")
                    self.assertEqual(connect.call_args.args[0]["RHOAI_KFP_URL"], target["endpoint"])
                    client.run_pipeline.assert_not_called()

    def test_download_without_run_id_does_not_attempt_recovery_or_submission(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "work/runs/uncertain"
            write_json(directory / "receipt.json", {"state": "SUBMISSION_UNCERTAIN", "run_id": None})
            with (
                patch.object(runner, "ROOT", Path(tmp)),
                patch.object(runner, "read_env", return_value=environment()),
                patch.object(runner, "client_for") as connect,
            ):
                with self.assertRaisesRegex(ValueError, "No run ID"):
                    runner.main(["--download-run", "uncertain"])
            connect.assert_not_called()

    def test_starter_kit_selects_a_tied_winner_and_rejects_other_or_invalid_kits(self):
        storage, objects = self.scored_storage({"Pattern3": 0.9, "Pattern2": 0.9, "Pattern1": 0.4})
        best = select_best_pattern(storage, "bucket", list(objects), "answer_correctness")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "starter_kit.zip"
            path.write_bytes(product_zip("Pattern3"))
            self.assertEqual(match_starter_kit(best, path)["name"], "Pattern3")
            for name in ("Pattern1", "Unknown"):
                path.write_bytes(product_zip(name))
                with self.assertRaisesRegex(ValueError, "highest-scoring"):
                    match_starter_kit(best, path)
            path.write_bytes(b"invalid zip")
            with self.assertRaisesRegex(ValueError, "Cannot identify"):
                match_starter_kit(best, path)

    def test_scores_from_different_evaluators_are_not_ranked_together(self):
        storage, objects = self.scored_storage({"Pattern1": 0.4, "Pattern2": 0.8})
        key = "pipeline/run-id/task/rag_patterns/Pattern2/pattern.json"
        pattern = json.loads(objects[key])
        pattern["evaluation"]["metrics"][0]["evaluator"] = "other"
        objects[key] = json.dumps(pattern).encode()
        with self.assertRaisesRegex(ValueError, "different evaluators"):
            select_best_pattern(storage, "bucket", list(objects), "answer_correctness")
        best = select_best_pattern(storage, "bucket", list(objects), "unitxt:answer_correctness")
        self.assertEqual(best["name"], "Pattern1")

    def test_download_uses_kit_tie_winner_and_handles_missing_leaderboard(self):
        for leaderboard in (True, False):
            with self.subTest(leaderboard=leaderboard), tempfile.TemporaryDirectory() as tmp:
                directory = Path(tmp)
                storage, objects = self.scored_storage({"Pattern3": 0.9, "Pattern2": 0.9})
                if not leaderboard:
                    objects.pop("pipeline/run-id/task/leaderboard")
                storage.get_paginator.return_value.paginate.return_value = [
                    {"Contents": [{"Key": key} for key in objects]}
                ]
                write_json(
                    directory / "receipt.json",
                    {
                        "state": "SUCCEEDED",
                        "kind": "optimization",
                        "pipeline_name": "pipeline",
                        "run_id": "run-id",
                    },
                )
                write_json(directory / "params.json", {"optimization_metric": "answer_correctness"})
                client = Mock()
                client.get_run.return_value = SimpleNamespace(runtime_config=None, pipeline_spec={})
                with patch("lib.artifacts.s3_client", return_value=storage):
                    download_run_artifacts(client, {"INPUT_DATA_BUCKET_NAME": "bucket"}, directory)
                pattern = read_json(directory / "artifacts/best-pattern/pattern.json")
                self.assertEqual(pattern["name"], "Pattern3")
                self.assertEqual((directory / "artifacts/leaderboard.html").exists(), leaderboard)
                receipt = read_json(directory / "receipt.json")
                self.assertEqual(receipt["artifact_download"]["state"], "SUCCEEDED")
                self.assertEqual(receipt["artifact_download"]["best_pattern"]["name"], pattern["name"])

    def test_mismatched_kit_fails_download_without_changing_pipeline_success(self):
        storage, objects = self.scored_storage({"Pattern1": 0.2, "Pattern2": 0.8})
        objects["pipeline/run-id/task/starter_kit/starter_kit.zip"] = product_zip("Pattern1")
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            write_json(
                directory / "receipt.json",
                {
                    "state": "SUCCEEDED",
                    "kind": "optimization",
                    "pipeline_name": "pipeline",
                    "run_id": "run-id",
                },
            )
            write_json(directory / "params.json", {"optimization_metric": "answer_correctness"})
            client = Mock()
            client.get_run.return_value = SimpleNamespace(runtime_config=None, pipeline_spec={})
            with patch("lib.artifacts.s3_client", return_value=storage):
                with self.assertRaisesRegex(RuntimeError, "highest-scoring"):
                    download_run_artifacts(client, {"INPUT_DATA_BUCKET_NAME": "bucket"}, directory)
            receipt = read_json(directory / "receipt.json")
            self.assertEqual(receipt["state"], "SUCCEEDED")
            self.assertEqual(receipt["artifact_download"]["state"], "FAILED")
            self.assertFalse((directory / "artifacts/best-pattern").exists())

    def scored_storage(self, scores):
        storage = Mock()
        objects = {}
        for name, score in scores.items():
            key = f"pipeline/run-id/task/rag_patterns/{name}/pattern.json"
            objects[key] = json.dumps(
                {
                    "name": name,
                    "evaluation": {
                        "metrics": [
                            {
                                "name": "answer_correctness",
                                "evaluator": "unitxt",
                                "optimization_metric": True,
                                "scores": {"mean": score},
                            },
                            {"name": "faithfulness", "evaluator": "unitxt", "scores": {"mean": 1.0}},
                        ]
                    },
                }
            ).encode()
            objects[key.replace("pattern.json", "inference.ipynb")] = b"notebook"
        winner = max(
            (name for name, score in scores.items() if score is not None and score == score),
            key=lambda name: scores[name],
            default="Pattern1",
        )
        objects["pipeline/run-id/task/starter_kit/starter_kit.zip"] = product_zip(winner)
        objects["pipeline/run-id/task/leaderboard"] = b"<html>Product leaderboard</html>"
        objects["pipeline/run-id/task/executor-logs"] = b"logs"
        storage.get_object.side_effect = lambda **kw: {"Body": io.BytesIO(objects[kw["Key"]])}
        storage.get_paginator.return_value.paginate.return_value = [
            {"Contents": [{"Key": key} for key in objects]}
        ]
        storage.download_file.side_effect = lambda bucket, key, path: Path(path).write_bytes(objects[key])
        return storage, objects

    def test_best_pattern_uses_optimization_metric_with_stable_ties(self):
        storage, objects = self.scored_storage({"Pattern3": 0.9, "Pattern2": 0.9, "Pattern1": 0.4})
        best = select_best_pattern(storage, "bucket", list(objects), "answer_correctness")
        self.assertEqual(best["name"], "Pattern2")
        self.assertEqual(best["score"], 0.9)
        self.assertEqual([row["name"] for row in best["rankings"]], ["Pattern2", "Pattern3", "Pattern1"])

    def test_missing_scores_are_skipped_and_unrankable_run_fails(self):
        storage, objects = self.scored_storage({"Pattern1": None, "Pattern2": 0.0, "Pattern3": float("nan")})
        self.assertEqual(
            select_best_pattern(storage, "bucket", list(objects), "answer_correctness")["name"], "Pattern2"
        )
        with self.assertRaisesRegex(ValueError, "No patterns"):
            select_best_pattern(storage, "bucket", list(objects), "unavailable_metric")
        with self.assertRaisesRegex(ValueError, "starter_kit.zip"):
            select_best_pattern(
                storage, "bucket", [key for key in objects if not key.endswith(".zip")], "answer_correctness"
            )

    def test_evaluator_collision_requires_unambiguous_metric(self):
        storage = Mock()
        payload = {
            "evaluation": {
                "metrics": [
                    {"name": "faithfulness", "evaluator": "unitxt", "scores": {"mean": 0.2}},
                    {"name": "faithfulness", "evaluator": "ragas", "scores": {"mean": 0.8}},
                ]
            }
        }
        storage.get_object.side_effect = lambda **kw: {"Body": io.BytesIO(json.dumps(payload).encode())}
        keys = ["pipeline/run/rag_patterns/Pattern1/pattern.json", "pipeline/run/starter_kit.zip"]
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            select_best_pattern(storage, "bucket", keys, "faithfulness")
        best = select_best_pattern(storage, "bucket", keys, "ragas:faithfulness")
        self.assertEqual(best["evaluator"], "ragas")
        self.assertEqual(best["score"], 0.8)

    def test_optimization_downloads_only_winning_pattern_and_product_zip(self):
        storage, _ = self.scored_storage({"Pattern1": 0.2, "Pattern2": 0.8})
        client = Mock()
        client.get_run.return_value = SimpleNamespace(
            state="SUCCEEDED", runtime_config=None, pipeline_spec={}
        )
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            write_json(
                directory / "receipt.json",
                {
                    "state": "SUCCEEDED",
                    "kind": "optimization",
                    "run_id": "run-id",
                    "pipeline_name": "pipeline",
                },
            )
            write_json(directory / "params.json", {"optimization_metric": "answer_correctness"})
            with patch("lib.artifacts.s3_client", return_value=storage):
                download_run_artifacts(
                    client,
                    {"INPUT_DATA_BUCKET_NAME": "bucket", "AUTORAG_OPTIMIZATION_METRIC": "faithfulness"},
                    directory,
                )
            downloaded = {
                str(path.relative_to(directory / "artifacts"))
                for path in (directory / "artifacts").rglob("*")
                if path.is_file()
            }
            self.assertEqual(
                downloaded,
                {
                    "best-pattern/pattern.json",
                    "best-pattern/inference.ipynb",
                    "starter_kit.zip",
                    "leaderboard.html",
                },
            )
            self.assertEqual(read_json(directory / "artifacts/best-pattern/pattern.json")["name"], "Pattern2")
            receipt = read_json(directory / "receipt.json")
            self.assertEqual(receipt["artifact_download"]["best_pattern"]["score"], 0.8)
            self.assertEqual(receipt["artifact_download"]["files"], 4)
        self.assertTrue(all("Pattern1" not in call.args[1] for call in storage.download_file.call_args_list))

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
        run = SimpleNamespace(state="SUCCEEDED", runtime_config=None, pipeline_spec={})
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
            client.get_run.return_value = SimpleNamespace(
                state="SUCCEEDED", runtime_config=None, pipeline_spec={}
            )
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
