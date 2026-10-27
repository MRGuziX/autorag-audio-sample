# Acceptance and validation record

Target: RHOAIENG-96837, with relevant parent/dependency criteria. No product run is recorded yet.
The repository currently implements the local data/configuration/tooling portion. The detailed
planning document remains local to the developer workspace.

## Local checks

Local validation on macOS / Python 3.12:

- 47 offline tests cover TC-P-5 parameters, both corpus profiles, custom corpus paths, upload
  isolation, pipeline identity/contract checks, full wrapped-spec comparisons, `.env` precedence,
  token/`oc` authentication, experiment reuse, indexing bindings and human answer evidence.
- Run receipts preserve uncertain submissions and wait timeouts without retrying the run.
- Local package tests cover blank/unset managed fallback, invalid-path rejection, exact YAML
  snapshots, separate Kubernetes platform settings, package submission and source provenance.
  The local optimization YAML supplied by the user passes package/parameter checks without a run.
- Ruff lint/format and the dependency lockfile checks pass.
- The private `.env` passes an offline dry run. Evidence worksheets use that same file.
- Both bundled profiles pass manifest/benchmark checks. All four audio files decoded with local
  ffmpeg during initial preparation; this does not establish product-container support.
- A read-only pipeline API inspection confirmed `pipeline_spec` / `platform_spec` wrappers.
  The runner preserves both when snapshotting and checking the installed version.

The normal entry point is `scripts/run_experiment.py`, configured only through `.env`. Shared
implementation lives in `scripts/lib/`; the former JSON configuration and manual submission tools
have been removed. The user runs and verifies the actual cluster experiments. No pipeline run or
S3 upload was performed during implementation or cleanup.

These checks establish sample integrity and helper behavior. Product execution, answer grounding,
listening review and public distribution clearance remain open. `validate_sample.py --release`
is expected to fail until actual clearance and listening review are recorded in the manifest.

## Baseline to record before a product run

Keep filled private values under ignored `work/` or another private evidence location:

| Item | Status |
| --- | --- |
| Repository revision and dataset manifest hashes | Pending review |
| RHOAI / OCP / DSPA-KFP versions and project | Not recorded |
| Optimization and indexing pipeline IDs/version IDs | Not recorded |
| Actual execution-image digests for both extraction paths | Not recorded |
| ai4rag / Docling / Transformers / ffmpeg versions | Not recorded |
| ASR backend/model revision, modelcar digest and effective local weights path | Not recorded |
| MaaS embedding/generation IDs; vector DB backend | Not recorded |
| Actual CPU/memory requests/limits, quota and observed usage | Not recorded |
| Original M4A decode/extraction result in the product image | Not tested |

## Acceptance checklist

- [ ] README can be followed from a clean clone using documented prerequisites only.
- [ ] S3 contains exactly the selected audio files and a source-aligned optimization benchmark.
- [ ] Official optimization run succeeds; every expected clip has a nonempty ASR transcript.
- [ ] Docling JSON contains usable segment timing when checking the local-ASR product contract.
- [ ] Leaderboard, selected pattern, evaluation, notebooks and starter-kit availability are documented.
- [ ] Pattern is selected using the optimization metric before held-out evaluation.
- [ ] Official indexing run processes the full sample corpus and populates the intended collection.
- [ ] Inference uses the same pattern, embedding settings, database and indexed collection.
- [ ] Worked answer is correct and supported by retrieved audio source/excerpt checked against recording.
- [ ] Fixed held-out questions have independent factual/source judgments and all outcomes recorded.
- [ ] Run IDs, versions, data sizes, duration, model details, metrics and failures are recorded.
- [ ] Original M4A result is recorded honestly; default WAV conversion is not counted as M4A support.
- [ ] Mixed audio+document and text-only product checks support any compatibility claims made.
- [ ] File-picker selection/forwarded keys are tested before claiming a working UI path.
- [ ] External model-host egress blocked + read-only local weights check supports any local-only ASR claim.
- [ ] Missing weights fail usefully without runtime download; internal service access still works.
- [ ] Optional hybrid chunk timings, if advertised, are ordered and within the source duration.
- [ ] Public data rights/attribution and listening review are resolved before public release.
- [ ] Public destination is agreed with AIS BU and public clean-clone walkthrough passes before full ticket closure.

## Evidence worksheet

`collect_evidence.py` can combine local metadata and run receipts and generate a held-out answer
worksheet. It never marks the checklist complete automatically. Review retrieved sources against
audio and record failed answers as well as passes. Report N/M and product metrics without inventing
a quality threshold or reusing historical base/turbo results as this sample's measurements.

For the ticket comment, record the eventual repo URL/visibility; formats/codecs and actual ASR model;
optimization/indexing run IDs; corpus size and duration; grounded question/result; and known language,
M4A, disconnected, resource and UI limitations. Posting Jira comments and public publication are
separate actions; this repository's local commands do neither.

The original benchmark includes fictional story facts, and the new holdout was drafted from written
reference text. Do not mark `label_review_status` as `verified_against_audio` until listening review
is complete. Do not mark `rights_status` as `cleared` until the distribution decision is recorded.
