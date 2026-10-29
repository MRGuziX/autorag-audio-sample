# Run from one .env file

Transcription, optimization and indexing execute in OpenShift AI pipelines. Your
workstation reads `.env`, submits the run and waits. It does not run a local RAG implementation.

## First run

```bash
uv sync --frozen
cp -n .env.example .env
```

Use the default `AUTORAG_INPUT_DATA_KEYS=["data/rag/audio/sample/documents"]` and
`AUTORAG_TEST_DATA_KEY=data/rag/audio/sample/benchmark.json` for the bundled files.
To use your own data, change both paths to your documents directory and benchmark JSON.
With uploads enabled, those same paths are read locally and used as S3 destinations.
See the [benchmark example](../data/README.md).

Fill the project, pipeline URL, bucket, Connection secret names, model IDs and workstation S3
credentials in `.env`, as described in the [README](../README.md). The example already selects
your local sample directory and enables upload. Reuse an existing OpenShift login or put a current bearer token in
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
| `AUTORAG_UPLOAD_TEST_DATASETS` | Example sets `true` to upload local inputs; `false` uses existing S3 inputs |
| `AWS_S3_ENDPOINT`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION` | Workstation access to the same S3 storage as the input Connection; required for local uploads |
| `DOWNLOAD_ARTIFACTS` | Example sets `true`: download the best optimization pattern and starter kit after success; absent/`false` skips downloads |
| `AWS_S3_BUCKET` | Optional artifact bucket override; also accepts `RHOAI_TEST_ARTIFACTS_BUCKET`; blank discovers the run root, then falls back to the input bucket |
| `AUTORAG_INPUT_DATA_KEYS` | One documents directory; local upload source and S3 destination; defaults to `["data/rag/audio/sample/documents"]` |
| `AUTORAG_TEST_DATA_KEY` | Benchmark JSON path; local upload source and S3 destination; defaults to `data/rag/audio/sample/benchmark.json` |
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

When the upload flag is absent, existing S3 objects are used. Set both dataset paths to the CI
fixture locations when reusing its `.env.rag`. The starter example explicitly enables local uploads.
Unrelated CI settings are not forwarded to KFP;
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
- `receipt.json`: project, endpoint, source, submission state and run ID, written before submission;
- `pipeline.yaml`: exact local pipeline snapshot, when using a local pipeline;
- `artifacts/`: downloaded S3 outputs when `DOWNLOAD_ARTIFACTS=true`.

These are generated records, not files to configure. They contain no copied bearer token or Secret
values. Private project/model/bucket names may appear, so review records before sharing.
Local package receipts record source path and SHA-256 in place of managed IDs, which are null.
Indexing receipts also record the selected pattern SHA-256 and target collection.
The evidence helper retains this source information. The full submitted package is preserved as
supplied, so review any values embedded in your own YAML before sharing run records.

After a timeout, interruption or uncertain submission, inspect the receipt and pipeline UI before
starting another run. The helper never retries a submission automatically. With `AUTORAG_RUN_NAME`
set, an existing local record blocks that name before connecting. Default names are unique, so a
second invocation creates another run. A wait timeout does not cancel the first run. Authentication,
discovery and upload failures occur before the run directory is reserved, so they do not consume
a fixed run name.

## Download artifacts

Set `DOWNLOAD_ARTIFACTS=true` to download the highest-scoring optimization pattern and the product
`starter_kit.zip`, plus `leaderboard.html` when the product supplies it. The runner reads each
pattern's aggregate metric scores from S3, ranks them by
the mean of the optimization metric saved in `params.json`, and downloads only the winning folder
(including `pattern.json`, notebooks and evaluation files) plus the ZIP. It checks evaluator names
for qualified metrics and rejects comparisons across different evaluators. For tied best scores,
it uses the pattern named in the product starter-kit README. A kit identifying a lower-scoring or
unknown pattern, or an unrecognized README format, causes a download error. Missing/non-finite
scores are excluded;
no usable score or no unique starter kit causes a download error rather than an arbitrary choice.

Outputs are `artifacts/best-pattern/`, `artifacts/starter_kit.zip` and `artifacts/leaderboard.html`.
A missing leaderboard is reported without failing the other downloads; check the optimization
task's output artifacts in the pipeline UI for product versions with different layouts. Ranked
scores and selection are recorded in the receipt. Indexing runs download their run-scoped artifacts.
The runner discovers the storage root from KFP
and scopes the prefix to the pipeline name and run ID. If KFP omits the root, set the artifact
bucket explicitly; otherwise it falls back to the input bucket.

Downloads reuse the AWS endpoint and credentials from `.env`; those credentials need read/list
access to the artifact bucket as well as any upload permissions for input data. Set
`AWS_S3_BUCKET` when artifacts are in a different bucket. If the storage service itself is
different, update the AWS endpoint/credentials before using the download-only command below.

Files are saved beneath `work/runs/<run-name>/artifacts/`. The selected pattern preserves its internal
folder structure under `best-pattern/`; the product ZIP is saved as `starter_kit.zip`.
Download status and file count are recorded in the run receipt. A failed download leaves the
pipeline result intact. Correct storage access and retry without creating another experiment:

```bash
uv run python scripts/run_experiment.py --download-run <run-name>
```

This command uses the endpoint/project saved in the receipt and refreshes the existing run state
from KFP, so it also recovers a run that succeeded after a wait timeout or interruption. It never
submits an experiment. A failed or still-running run is reported without downloading. An unknown
run ID requires inspection in the pipeline UI. Older records may still use their existing
`target.json`; new runs do not create it. The command works even when `DOWNLOAD_ARTIFACTS=false`.
`--dry-run` makes no artifact requests.

## Indexing and answer checks

With automatic downloads, use `work/runs/<run-name>/artifacts/best-pattern/pattern.json`, then set
`AUTORAG_PATTERN_FILE` and a fresh `AUTORAG_COLLECTION_NAME` in `.env`:

```bash
uv run python scripts/run_experiment.py --kind indexing
```

The pattern file is a product output, not another hand-written configuration. Relative pattern
paths resolve from the selected .env file's directory; `~` is expanded, as for local pipeline paths.
Indexing dry-run validates the pattern blueprint without network access. Indexing gets model and
chunking choices from the pattern; optimization-only model lists, benchmark and pattern-count
settings are not required for this step. Collection/model
bindings in your inference notebook must match this indexing run. Use the product notebook's ask
path against the populated collection and check factual accuracy and retrieved audio support
separately. Full ticket evidence and remaining product checks are in [validation](validation.md).

For local uploads and custom recordings, follow [data/README.md](../data/README.md).
