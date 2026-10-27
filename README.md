# AutoRAG audio sample

Run an audio RAG experiment on OpenShift AI with **one `.env` file and one command**.
The pipeline reads audio from S3, transcribes it with Docling ASR and optimizes RAG patterns.
After selecting a pattern, use the same `.env` to index the full corpus and ask grounded questions.

## Configure once

You need an existing RHOAI project, a ready pipeline server with the managed AutoRAG pipelines,
S3 data, and project Connections for S3, MaaS and Milvus/PGVector.
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
| `INPUT_DATA_BUCKET_NAME` | Bucket containing the recordings |
| `INPUT_DATA_SECRET_NAME` | Project's S3 Connection secret name |
| `MAAS_SECRET_NAME` | Project's MaaS Connection secret name |
| `VECTOR_DB_SECRET_NAME` | Project's Milvus/PGVector Connection secret name |
| `AUTORAG_EMBEDDING_MODELS` | MaaS embedding model IDs, as a JSON array or comma-separated list |
| `AUTORAG_GENERATION_MODELS` | MaaS generation model IDs, in the same format |

For authentication, use `oc login` in your terminal, or fill `RHOAI_TOKEN` and `RHOAI_KFP_URL` in `.env`.
No need to source the file. It is ignored by Git. Names follow AutoX CI's `.env.rag`; the runner also
accepts `--env-file /path/to/.env.rag`. Explicit shell variables override file values.

The default audio scenario matches **TC-P-5**:

- Audio directory: `datasets/rag/audio/documents`
- Benchmark: `datasets/rag/audio/benchmark_data.json`
- Metric: `answer_correctness`; maximum patterns: `4`; preset: `speed`

Change the two S3 paths in `.env` to use another existing dataset. The benchmark's source keys must
point at those recordings. CI may remove its fixtures, so the configured objects must still exist.
Existing data is used as supplied; the runner does not upload or delete it.

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

The command validates your selected pipeline, creates or reuses `autorag-audio-sample`, submits a
uniquely named run and waits for it. Managed mode discovers and pins an installed version. Local
mode submits an exact snapshot of your YAML, including Kubernetes platform settings, without
replacing the managed pipeline. Execution takes place on OpenShift in both modes.
**You don't create or edit JSON configuration files.** Parameters, full pipeline spec, selected IDs
and the run receipt are saved automatically under `work/runs/<run-name>/` for troubleshooting.
Tokens and Connection credentials are not saved there.

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

After optimization succeeds, check every recording produced a nonempty transcript. Select a pattern
by the optimization metric and download its product `pattern.json` and `inference.ipynb`.
Also retain evaluation results, leaderboard and starter kit when available.

Set these two additional values in the **same `.env`**:

```dotenv
AUTORAG_PATTERN_FILE=work/pattern.json
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
not an observed result. Verify the retrieved source/excerpt against the recording, then evaluate
the separate questions in `data/holdout.json` after fixing the pattern.

## More options

- [Environment settings and run details](docs/run-on-openshift.md)
- [Use your own recordings or upload the bundled corpus](samples/README.md)
- [Prerequisites and ASR packaging](docs/prerequisites.md)
- [Compatibility](docs/compatibility.md), [troubleshooting](docs/troubleshooting.md), [acceptance checklist](docs/validation.md)

The only configuration file is `.env`. Shared implementation lives in `scripts/lib/`.
Optional commands prepare your own corpus, validate local data and collect answer evidence.

This private sample includes three Polish recordings, an 11-question benchmark and three draft
held-out questions. A successful sample pipeline run and grounded answer remain to be recorded.
Public corpus redistribution clearance and listening review remain pending. Original M4A support
depends on the installed product image; the WAV derivative is not evidence of M4A support.
Helper code is Apache-2.0; corpus rights are separate. See [NOTICE](NOTICE) and [data provenance](data/README.md).

## Local checks

```bash
uv sync --frozen --dev
uv run ruff check .
uv run ruff format --check .
uv run python -m unittest discover -s tests
uv run python scripts/validate_sample.py --profile wav-mp3
uv run python scripts/validate_sample.py --profile original-three
```
