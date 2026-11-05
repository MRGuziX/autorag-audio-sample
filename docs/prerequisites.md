# Prerequisites

These services are shared by the [UI walkthrough](run-via-ui.md) and
[code walkthrough](run-via-code.md).

## Create or select a project

1. Sign in to the OpenShift AI dashboard and create a project, or select an existing one.
   You need permission to manage its Connections and submit pipeline runs.
2. Configure the project's pipeline server and S3 artifact storage, then wait for it to become ready.
3. When using managed pipelines, confirm that `documents-rag-optimization-pipeline` and
   `documents-indexing-pipeline` are available in that project. The code walkthrough can also
   submit compatible compiled local packages.
4. Create the storage, MaaS and database Connections in this same project.

If you create a project through the OpenShift CLI instead, register it with the dashboard:

```bash
oc new-project my-rag-project
oc label namespace my-rag-project opendatahub.io/dashboard=true --overwrite
```

Replace `my-rag-project` with your chosen project name. For an existing project, select it in
the dashboard or with `oc project my-rag-project`, then complete the pipeline and Connection setup.

## Project and services

- A RHOAI project with a ready Data Science Pipelines Application and access to the managed
  `documents-rag-optimization-pipeline` and `documents-indexing-pipeline` versions.
- Permission to read pipeline versions, submit to an existing experiment, read run artifacts and
  use the project Connections. Pipeline pods need access to the same storage/model/database services.
- S3-compatible data storage and pipeline artifact storage. They can be different buckets/services.
- A MaaS service with compatible embedding and generation models for English, or the language of
  your own recordings. Check model availability, context limits and embedding dimensions.
- One supported Milvus, PGVector or Neo4j database. Use a separate sample collection, and confirm the
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
| Neo4j | `NEO4J_URI`, `NEO4J_PASSWORD`, optional `NEO4J_USERNAME` (default `neo4j`), optional `NEO4J_DATABASE` (default `neo4j`), optional `NEO4J_CA_CERT` (inline PEM) |

In the selected project's Connections page, create S3 storage, MaaS and database Connections
with the fields above. The dashboard stores their credentials as Kubernetes secrets.
You can also add a secret from a local manifest:

```bash
oc create -n my-rag-project -f /path/to/connection-secret.yaml
```

The manifest must contain the keys for one Connection from the table above. Keep credential
manifests outside version control. Creating a secret this way requires the registration described
[below](#make-existing-secrets-visible-in-the-ui) before using it through the UI.

For the code walkthrough, use the Kubernetes secret names in `.env`; these can differ from the
Connections' display names. Set `VECTOR_DB_SECRET_NAME` to the chosen database secret for both
optimization and indexing. The pipeline detects the backend from its keys.

For Neo4j, the database needs the APOC procedures used by graph extraction, and MaaS must serve
the selected generation model as well as the embedding
model. Indexing reuses `foundation_model_id`, `foundation_model_params` and `graph_extraction_config`
from the optimized pattern to rebuild its knowledge graph.

Secrets contain credentials; pipeline arguments contain their names only. Existing audio and
benchmark data may use separate buckets and Connections. Code-based local uploads require the
same bucket and Connection for both; leave `TEST_DATA_*` blank to inherit the input settings.

## Make existing secrets visible in the UI

A Kubernetes secret also needs dashboard Connection metadata to appear in the project's
Connections list. Check its required fields before registering it. For an existing PGVector
secret named `pgvector`, for example:

```bash
oc label secret pgvector -n my-rag-project opendatahub.io/dashboard=true --overwrite
oc annotate secret pgvector -n my-rag-project \
  openshift.io/display-name=pgvector \
  opendatahub.io/connection-type=vector-db \
  opendatahub.io/vector-db-provider=pgvector --overwrite
```

For Milvus, use your Milvus secret name and set the provider annotation to `milvus`.
For Neo4j, use `opendatahub.io/connection-type=database` and
`opendatahub.io/database-provider=neo4j`. These commands update metadata on an existing secret;
the Connection still needs valid credentials and a reachable database.

For S3 and MaaS, create the Connections through the dashboard's corresponding forms.
Refresh the AutoRAG page and confirm that the Connections appear in the storage, model and
database selectors for the selected project.

## Code authentication and workstation access

Copy `.env.example` to `.env` and fill in the values listed in the
[code walkthrough](run-via-code.md#create-and-fill-env), including the project, Connection secret
names, bucket and MaaS model IDs.

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
