# Acceptance and validation record

Target: [RHOAIENG-96837](https://redhat.atlassian.net/browse/RHOAIENG-96837).
The sample implements staging, managed/local pipeline submission, artifact downloads and indexing.
A complete product walkthrough with recorded optimization/indexing runs and a grounded answer
remains pending. Local tests do not establish the installed product's ASR compatibility.

## Local checks

Validation on macOS / Python 3.12:

- 69 offline tests cover configuration, both bundled datasets, custom audio/benchmark-only inputs,
  upload isolation and conflicts, managed/local pipeline contracts, authentication and submission.
- Run recovery tests cover timeout followed by remote success, active/failed runs, old target.json
  records and retries without resubmission. Unknown submission outcomes remain protected.
- New receipts contain endpoint/project and source metadata. Indexing receipts retain the selected
  pattern hash and target collection without generating target.json or pattern.bound.json.
- Artifact tests cover evaluator consistency, missing/non-finite scores, tied winners identified by
  the product ZIP, mismatched kits, optional leaderboard download, safe paths and atomic transfers.
- Indexing dry-run rejects malformed/inconsistent patterns without contacting KFP. Indexing does not
  require optimization model lists, benchmark settings or a pattern count.
- Ruff lint/format and dependency lockfile checks pass.

Commands are listed in the README. No cluster experiment or S3 upload was performed while
implementing these fixes. The original mixed-format corpus and the additional English corpus pass
structural validation; human listening review and public redistribution clearance remain open.

## Sample acceptance checklist

- [ ] Follow README from a clean clone with the documented prerequisites.
- [ ] Stage the selected recordings and source-aligned benchmark at the configured S3 keys.
- [ ] Complete the official optimization pipeline and verify a nonempty transcript for every clip.
- [ ] Check the optimization metric, selected pattern, product starter kit, notebooks and leaderboard.
- [ ] Complete official full-corpus indexing into the intended fresh collection.
- [ ] Use the product inference notebook with the same pattern, embeddings, database and collection.
- [ ] Record one observed correct answer and retrieved audio source/excerpt checked against the recording.
- [ ] Record both run IDs, versions/image digests, ASR model, corpus size/duration and resulting scores.
- [ ] Record known format, language, resource and disconnected limitations honestly.
- [ ] Clear corpus redistribution/attribution and agree the public destination with AIS BU before publication.

Keep filled settings and detailed run records under ignored work/; share only reviewed, sanitized
results. The code license does not establish rights to either corpus. Do not reuse historical
base/turbo benchmark results as measurements from this starter.

## Product compatibility checks

These apply before making the corresponding support claims; they are not extra configuration
steps for a sample user. Track fixes in their product repositories rather than adding them here:

| Claim | Required product evidence |
| --- | --- |
| Original M4A support | Decode and extract the original M4A in the selected image; WAV conversion is not M4A evidence (RHAI-8244) |
| Local-only ASR | Actual image uses complete read-only local weights with external model-host egress blocked; missing weights fail without downloading (RHOAIENG-97601) |
| Mixed audio/document and text-only compatibility | Corresponding product regressions pass before claiming broader support (RHOAIENG-88080) |
| UI picker support | Select audio and verify forwarded keys in the actual dashboard (RHOAIENG-96103) |
| Retrieved chunk timing | Hybrid/Docling chunks retain ordered source timing ranges; no word-level accuracy claim (RHOAIENG-96490) |

Record the selected RHOAI/OCP/DSPA versions, optimization/indexing pipeline IDs and versions,
execution-image digests, ai4rag/Docling/Transformers/ffmpeg versions, modelcar/model revision and
local weights path. Source fixes or resolved issue statuses alone do not prove an installed baseline.

## Optional answer worksheet

`collect_evidence.py` combines local dataset metadata, supplied receipts and manually reviewed
benchmark responses. It needs local recordings and benchmark files; it is optional and does not
certify product behavior or automatically establish run/data/pattern lineage. The normal
experiment flow does not require it or a separate metadata configuration.

Review retrieved sources against the audio and record failed answers as well as passes. These
checks reuse optimization questions and do not measure performance on unseen questions.
For the ticket, prepare the eventual repository URL, formats/model, both successful run IDs,
worked answer/source and known gaps. Publication and Jira posting are separate actions.
