"""Shared data and pipeline contracts; no product RAG implementation lives here."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
OPTIMIZATION_PIPELINE = "documents-rag-optimization-pipeline"
INDEXING_PIPELINE = "documents-indexing-pipeline"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def pipeline_spec_body(spec: dict) -> dict:
    """Read the pipeline body without discarding a KFP package's platform settings."""
    body = spec.get("pipeline_spec", spec)
    require(isinstance(body, dict), "PipelineSpec must be an object")
    return body


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def relative_path(value: str) -> str:
    require(isinstance(value, str) and bool(value), "Expected a nonempty relative path")
    parts = value.split("/")
    require(
        not value.startswith("/") and all(p not in ("", ".", "..") for p in parts) and "\\" not in value,
        f"Unsafe or ambiguous relative path: {value!r}",
    )
    return str(PurePosixPath(value))


def local_path(value: str, root: Path = ROOT) -> Path:
    path = (root / relative_path(value)).resolve()
    require(path.is_relative_to(root.resolve()), f"Path leaves the repository: {value}")
    return path


def non_placeholder(value, name: str) -> None:
    require(
        isinstance(value, str) and bool(value.strip()) and "<" not in value and ">" not in value,
        f"Set {name}; unresolved or empty value: {value!r}",
    )


def validate_config(config: dict) -> dict:
    """Validate the configuration resolved from .env."""
    expected = {
        "bucket",
        "input_data_keys",
        "test_data_key",
        "input_data_secret_name",
        "test_data_secret_name",
        "maas_secret_name",
        "db_secret_name",
        "embedding_models",
        "generation_models",
        "optimization_metric",
        "optimization_max_rag_patterns",
        "preset",
    }
    optional = {"test_data_bucket_name"}
    require(
        isinstance(config, dict) and expected <= set(config) and not set(config) - expected - optional,
        "Unexpected or missing experiment configuration fields",
    )
    for name in expected - {
        "embedding_models",
        "generation_models",
        "optimization_max_rag_patterns",
        "input_data_keys",
    }:
        non_placeholder(config[name], name)
    require("/" not in config["bucket"] and ":" not in config["bucket"], "bucket must be a bucket name")
    if "test_data_bucket_name" in config:
        bucket = config["test_data_bucket_name"]
        non_placeholder(bucket, "test_data_bucket_name")
        require("/" not in bucket and ":" not in bucket, "test_data_bucket_name must be a bucket name")
    for name in ("embedding_models", "generation_models"):
        require(isinstance(config[name], list) and bool(config[name]), f"{name} must be a nonempty list")
        for model in config[name]:
            non_placeholder(model, name)
    require(config["preset"] in ("speed", "balanced"), "preset must be speed or balanced")
    patterns = config["optimization_max_rag_patterns"]
    require(type(patterns) is int and 4 <= patterns <= 10, "optimization_max_rag_patterns must be 4–10")
    if {"input_data_keys", "test_data_key"} & config.keys():
        require({"input_data_keys", "test_data_key"} <= config.keys(), "Set both S3 dataset paths")
        keys = config["input_data_keys"]
        require(
            isinstance(keys, list) and len(keys) == 1,
            "Set one explicit S3 audio directory",
        )
        non_placeholder(keys[0], "input_data_keys")
        require(len(relative_path(keys[0].rstrip("/")).split("/")) >= 2, "Use a dedicated audio directory")
        non_placeholder(config["test_data_key"], "test_data_key")
        relative_path(config["test_data_key"])
        require(
            not config["test_data_key"].startswith(keys[0].rstrip("/") + "/"),
            "Benchmark must be outside the audio directory",
        )
    return config


def validate_questions(rows, allowed_keys: set[str], label: str) -> None:
    require(isinstance(rows, list) and bool(rows), f"{label} must be a nonempty JSON list")
    questions = set()
    for i, row in enumerate(rows):
        require(isinstance(row, dict), f"{label}[{i}] must be an object")
        require(
            set(row) == {"question", "correct_answers", "correct_answer_document_keys"},
            f"{label}[{i}] has unexpected/missing fields",
        )
        question = row["question"]
        non_placeholder(question, f"{label}[{i}].question")
        normalized = " ".join(question.casefold().split())
        require(normalized not in questions, f"Duplicate question in {label}: {question}")
        questions.add(normalized)
        for name in ("correct_answers", "correct_answer_document_keys"):
            values = row[name]
            require(isinstance(values, list) and bool(values), f"{label}[{i}].{name} must be a nonempty list")
            for value in values:
                non_placeholder(value, f"{label}[{i}].{name}")
        require(
            set(row["correct_answer_document_keys"]) <= allowed_keys,
            f"{label}[{i}] refers to a missing audio file: {row['correct_answer_document_keys']}",
        )


def load_sample(
    documents_dir: str = "data/rag/audio/sample/documents",
    benchmark_key: str | None = None,
    root: Path = ROOT,
) -> tuple[list[dict], list]:
    """Read local files at the configured S3 paths; no preparation file needed."""
    audio_dir = local_path(documents_dir.rstrip("/"), root)
    dataset_root = audio_dir.parent
    require(audio_dir.is_dir(), f"Create {audio_dir} and drop your recordings there")
    files = []
    for path in sorted(audio_dir.iterdir()):
        if path.name.startswith("."):
            continue
        require(
            path.is_file() and path.suffix.lower() in {".wav", ".mp3", ".m4a"},
            f"Unsupported audio entry: {path.name}; use WAV, MP3 or M4A files",
        )
        require(path.resolve().is_relative_to(dataset_root), f"Audio symlink leaves dataset: {path.name}")
        require(path.stat().st_size > 0, f"Empty audio file: {path.name}")
        files.append(
            {
                "path": f"{documents_dir.rstrip('/')}/{path.name}",
                "object_key": f"{documents_dir.rstrip('/')}/{path.name}",
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    require(bool(files), f"Drop at least one audio file into {audio_dir}")
    benchmark_path = local_path(benchmark_key, root) if benchmark_key else dataset_root / "benchmark.json"
    require(benchmark_path.is_file(), f"Add your questions and expected answers to {benchmark_path}")
    benchmark = read_json(benchmark_path)
    allowed = {
        key
        for entry in files
        for key in (entry["object_key"], entry["path"], f"documents/{Path(entry['path']).name}")
    }
    validate_questions(benchmark, allowed, "benchmark")
    return files, benchmark


def input_keys(config: dict) -> list[str]:
    return list(config["input_data_keys"])


def render_config_questions(rows: list, config: dict) -> list:
    """Resolve local label source names against either staged or existing S3 audio."""
    directory = input_keys(config)[0].rstrip("/")
    return [
        {
            **row,
            "correct_answer_document_keys": [
                f"{directory}/{PurePosixPath(key).name}" for key in row["correct_answer_document_keys"]
            ],
        }
        for row in rows
    ]


def optimization_params(config: dict) -> dict:
    return {
        **{
            key: config[key]
            for key in (
                "test_data_secret_name",
                "input_data_secret_name",
                "maas_secret_name",
                "db_secret_name",
                "embedding_models",
                "generation_models",
                "optimization_metric",
                "optimization_max_rag_patterns",
                "preset",
            )
        },
        "test_data_bucket_name": config.get("test_data_bucket_name", config["bucket"]),
        "input_data_bucket_name": config["bucket"],
        "input_data_keys": input_keys(config),
        "test_data_key": config["test_data_key"],
    }


def validate_pipeline_params(params: dict, spec: dict, expected_name: str) -> dict:
    """Validate concrete values against an exported KFP v2 PipelineSpec."""
    spec = pipeline_spec_body(spec)
    require(spec.get("pipelineInfo", {}).get("name") == expected_name, f"Expected pipeline {expected_name}")
    definitions = spec.get("root", {}).get("inputDefinitions", {}).get("parameters")
    require(isinstance(definitions, dict) and bool(definitions), "Missing KFP v2 parameter definitions")
    require(isinstance(params, dict), "Parameters must be a JSON object")
    require(
        not set(params) - set(definitions),
        f"Unknown pipeline parameters: {sorted(set(params) - set(definitions))}",
    )
    types = {
        "STRING": lambda v: isinstance(v, str),
        "NUMBER_INTEGER": lambda v: type(v) is int,
        "NUMBER_DOUBLE": lambda v: type(v) in (int, float) and math.isfinite(v),
        "BOOLEAN": lambda v: type(v) is bool,
        "LIST": lambda v: isinstance(v, list),
        "STRUCT": lambda v: isinstance(v, dict),
    }
    for name, definition in definitions.items():
        if name not in params:
            require(
                "defaultValue" in definition or definition.get("isOptional", False),
                f"Missing required pipeline parameter: {name}",
            )
            continue
        value = params[name]
        if value is None:
            require(definition.get("isOptional", False), f"{name} cannot be null")
            continue
        kind = definition.get("parameterType")
        require(kind in types, f"Unsupported KFP type {kind} for {name}")
        require(types[kind](value), f"{name} must have KFP type {kind}")
        require(not re.search(r"<[^>]+>", json.dumps(value)), f"Unresolved placeholder in {name}")
    # Prevent hand-edited requests from widening this sample to an entire bucket.
    if "input_data_keys" in definitions:
        prefixes = params.get("input_data_keys", [])
        require(isinstance(prefixes, list) and 1 <= len(prefixes) <= 10, "Use 1–10 explicit audio prefixes")
        for prefix in prefixes:
            require(isinstance(prefix, str), "Audio prefixes must be strings")
            require(len(relative_path(prefix.rstrip("/")).split("/")) >= 2, "Use a dedicated audio prefix")
    if "embedding_models" in params or "generation_models" in params:
        for name in ("embedding_models", "generation_models"):
            models = params.get(name)
            require(isinstance(models, list) and bool(models), f"{name} must be a nonempty list")
            for model in models:
                non_placeholder(model, name)
    return definitions


def cli(main) -> None:
    """Display expected validation/service failures without dumping response bodies or tokens."""
    try:
        main()
    except (ValueError, KeyError, OSError, RuntimeError) as exc:
        raise SystemExit(f"Error: {exc}") from None
