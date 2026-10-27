# Run from one .env file

Transcription, optimization and indexing execute in OpenShift AI pipelines. Your
workstation reads `.env`, submits the run and waits. It does not run a local RAG implementation.

## First run

```bash
uv sync --frozen
cp -n .env.example .env
```

Fill the project, pipeline URL, bucket, Connection secret names and model IDs in `.env`, as described
in the [README](../README.md). Reuse an existing OpenShift login or put a current bearer token in
`RHOAI_TOKEN` with `RHOAI_KFP_URL`. Do not source the file or put credentials into generated JSON.

```bash
uv run python scripts/run_experiment.py --dry-run
uv run python scripts/run_experiment.py
```

Only the second command connects, creates an experiment if needed and submits a pipeline run.
It does not create a project, DSPA, Connections, model service or database. Set those up first using
the [prerequisites](prerequisites.md). No separate connect, render or submit command is required.

## Settings

Core variables use the AutoX CI `.env.rag` names. Audio scenario settings that AutoX keeps in
`optimisation_test_configs.json` are available as `AUTORAG_*` values in this same file.

| Variable | Meaning/default |
| --- | --- |
| `RHOAI_PROJECT_NAME` | Required existing project |
| `RHOAI_KFP_URL` | HTTPS pipeline API route; discovered with `oc` if blank |
| `RHOAI_TOKEN` | Optional token; otherwise use current `oc` login |
| `AUTORAG_PIPELINE_PATH` | Optional compiled local optimization YAML; blank/unset uses managed |
| `AUTORAG_INDEXING_PIPELINE_PATH` | Optional compiled local indexing YAML; blank/unset uses managed |
| `INPUT_DATA_SECRET_NAME`, `INPUT_DATA_BUCKET_NAME` | Required audio Connection and bucket |
| `TEST_DATA_SECRET_NAME`, `TEST_DATA_BUCKET_NAME` | Benchmark Connection and bucket; blank inherits input values |
| `MAAS_SECRET_NAME`, `VECTOR_DB_SECRET_NAME` | Required existing inference and DB Connections |
| `AUTORAG_EMBEDDING_MODELS`, `AUTORAG_GENERATION_MODELS` | Required JSON arrays or comma-separated MaaS IDs |
| `AUTORAG_INPUT_DATA_KEYS` | JSON array containing one audio directory; defaults to TC-P-5 |
| `AUTORAG_TEST_DATA_KEY` | Benchmark key; defaults to TC-P-5 |
| `AUTORAG_OPTIMIZATION_METRIC` | `answer_correctness` |
| `AUTORAG_MAX_RAG_PATTERNS` | `4` (supported range 4–10) |
| `AUTORAG_PRESET` | `speed` or `balanced` |
| `AUTORAG_EXPERIMENT_NAME` | `autorag-audio-sample` |
| `RHOAI_PIPELINE_RUN_TIMEOUT` | Wait timeout in seconds, `7200` |
| `AUTORAG_RUN_NAME` | Optional fixed name; defaults to a unique name on each invocation |
| `KFP_CA_CERT` | Optional private CA file; TLS verification stays enabled |
| `RHOAI_DSPA_NAME`, `AUTORAG_OC_CONTEXT` | Optional DSPA/context for `oc` discovery |

Use your actual MaaS model IDs, with multilingual support for the Polish corpus. Secrets must be
present in the selected project, not just defined in a different project. The managed product image
must include its supported ASR model and audio decoder; there is no separate transcription service
to configure in this sample. The TC-P-5 fixture includes M4A; its old `.mp4` description is stale.

To reuse the CI environment directly:

```bash
uv run python scripts/run_experiment.py --env-file /path/to/autox-ci/autox_tests/.env.rag
```

Missing scenario variables use TC-P-5 defaults. Unrelated CI settings are not forwarded to KFP;
the runner does not provision CI infrastructure, run notebook Jobs or perform CI fixture teardown.
Explicit shell environment variables override file values; `${...}` interpolation is not used.

When the path for the requested pipeline kind is blank or unset, the runner chooses the newest
installed managed version and records it for that run. To reproduce a particular version, set
`AUTORAG_OPTIMIZATION_PIPELINE_ID` and
`AUTORAG_OPTIMIZATION_VERSION_ID`, or their `AUTORAG_INDEXING_*` equivalents. The pipeline's internal
name and full installed contract are still checked. Only the requested pipeline needs to exist.

When a path is filled, it takes precedence over managed IDs. The file must be compiled KFP v2
`.yaml`/`.yml` with the expected pipeline name, executable deployment spec and compatible parameters.
Relative paths resolve from the selected `.env` file's directory; `~` is expanded. A missing, invalid
or incompatible package fails before connecting, without falling back to a different pipeline.
The command does not compile Python pipeline source.

Local mode copies the exact YAML into the run record and submits that snapshot using KFP's package
submission API. Separate Kubernetes platform documents are retained. It does not upload a reusable
pipeline/version or change installed managed definitions. Both sources execute on OpenShift and
use the same project Connections. A local YAML must reference the intended runtime images and ASR
model delivery; choosing it does not itself repair a broken runtime image.

## Outputs and failures

The runner creates `work/runs/<run-name>/` automatically. It contains:

- `params.json`: actual pipeline arguments;
- `spec.json`: full selected spec, including Kubernetes platform settings;
- `target.json`: project, endpoint and source; managed IDs or local path and SHA-256;
- `receipt.json`: submission state and run ID, written before submission;
- `package.yaml`: exact local package snapshot, when using a local pipeline;
- `pattern.bound.json`: indexing collection binding, for indexing runs.

These are generated records, not files to configure. They contain no copied bearer token or Secret
values. Private project/model/bucket names may appear, so review records before sharing.
Local package receipts record source path and SHA-256 in place of managed IDs, which are null.
The evidence helper retains this source information. The full submitted package is preserved as
supplied, so review any values embedded in your own YAML before sharing run records.

After a timeout, interruption or uncertain submission, inspect the receipt and pipeline UI before
starting another run. The helper never retries a submission automatically. With `AUTORAG_RUN_NAME`
set, an existing local record blocks that name before connecting. Default names are unique, so a
second invocation creates another run. A wait timeout does not cancel the first run.

## Indexing and answer checks

Select the optimization pattern by its declared metric, download its `pattern.json`, then set
`AUTORAG_PATTERN_FILE` and a fresh `AUTORAG_COLLECTION_NAME` in `.env`:

```bash
uv run python scripts/run_experiment.py --kind indexing
```

The pattern file is a product output, not another hand-written configuration. Collection/model
bindings in your inference notebook must match this indexing run. Use the product notebook's ask
path against the populated collection and check factual accuracy and retrieved audio support
separately. Full ticket evidence and remaining product checks are in [validation](validation.md).

For local uploads and custom recordings, follow [samples/README.md](../samples/README.md).
