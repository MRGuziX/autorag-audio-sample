# Run via code

Use one `.env` file and the Python runner to submit audio RAG experiments, download results
and index the full corpus. Transcription, optimization and indexing execute in OpenShift AI
pipelines; the workstation prepares inputs and submits the runs.

[Sample overview](../README.md) · [Run via UI](run-via-ui.md)

Run the commands below from the repository root.

## Prerequisites

1. Create or select an OpenShift AI project. Configure its pipeline server and artifact storage,
   and wait for the server to become ready. The managed optimization and indexing pipelines must
   be available when using managed mode.
2. Add secrets in that project for S3 storage, MaaS and a Milvus, PGVector or Neo4j database.
   The pipeline pods need access to those services, and MaaS must serve your embedding and
   generation models. Use the same database secret when optimizing and indexing a selected pattern.
3. Install Python 3.12 or 3.13 and [uv](https://docs.astral.sh/uv/).
   Install the OpenShift CLI (`oc`) if you will authenticate using your current OpenShift login.
4. Prepare workstation S3 credentials when uploading recordings or downloading artifacts.
   The example enables both operations.

See [project creation](prerequisites.md#create-or-select-a-project) and
[required secret keys](prerequisites.md#connections-and-credentials) for shared setup details.
The runner uses the Kubernetes secret names. Register those secrets as dashboard Connections
as well if you want to use the [UI walkthrough](run-via-ui.md).

## Create and fill .env

Install the dependencies and create your configuration:

```bash
uv sync --frozen
cp -n .env.example .env
```

Fill the following values in `.env` before running:

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
| `AWS_SESSION_TOKEN` | Optional session token when using temporary AWS credentials |
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

Use your actual MaaS model IDs, with support for the language of your recordings. Secrets must be
present in the selected project, not just defined in a different project. The managed product image
must include its supported ASR model and audio decoder.

Choose the database through `VECTOR_DB_SECRET_NAME`. For example, secrets named `milvus`,
`pgvector` and `neo4j` select those respective connections when they exist in your project.
The pipeline detects the backend from the secret's keys. For Neo4j, see the
[Connection requirements](prerequisites.md#connections-and-credentials).

For authentication, run `oc login` using your cluster's login instructions.
Leave `RHOAI_TOKEN` blank to reuse that session; leave `RHOAI_KFP_URL` blank to discover the
project's pipeline endpoint. Alternatively, fill both `RHOAI_TOKEN` and `RHOAI_KFP_URL` to use
explicit token authentication.

The runner reads `.env` directly. Keep it local and ignored by Git; do not source it.
Explicit shell variables override file values. Connection passwords and MaaS API keys belong in
the project secrets; the corresponding `.env` settings contain secret names.

## Choose your data

The bundled sample contains three English MP3 recordings and 20 benchmark questions.
Keep these defaults to use it:

```dotenv
AUTORAG_INPUT_DATA_KEYS=["data/rag/audio/sample/documents"]
AUTORAG_TEST_DATA_KEY=data/rag/audio/sample/benchmark.json
AUTORAG_UPLOAD_TEST_DATASETS=true
DOWNLOAD_ARTIFACTS=true
```

With uploads enabled, the runner reads the two paths locally and uploads to those same keys in S3.
Local uploads require the same bucket and Connection for recordings and benchmark.
Use fresh paths when replacing uploaded data; conflicting objects are refused.

To use recordings already in S3, set `AUTORAG_UPLOAD_TEST_DATASETS=false` and set both dataset
paths to their existing object keys. Workstation S3 credentials are still needed when
`DOWNLOAD_ARTIFACTS=true`.

>!note
> Why that path `data/rag/audio/sample/benchmark.json` need to be exact the same?
> Because we are using in the AI4RAG repository precise key paths. Which mean that
> file benchmark.json need to provide the full path to the targeted files for questions.
> You can use your own files, but remember that You need to write a full correct path.

To use your own data, put recordings in `data/rag/audio/users/documents/`, create
`data/rag/audio/users/benchmark.json`, and change both paths in `.env`.
See [data preparation and the benchmark format](../data/README.md).

## Validate and run

The example uses metric `answer_correctness`, four patterns and preset `speed`.
Leave `AUTORAG_PIPELINE_PATH` blank to use the managed optimization pipeline.
See [pipeline source](#pipeline-source) to submit a compiled local YAML instead.

Check local inputs, then submit:

```bash
uv run python scripts/run_experiment.py --dry-run
uv run python scripts/run_experiment.py
```

A dry run validates local settings and, when selected, the local YAML and parameter contract.
Managed pipeline contracts are checked when connected. Data access, model availability and
ASR compatibility still need a product run.

The second command uploads the dataset when enabled, validates the selected pipeline, creates
or reuses the `autorag-audio-sample` experiment, submits a uniquely named run and waits for it.
Managed mode discovers and pins an installed version. Generated parameters, the pipeline spec
and the receipt are saved under `work/runs/<run-name>/`; these files are created automatically.

A timeout leaves the remote run running. Check the receipt and pipeline UI before starting
another run. See [outputs and failures](#outputs-and-failures) for recovery details.

## Pipeline source

Leave `AUTORAG_PIPELINE_PATH` blank to use the installed managed optimization pipeline.
To submit a compiled local package instead, set its path in the same `.env`:

```dotenv
AUTORAG_PIPELINE_PATH=/path/to/documents_rag_optimization_pipeline/pipeline.yaml
```

For indexing, `AUTORAG_INDEXING_PIPELINE_PATH` makes the same choice independently.

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
uv run python scripts/run_experiment.py --download-run "<run-name>"
```

This command uses the endpoint/project saved in the receipt and refreshes the existing run state
from KFP, so it also recovers a run that succeeded after a wait timeout or interruption. It never
submits an experiment. A failed or still-running run is reported without downloading. An unknown
run ID requires inspection in the pipeline UI. Older records may still use their existing
`target.json`; new runs do not create it. The command works even when `DOWNLOAD_ARTIFACTS=false`.
`--dry-run` makes no artifact requests.

## Select a pattern, index and ask

With downloads enabled, the selected pattern's `pattern.json`, notebooks and evaluation files
are saved under `work/runs/<run-name>/artifacts/best-pattern/`, with `starter_kit.zip` and
the available `leaderboard.html` beside that folder. The runner prints the winning name and
score, and records all ranked scores in the run receipt. Check transcript coverage through
the pipeline UI; this download option does not download transcript artifacts.

Set these additional values in the **same `.env`**:

```dotenv
AUTORAG_PATTERN_FILE=work/runs/<run-name>/artifacts/best-pattern/pattern.json
AUTORAG_COLLECTION_NAME=audio_sample_001
```

Use a fresh vector collection, then run:

```bash
uv run python scripts/run_experiment.py --kind indexing --dry-run
uv run python scripts/run_experiment.py --kind indexing
```

The pattern file is a product output. Relative pattern paths resolve from the selected
`.env` file's directory; `~` is expanded, as for local pipeline paths.
Indexing dry-run validates the pattern blueprint without network access.

Indexing gets the model and chunking choices from the pattern. Optimization model lists,
benchmark settings and the pattern count are not required for this step. It reuses the
selected S3 paths without uploading recordings again.

Neo4j indexing also preserves and validates the selected generation model, generation parameters
and graph-extraction settings. Use the same database Connection for optimization and indexing.
The indexing receipt records the pattern hash and target collection; `params.json` records the
exact submitted arguments.

Use the downloaded product `inference.ipynb` for the ask step:

1. Open `artifacts/best-pattern/inference.ipynb` in an OpenShift AI workbench and run **Setup**.
2. Attach the MaaS and database Connections used by the indexing pipeline.
   In **Prepare MaaS client**, verify that `MAAS_BASE_URL` and `MAAS_API_KEY` are available.
3. In **Initialize Vector Store Client** (or **Connect to the Neo4j graph**), replace the
   generated `collection_name` with your `AUTORAG_COLLECTION_NAME`. Keep the generated embedding
   model, dimensions and retrieval settings. The original collection refers to optimization
   data; use the full-corpus collection you just populated.
4. Run the initialization cells through **Query RAG Pattern**, enter a question and inspect the
   response and retrieved sources. The indexing pipeline has populated the collection, so you
   can skip the separate `indexing.ipynb` walkthrough.

For the bundled sample, ask:

> What kind of animal did Billy keep as a pet?

Expected answer: **A goat**, supported by `story_10.mp3`. This is a reference answer;
verify the observed response and source excerpt against the recording.

The downloaded starter kit is also a product output. To use it against the new collection,
update `vector_store.collection_name` in its `agent_config.json` and configure access according
to its README. This sample does not deploy it automatically.

Optional answer evidence is collected with `scripts/collect_evidence.py` after the run.
See [validation](validation.md) for the evidence workflow and remaining product checks.

## Local development checks

Shared implementation lives in `scripts/lib/`. To run the repository's local checks:

```bash
uv sync --frozen --dev
uv run ruff check .
uv run ruff format --check .
uv run python -m unittest discover -s tests
```

[Back to the sample overview](../README.md)
