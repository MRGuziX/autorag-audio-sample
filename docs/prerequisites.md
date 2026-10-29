# Prerequisites

## Project and services

- A RHOAI project with a ready Data Science Pipelines Application and access to the managed
  `documents-rag-optimization-pipeline` and `documents-indexing-pipeline` versions.
- Permission to read pipeline versions, submit to an existing experiment, read run artifacts and
  use the project Connections. Pipeline pods need access to the same storage/model/database services.
- S3-compatible data storage and pipeline artifact storage. They can be different buckets/services.
- A MaaS service with compatible embedding and generation models. Polish clips require suitable
  multilingual models. Check model availability, context limits and embedding dimensions.
- One supported Milvus or PGVector database. Use a separate sample collection, and confirm the
  database Connection secret selects the same backend as the selected pattern.
- Sufficient CPU/memory, namespace quota and image-pull access for the installed pipeline. The
  inspected local pipeline source requests up to 4 CPUs/16 GiB for optimization extraction; actual
  defaults and limits must be checked on the selected installed version.

## Connections and credentials

The current source uses these secret keys. Validate them against your installed pipeline version:

| Connection | Kubernetes secret keys |
| --- | --- |
| Input and benchmark S3 | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_ENDPOINT`, optional `AWS_DEFAULT_REGION` |
| MaaS | `MAAS_BASE_URL`, `MAAS_API_KEY` |
| Milvus | `MILVUS_URI`, optional `MILVUS_TOKEN`, optional `MILVUS_CA_CERT` |
| PGVector | `PGVECTOR_HOST`, `PGVECTOR_PORT`, `PGVECTOR_DB`, `PGVECTOR_USER`, `PGVECTOR_PASSWORD`, optional `PGVECTOR_CA_CERT` |

Use the Kubernetes secret names in `.env`, which can differ from the Connections' display names.
Existing audio and benchmark data may use separate buckets and Connections. Leave the `TEST_DATA_*`
values blank to inherit the input settings. Local uploads require one bucket and Connection for
both. Secrets contain credentials; the pipeline arguments contain their names only.

Workstation S3 access is needed when `AUTORAG_UPLOAD_TEST_DATASETS=true` or
`DOWNLOAD_ARTIFACTS=true`, and for explicit `--download-run` retries. Fill
`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`, optional `AWS_SESSION_TOKEN`, `AWS_S3_ENDPOINT`
and `AWS_DEFAULT_REGION` in `.env`, or use the workstation's normal boto3 credential chain.
An exported `AWS_CA_BUNDLE` can supply a custom storage CA. Existing-S3 experiments with downloads
disabled need no workstation S3 credentials because the pipeline reads its project Connections. Downloads require
read/list access to the artifact bucket; uploads additionally require access to the input bucket.

The normal runner reads `RHOAI_KFP_URL`, optional `RHOAI_TOKEN` and optional `KFP_CA_CERT` from `.env`.
Without a token it reuses `oc login`; without an endpoint it discovers the project's DSPA route.
With both token and endpoint set, the OpenShift CLI is not required. Use credentials obtained through
your cluster's supported login flow. Never paste token values into issues, receipts or committed files.

## Audio and ASR

The product extraction image must supply its supported Docling ASR backend, ffmpeg/decoder
dependencies and a complete locally readable model. Both optimization and indexing need this.
The inspected source uses the approved HF-format Whisper tiny model through `HF_MODEL_DIR`;
it must not fall back to downloading `tiny.pt` at runtime. HF Transformers weights and native
OpenAI `.pt` checkpoints are different formats.

The inspected adapter runs ASR on CPU. This sample does not request a GPU or expose an ASR
model-size selector. Historical turbo/GPU recommendations are not evidence of the installed
implementation. Confirm the actual backend/model, effective model path, image/modelcar digests,
Docling/Transformers/ffmpeg versions, resource usage and original-format decode results.

You do not need ffmpeg/ffprobe on your workstation to run this starter. Audio decoding happens
in the pipeline image. Local decoding, if you investigate a file separately, does not establish
support in the product container.

## Disconnected environments

No disconnected run has been validated for this repository. To establish ASR local-only behavior,
test the actual product image with complete read-only local weights and external model-host access
blocked, while allowing required internal S3/MaaS/database/pipeline/DNS connections and writable
temporary workspace. Missing weights must produce a clear error without a network fallback.

A fully air-gapped walkthrough also needs mirrored product/model images, offline Python
dependencies and reachable internal services. Do not infer that broader support from a local-only
ASR test. Keep separate results in the validation record.
