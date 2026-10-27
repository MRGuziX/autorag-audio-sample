# Compatibility record

**No installed RHOAI baseline has been validated for this sample yet.** All entries below are
implementation observations from local source, not a release support matrix.

| Component | Inspected revision | Observation |
| --- | --- | --- |
| pipelines-components | `6f11d3e0`, 2026-10-23 | `input_data_keys` list; explicit MaaS/DB secrets and embedding/generation model lists; indexing blueprint carries preset |
| ai4rag | `25a8102`, 2026-10-26 | Local HF Whisper adapter, CPU execution, seekable-file decode and M4A error handling in source |
| autox-ci audio fixture | `ccc7a06e59e70cb466d170df5389cb2f895d1c83` | Three Polish recordings and 11 source-linked questions |

The tests include small **parameter-definition snapshots** from the local Python pipeline signatures.
These check helper compatibility with that source shape. They are not executable pipeline packages
or substitutes for the runner's validation against the full installed version.

Known differences from historical audio benchmarks:

- Use `input_data_keys: ["prefix/audio/"]`; the older singular `input_data_key` is not forwarded.
- Use `maas_secret_name`, `db_secret_name`, `embedding_models` and `generation_models`; do not
  reuse historical `ogx_secret_name` or `vector_io_provider_id` parameters.
- The sample defaults to `answer_correctness`, matching AutoX CI TC-P-5. Other metrics must be
  supported by the installed evaluator. A STRING parameter definition alone cannot establish metric validity.
- Generated indexing blueprints can contain `provider_type` although the target indexing signature
  chooses its backend through secret keys. The adapter validates this known metadata before omitting
  it. Any other unknown field fails instead of being silently discarded.
- ASR size/model selection is not a top-level parameter in these inspected signatures. UI audio
  file selection does not imply an ASR settings panel exists.
- Segment timing in Docling JSON and timing on retrieved vector chunks are separate checks.
  `audio_start_seconds`/`audio_end_seconds` require the supported hybrid/Docling chunking path;
  no word-level-seek precision is promised.

Relevant product work: RHOAIENG-97601 (local modelcar-backed ASR), RHOAIENG-96946 and
RHOAIENG-97386 (model download failures), RHAI-8244 (original M4A failures), RHOAIENG-96103
(file-picker support) and RHOAIENG-96490 (chunk timing).

When establishing a baseline, record platform versions, explicit pipeline/version IDs, execution
image digests, runtime library versions, modelcar digest/revision and model mount/copy paths.
If source fixes are not present in those images, keep the dependent support claim open.
