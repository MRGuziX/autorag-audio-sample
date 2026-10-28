"""Behavior checks for data isolation and managed-pipeline request contracts."""

import copy
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from collect_evidence import main as evidence_main  # noqa: E402
from lib.indexing import prepare  # noqa: E402
from lib.sample import (  # noqa: E402
    INDEXING_PIPELINE,
    OPTIMIZATION_PIPELINE,
    load_sample,
    optimization_params,
    read_json,
    render_config_questions,
    validate_config,
    validate_pipeline_params,
    write_json,
)
from lib.storage import stage, upload_plan  # noqa: E402


def config():
    return {
        "bucket": "sample-bucket",
        "input_data_keys": ["data/rag/audio/sample/documents"],
        "test_data_key": "data/rag/audio/sample/benchmark.json",
        "input_data_secret_name": "audio-data-connection",
        "test_data_secret_name": "audio-data-connection",
        "maas_secret_name": "audio-maas-connection",
        "db_secret_name": "audio-vector-db-connection",
        "embedding_models": ["multilingual-embedding"],
        "generation_models": ["generation"],
        "optimization_metric": "custom:overall_score",
        "optimization_max_rag_patterns": 4,
        "preset": "speed",
    }


def indexing_pattern():
    return {
        "name": "selected-pattern",
        "settings": {
            "store_binding": {"provider_type": "milvus", "collection_name": "optimization_collection"},
            "embedding": {"model_id": "multilingual-embedding", "embedding_params": {}},
            "chunking": {"method": "recursive", "chunk_size": 512, "chunk_overlap": 64},
            "generation": {"language": {"code": "pl"}},
        },
        "indexing": {
            "pipeline_spec": {
                "pipeline_name": INDEXING_PIPELINE,
                "parameters": {
                    "maas_secret_name": "old-maas",
                    "db_secret_name": "old-db",
                    "input_data_secret_name": "old-s3",
                    "input_data_bucket_name": "old-bucket",
                    "input_data_keys": ["old-prefix"],
                    "provider_type": "milvus",
                    "collection_name": "optimization_collection",
                    "embedding_model_id": "multilingual-embedding",
                    "embedding_params": {},
                    "chunking_method": "recursive",
                    "chunk_size": 512,
                    "chunk_overlap": 64,
                    "preset": "speed",
                },
            }
        },
    }


class MemoryS3:
    """Small S3 fake that checks default conditional creation and records mutations."""

    def __init__(self, objects=None):
        self.objects = dict(objects or {})
        self.puts = []

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return self

    def paginate(self, *, Bucket, Prefix):
        return [{"Contents": [{"Key": key} for key in self.objects if key.startswith(Prefix)]}]

    def get_object(self, *, Bucket, Key):
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {"Body": io.BytesIO(self.objects[Key])}

    def put_object(self, **kwargs):
        if kwargs.get("IfNoneMatch") == "*" and kwargs["Key"] in self.objects:
            raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
        self.puts.append(kwargs["Key"])
        self.objects[kwargs["Key"]] = kwargs["Body"].read()


class SampleDataTests(unittest.TestCase):
    def test_existing_s3_paths_render_the_original_audio_test_case(self):
        cfg = {
            **config(),
            "optimization_metric": "answer_correctness",
            "input_data_keys": ["datasets/rag/audio/documents"],
            "test_data_key": "datasets/rag/audio/benchmark_data.json",
        }
        loaded = validate_config(cfg)
        params = optimization_params(loaded)
        self.assertEqual(params["input_data_keys"], ["datasets/rag/audio/documents"])
        self.assertEqual(params["test_data_key"], "datasets/rag/audio/benchmark_data.json")
        self.assertEqual(params["optimization_metric"], "answer_correctness")
        validate_pipeline_params(
            params, read_json(ROOT / "tests/fixtures/optimization.parameters.json"), OPTIMIZATION_PIPELINE
        )
        benchmark = read_json(ROOT / "data/rag/audio/sample/benchmark.json")
        rendered = render_config_questions(benchmark, loaded)
        self.assertEqual(
            rendered[0]["correct_answer_document_keys"],
            ["datasets/rag/audio/documents/" + Path(benchmark[0]["correct_answer_document_keys"][0]).name],
        )
        indexed, _ = prepare(
            indexing_pattern(),
            read_json(ROOT / "tests/fixtures/indexing.parameters.json"),
            loaded,
            "fresh_collection",
        )
        self.assertEqual(indexed["input_data_keys"], params["input_data_keys"])

    def test_existing_s3_overrides_must_be_paired_and_keep_benchmark_outside_corpus(self):
        missing = config()
        missing.pop("test_data_key")
        with self.assertRaisesRegex(ValueError, "missing"):
            validate_config(missing)
        with self.assertRaisesRegex(ValueError, "outside the audio"):
            validate_config(
                {
                    **config(),
                    "input_data_keys": ["datasets/audio/documents"],
                    "test_data_key": "datasets/audio/documents/benchmark.json",
                }
            )

    def test_bundled_corpus_loads_directly_from_directory(self):
        files, benchmark = load_sample()
        self.assertEqual((len(files), len(benchmark)), (3, 11))
        self.assertEqual(
            {entry["object_key"] for entry in files},
            {
                "data/rag/audio/sample/documents/anteater_story.mp3",
                "data/rag/audio/sample/documents/termites_story.wav",
                "data/rag/audio/sample/documents/capybara_story.m4a",
            },
        )

    def test_outside_audio_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "data/rag/audio/users/documents"
            audio.mkdir(parents=True)
            (root / "outside.mp3").write_bytes(b"outside")
            (audio / "link.mp3").symlink_to(root / "outside.mp3")
            with self.assertRaisesRegex(ValueError, "leaves dataset"):
                load_sample("data/rag/audio/users/documents", root=root)

    def test_paths_and_placeholders_fail_before_upload(self):
        with self.assertRaisesRegex(ValueError, "unresolved"):
            validate_config({**config(), "bucket": "<bucket>"})
        for prefix in ("", "bucket-root", "x/../audio", "/x/audio", "x//audio"):
            with self.subTest(prefix=prefix), self.assertRaises(ValueError):
                validate_config({**config(), "input_data_keys": [prefix]})

    def test_upload_allowlist_contains_only_audio_and_benchmark(self):
        plan = upload_plan(config())
        self.assertEqual(len(plan), 4)
        keys = {entry["key"] for entry in plan}
        self.assertEqual(
            keys,
            {
                f"data/rag/audio/sample/{path}"
                for path in (
                    "documents/anteater_story.mp3",
                    "documents/termites_story.wav",
                    "documents/capybara_story.m4a",
                    "benchmark.json",
                )
            },
        )
        rendered = json.loads(plan[-1]["body"])
        self.assertTrue(all(key in keys for row in rendered for key in row["correct_answer_document_keys"]))
        original = read_json(ROOT / "data/rag/audio/sample/benchmark.json")
        self.assertTrue(
            original[0]["correct_answer_document_keys"][0].startswith("data/rag/audio/sample/documents/")
        )

    def test_custom_corpus_runs_with_audio_and_benchmark_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = root / "data/rag/audio/users"
            (directory / "documents").mkdir(parents=True)
            content = b"example bytes for file checks; decoding happens on OpenShift"
            clip = directory / "documents/briefing.wav"
            clip.write_bytes(content)
            (directory / "documents/.DS_Store").write_bytes(b"ignored")
            questions = [
                {
                    "question": "What is the maintenance window?",
                    "correct_answers": ["22:00"],
                    "correct_answer_document_keys": ["documents/briefing.wav"],
                }
            ]
            write_json(directory / "benchmark.json", questions)
            files, benchmark = load_sample("data/rag/audio/users/documents", root=root)
            self.assertEqual((len(files), len(benchmark)), (1, 1))
            self.assertEqual(files[0]["sha256"], hashlib.sha256(content).hexdigest())
            self.assertEqual(
                set(directory.iterdir()), {directory / "documents", directory / "benchmark.json"}
            )
            self.assertEqual(
                render_config_questions(benchmark, {"input_data_keys": ["custom/v1/documents"]})[0][
                    "correct_answer_document_keys"
                ],
                ["custom/v1/documents/briefing.wav"],
            )
            # Replacing a recording needs no metadata regeneration.
            clip.write_bytes(b"updated recording")
            updated, _ = load_sample("data/rag/audio/users/documents", root=root)
            self.assertNotEqual(updated[0]["sha256"], files[0]["sha256"])

    def test_missing_benchmark_empty_audio_and_bad_references_fail_clearly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = root / "data/rag/audio/users"
            audio = directory / "documents"
            audio.mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "at least one"):
                load_sample("data/rag/audio/users/documents", root=root)
            clip = audio / "briefing.wav"
            clip.write_bytes(b"")
            with self.assertRaisesRegex(ValueError, "Empty audio"):
                load_sample("data/rag/audio/users/documents", root=root)
            clip.write_bytes(b"audio")
            with self.assertRaisesRegex(ValueError, "questions and expected answers"):
                load_sample("data/rag/audio/users/documents", root=root)
            write_json(
                directory / "benchmark.json",
                [
                    {
                        "question": "When?",
                        "correct_answers": ["22:00"],
                        "correct_answer_document_keys": ["documents/missing.wav"],
                    }
                ],
            )
            with self.assertRaisesRegex(ValueError, "missing audio file"):
                load_sample("data/rag/audio/users/documents", root=root)


class UploadTests(unittest.TestCase):
    @staticmethod
    def plan():
        return [
            {
                "key": "sample/v1/documents/a.wav",
                "body": b"audio",
                "bytes": 5,
                "sha256": hashlib.sha256(b"audio").hexdigest(),
            },
            {
                "key": "sample/v1/benchmark.json",
                "body": b"benchmark",
                "bytes": 9,
                "sha256": hashlib.sha256(b"benchmark").hexdigest(),
            },
        ]

    def test_upload_then_rerun_is_verified_and_idempotent(self):
        client = MemoryS3()
        stage(client, "bucket", "sample/v1/documents", self.plan())
        self.assertEqual(len(client.puts), 2)
        stage(client, "bucket", "sample/v1/documents", self.plan())
        self.assertEqual(len(client.puts), 2)

    def test_conflict_preflight_performs_no_partial_writes(self):
        client = MemoryS3({"sample/v1/benchmark.json": b"old benchmark"})
        with self.assertRaisesRegex(ValueError, "Different object"):
            stage(client, "bucket", "sample/v1/documents", self.plan())
        self.assertEqual(client.puts, [])

    def test_reference_text_left_in_prefix_blocks_upload(self):
        client = MemoryS3({"sample/v1/documents/transcript.txt": b"leaked reference"})
        with self.assertRaisesRegex(ValueError, "Unexpected objects"):
            stage(client, "bucket", "sample/v1/documents", self.plan())
        self.assertEqual(client.puts, [])


class PipelineContractTests(unittest.TestCase):
    def setUp(self):
        self.index_spec = read_json(ROOT / "tests/fixtures/indexing.parameters.json")
        self.opt_spec = read_json(ROOT / "tests/fixtures/optimization.parameters.json")

    def test_rendered_request_matches_current_optimization_contract(self):
        params = optimization_params(config())
        validate_pipeline_params(params, self.opt_spec, OPTIMIZATION_PIPELINE)
        for key, value in (("input_data_key", "old/path"), ("ogx_secret_name", "old-secret")):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "Unknown"):
                validate_pipeline_params({**params, key: value}, self.opt_spec, OPTIMIZATION_PIPELINE)

    def test_boolean_integer_and_missing_required_values_fail(self):
        params = optimization_params(config())
        with self.assertRaisesRegex(ValueError, "NUMBER_INTEGER"):
            validate_pipeline_params(
                {**params, "optimization_max_rag_patterns": True}, self.opt_spec, OPTIMIZATION_PIPELINE
            )
        params.pop("maas_secret_name")
        with self.assertRaisesRegex(ValueError, "Missing required"):
            validate_pipeline_params(params, self.opt_spec, OPTIMIZATION_PIPELINE)

    def test_hand_edited_bucket_wide_requests_are_rejected(self):
        for prefixes in ([], [""], ["/"], ["audio/"]):
            with self.subTest(prefixes=prefixes), self.assertRaises(ValueError):
                validate_pipeline_params(
                    {**optimization_params(config()), "input_data_keys": prefixes},
                    self.opt_spec,
                    OPTIMIZATION_PIPELINE,
                )

    def test_indexing_preserves_pattern_and_rebinds_collection(self):
        pattern = indexing_pattern()
        untouched = copy.deepcopy(pattern)
        params, result = prepare(pattern, self.index_spec, config(), "new_collection")
        self.assertEqual(pattern, untouched)
        self.assertNotIn("provider_type", params)
        self.assertEqual(params["chunk_size"], 512)
        self.assertEqual(params["chunk_overlap"], 64)
        self.assertEqual(params["ocr_lang"], "pl")
        self.assertEqual(result["pattern"]["settings"]["store_binding"]["collection_name"], "new_collection")

    def test_unknown_indexing_fields_and_conflicting_settings_fail(self):
        pattern = indexing_pattern()
        pattern["indexing"]["pipeline_spec"]["parameters"]["new_unhandled_field"] = "x"
        with self.assertRaisesRegex(ValueError, "Unknown pipeline"):
            prepare(pattern, self.index_spec, config(), "new_collection")
        pattern = indexing_pattern()
        pattern["indexing"]["pipeline_spec"]["parameters"]["chunk_size"] = 2048
        with self.assertRaisesRegex(ValueError, "disagrees"):
            prepare(pattern, self.index_spec, config(), "new_collection")

    def test_stale_indexing_spec_cannot_silently_drop_preset(self):
        stale_spec = copy.deepcopy(self.index_spec)
        stale_spec["root"]["inputDefinitions"]["parameters"].pop("preset")
        with self.assertRaisesRegex(ValueError, "Unknown pipeline parameters.*preset"):
            prepare(indexing_pattern(), stale_spec, config(), "new_collection")


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        for name, value in (("read_env", {}), ("configuration", config())):
            patcher = patch("collect_evidence." + name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_pending_answers_are_not_counted_as_reviewed(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            worksheet, output = (
                directory / "answers.json",
                directory / "evidence.json",
            )
            argv = [
                "collect_evidence.py",
                "--answer-template",
                str(worksheet),
                "--output",
                str(output),
            ]
            with patch.object(sys, "argv", argv):
                evidence_main()
            self.assertEqual(read_json(output)["benchmark_answers"]["reviewed"], 0)
            argv = [
                "collect_evidence.py",
                "--answers",
                str(worksheet),
                "--output",
                str(output),
            ]
            with patch.object(sys, "argv", argv), self.assertRaisesRegex(ValueError, "must be reviewed"):
                evidence_main()

    def test_reviewed_answer_requires_expected_source_and_excerpt(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            worksheet, output = (
                directory / "answers.json",
                directory / "evidence.json",
            )
            benchmark = read_json(ROOT / "data/rag/audio/sample/benchmark.json")
            answers = [
                {
                    "question": row["question"],
                    "answer": "Observed test answer",
                    "review_status": "reviewed",
                    "factual_pass": True,
                    "source_pass": True,
                    "source_keys": ["wrong/audio.wav"],
                    "supporting_excerpt": "Observed test excerpt",
                }
                for row in benchmark
            ]
            write_json(worksheet, answers)
            argv = [
                "collect_evidence.py",
                "--answers",
                str(worksheet),
                "--output",
                str(output),
            ]
            with patch.object(sys, "argv", argv), self.assertRaisesRegex(ValueError, "expected audio"):
                evidence_main()

    def test_answer_template_does_not_overwrite_existing_reviews(self):
        with tempfile.TemporaryDirectory() as tmp:
            worksheet = Path(tmp) / "answers.json"
            worksheet.write_text("existing reviewed answers")
            argv = ["collect_evidence.py", "--answer-template", str(worksheet)]
            with patch.object(sys, "argv", argv), self.assertRaisesRegex(ValueError, "worksheet exists"):
                evidence_main()
            self.assertEqual(worksheet.read_text(), "existing reviewed answers")


if __name__ == "__main__":
    unittest.main()
