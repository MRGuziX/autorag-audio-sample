# AutoRAG audio sample

Run an audio RAG experiment on OpenShift AI with **one `.env` file and one command**.
The pipeline reads audio from S3, transcribes it with Docling ASR and optimizes RAG patterns.
After selecting a pattern, use the same `.env` to index the full corpus and ask grounded questions.

## Choose your data

The bundled Polish recordings and benchmark are ready at the default paths:

```dotenv
AUTORAG_INPUT_DATA_KEYS=["data/rag/audio/sample/documents"]
AUTORAG_TEST_DATA_KEY=data/rag/audio/sample/benchmark.json
```

To use your own data, drop recordings into `data/rag/audio/users/documents/`, add
`data/rag/audio/users/benchmark.json`, then change both paths in `.env` to those locations.
See the [benchmark example](data/README.md). No preparation command or metadata file is required.

## Configure once

You need an existing RHOAI project, a ready pipeline server with the managed AutoRAG pipelines,
an S3 bucket, and project Connections for S3, MaaS and Milvus/PGVector.
Install [uv](https://docs.astral.sh/uv/) and the OpenShift CLI (`oc`) if using your current login.

```bash
uv sync --frozen
cp -n .env.example .env
```

Fill in `.env`:

| Variable | Value |
| --- | --- |
| `RHOAI_PROJECT_NAME` | Your RHOAI project |
| `RHOAI_KFP_URL` | That project's pipeline API URL; leave blank to discover it using `oc` |
| `INPUT_DATA_BUCKET_NAME` | Bucket to upload the recordings into |
| `INPUT_DATA_SECRET_NAME` | Project's S3 Connection secret name |
| `MAAS_SECRET_NAME` | Project's MaaS Connection secret name |
| `VECTOR_DB_SECRET_NAME` | Project's Milvus/PGVector Connection secret name |
| `AUTORAG_EMBEDDING_MODELS` | MaaS embedding model IDs, as a JSON array or comma-separated list |
| `AUTORAG_GENERATION_MODELS` | MaaS generation model IDs, in the same format |
| `AWS_S3_ENDPOINT`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | Workstation access to the same S3 service, or use your AWS credential chain |

For authentication, use `oc login` in your terminal, or fill `RHOAI_TOKEN` and `RHOAI_KFP_URL` in `.env`.
No need to source the file. It is ignored by Git. Names follow AutoX CI's `.env.rag`; the runner also
accepts `--env-file /path/to/.env.rag`. Explicit shell variables override file values.

The example enables `AUTORAG_UPLOAD_TEST_DATASETS=true`: the runner reads the two dataset paths
locally and uploads to those same keys in S3. Set it to `false` to use objects already in S3.
Change `AUTORAG_INPUT_DATA_KEYS` and `AUTORAG_TEST_DATA_KEY` to switch datasets in either mode.
Metric `answer_correctness`, four patterns and preset `speed` match TC-P-5.
Use fresh paths when replacing uploaded data; conflicting objects are refused.

## Run

Leave `AUTORAG_PIPELINE_PATH` blank to use the managed optimization pipeline. To use a compiled local
pipeline instead, set its path in the same `.env`, for example:

```dotenv
AUTORAG_PIPELINE_PATH=/path/to/documents_rag_optimization_pipeline/pipeline.yaml
```

For indexing, `AUTORAG_INDEXING_PIPELINE_PATH` makes the same choice independently. Relative paths
resolve from the `.env` file's directory. A missing or invalid filled path is an error.

```bash
uv run python scripts/run_experiment.py
```

The command reads and uploads your audio and benchmark, validates the selected pipeline, then
creates or reuses the `autorag-audio-sample` experiment. It submits a uniquely named run and waits
for it. Managed mode discovers and pins an installed version. Local
mode submits an exact snapshot of your YAML, including Kubernetes platform settings, without
replacing the managed pipeline. Execution takes place on OpenShift in both modes.
**You don't create or edit JSON configuration files.** Parameters, full pipeline spec, selected IDs
and the run receipt are saved automatically under `work/runs/<run-name>/` for troubleshooting.
Tokens and Connection credentials are not saved there.

With `DOWNLOAD_ARTIFACTS=true` (enabled in `.env.example`), a successful optimization run downloads the
highest-scoring pattern folder and `starter_kit.zip` to `work/runs/<run-name>/artifacts/`. It uses the AWS endpoint and credentials in
`.env`. The artifact bucket is discovered from the run; set `AWS_S3_BUCKET` if needed.
If KFP omits the storage root, the input bucket is the fallback. Pattern selection uses the mean score
for the run's saved optimization metric. Ties are resolved by pattern name. Other pattern folders
and logs are skipped; indexing runs retain their run-scoped artifact download behavior.

To retry a download without submitting another experiment:

```bash
uv run python scripts/run_experiment.py --download-run <run-name>
```

To check `.env` without connecting or submitting:

```bash
uv run python scripts/run_experiment.py --dry-run
```

A dry run validates local settings and, when selected, the local YAML and parameter contract.
Managed pipeline contracts are checked when connected. Data access, model availability and ASR
compatibility still need a product run. A wait timeout leaves the
run running; check the printed receipt and pipelines UI before submitting another run.

Local YAML uses the container images it references; changing the pipeline source alone does not
install an ASR fix in those images.

## Select a pattern, index and ask

With downloads enabled, the selected pattern's `pattern.json`, notebooks and evaluation files are
saved under `work/runs/<run-name>/artifacts/best-pattern/`, with `starter_kit.zip` beside that folder.
The runner prints the winning name and score and records all ranked scores in the run receipt.
Check transcript coverage through the pipeline UI; transcript artifacts are not downloaded by this option.

Set these two additional values in the **same `.env`**:

```dotenv
AUTORAG_PATTERN_FILE=work/runs/<run-name>/artifacts/best-pattern/pattern.json
AUTORAG_COLLECTION_NAME=audio_sample_001
```

Use a fresh vector collection, then run:

```bash
uv run python scripts/run_experiment.py --kind indexing
```

The runner preserves the selected pattern's model/chunking settings and saves `pattern.bound.json`
in that run's folder. In the product `inference.ipynb`, set `collection_name` to the same collection,
configure its MaaS/database access and ask against the managed index.

For the original Polish corpus, try:

> Na jakiej głębokości pod powierzchnią ziemi znajdował się tron Imperatora termitów?

Expected fact: **45 metrów**, supported by `termites_story.wav`. This is a reference answer,
not an observed result. Verify the retrieved source/excerpt against the recording.

## More options

- [Environment settings and run details](docs/run-on-openshift.md)
- [Use your own recordings or upload the bundled corpus](data/README.md)
- [Prerequisites and ASR packaging](docs/prerequisites.md)
- [Compatibility](docs/compatibility.md), [troubleshooting](docs/troubleshooting.md), [acceptance checklist](docs/validation.md)

The only configuration file is `.env`. Shared implementation lives in `scripts/lib/`.
Optional answer evidence is collected with `scripts/collect_evidence.py` after the run.

This private sample includes three Polish recordings and an 11-question benchmark.
A successful sample pipeline run and grounded answer remain to be recorded.
Public corpus redistribution clearance and listening review remain pending. Original M4A support
depends on the installed product image.
Helper code is Apache-2.0; corpus rights are separate. See [NOTICE](NOTICE) and [data provenance](data/rag/audio/sample/README.md).

## Local checks

```bash
uv sync --frozen --dev
uv run ruff check .
uv run ruff format --check .
uv run python -m unittest discover -s tests
```
