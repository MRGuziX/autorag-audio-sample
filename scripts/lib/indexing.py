"""Bind a selected product pattern to managed full-corpus indexing."""

import copy

from lib.sample import INDEXING_PIPELINE, input_keys, non_placeholder, require, validate_pipeline_params


def validate_pattern(pattern: dict, preset: str) -> dict:
    """Check the product blueprint without needing an installed pipeline."""
    require(isinstance(pattern, dict), "Pattern must be a JSON object")
    try:
        return _validated_pattern(pattern, preset)
    except (KeyError, TypeError, AttributeError):
        raise ValueError("Invalid pattern: expected settings and an indexing pipeline blueprint") from None


def _validated_pattern(pattern: dict, preset: str) -> dict:
    settings = pattern["settings"]
    provider = settings["store_binding"]["provider_type"]
    require(
        provider in {"milvus", "milvus-remote", "pgvector", "pgvector-remote"},
        "Use a Milvus or PGVector pattern",
    )
    blueprint = pattern["indexing"]["pipeline_spec"]
    require(blueprint["pipeline_name"] == INDEXING_PIPELINE, "Unexpected indexing pipeline in pattern")
    params = copy.deepcopy(blueprint["parameters"])
    require(isinstance(params, dict), "Pattern indexing parameters must be an object")
    if "provider_type" in params:
        require(params["provider_type"] == provider, "Pattern provider metadata mismatch")
    expected_settings = {
        "embedding_model_id": settings["embedding"]["model_id"],
        "embedding_params": settings["embedding"]["embedding_params"],
        "chunking_method": settings["chunking"]["method"],
        "chunk_size": settings["chunking"]["chunk_size"],
        "chunk_overlap": settings["chunking"]["chunk_overlap"],
    }
    for key, value in expected_settings.items():
        require(params.get(key) == value, f"Pattern blueprint disagrees with selected settings: {key}")
    require(params.get("preset") == preset, "Config preset differs from optimization pattern preset")
    return params


def prepare(pattern: dict, spec: dict, config: dict, collection: str) -> dict:
    non_placeholder(collection, "collection name")
    params = validate_pattern(pattern, config["preset"])
    settings = pattern["settings"]
    definitions = spec.get("pipeline_spec", spec)["root"]["inputDefinitions"]["parameters"]
    if "provider_type" not in definitions:
        params.pop("provider_type", None)
    params.update(
        {
            "maas_secret_name": config["maas_secret_name"],
            "db_secret_name": config["db_secret_name"],
            "input_data_secret_name": config["input_data_secret_name"],
            "input_data_bucket_name": config["bucket"],
            "input_data_keys": input_keys(config),
            "collection_name": collection,
        }
    )
    # Preserve the optimization language setting when supported by this pipeline.
    language = settings.get("generation", {}).get("language", {}).get("code")
    if "ocr_lang" in definitions and language and "ocr_lang" not in params:
        params["ocr_lang"] = language
    validate_pipeline_params(params, spec, INDEXING_PIPELINE)
    return params
