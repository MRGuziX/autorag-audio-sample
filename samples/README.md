# Use your own recordings

Create this structure inside the repository; `samples/user/` contents are ignored by Git:

```text
samples/user/
  audio/
    briefing.wav
    walkthrough.mp3
  benchmark.json
  holdout.json       # optional, recommended for checking an unseen question
```

Keep reference transcripts outside `audio/`. Use lowercase `.wav`, `.mp3` or `.m4a` extensions.
Start with short WAV/MP3 clips. Product M4A compatibility depends on the installed image.

Write questions and expected answers about the actual recordings. The benchmark is a nonempty
JSON list using relative object keys, not absolute filesystem paths or S3 URLs:

```json
[
  {
    "question": "What time does the briefing say the maintenance window begins?",
    "correct_answers": ["22:00", "10 PM"],
    "correct_answer_document_keys": ["audio/briefing.wav"]
  },
  {
    "question": "Which entrance does the walkthrough say visitors should use?",
    "correct_answers": ["the north entrance"],
    "correct_answer_document_keys": ["audio/walkthrough.mp3"]
  }
]
```

These example facts are illustrative; replace them with facts from your clips. Each clip must be
covered by a benchmark question. If you include `holdout.json`, use the same shape with distinct
questions covering each clip. Leave it out if you only want to run optimization; that run then has
no held-out quality evidence. No question file goes inside `audio/`.

Install ffmpeg/ffprobe for manifest preparation, then run:

```bash
uv run python scripts/prepare_corpus.py --directory samples/user --language en
```

Preparation reads your audio with ffprobe and writes an integrity manifest. It does not transcribe,
change the audio or upload it. Rerun with `--replace-manifest` after deliberately changing files.
ffprobe success is a local metadata check; actual decoding and ASR still need product validation.

In your ignored `.env`, set:

```dotenv
AUTORAG_DATASET_DIR=samples/user
AUTORAG_PROFILE=custom
AUTORAG_S3_PREFIX=autorag-audio/my-corpus-v1
AUTORAG_UPLOAD_TEST_DATASETS=true
AUTORAG_INPUT_DATA_KEYS=
AUTORAG_TEST_DATA_KEY=
```

Keep the bucket/Connection/model settings from the main setup. Clear both explicit S3 path fields
so the uploaded audio and benchmark paths derive from your new prefix. Use the same input and test
bucket/Connection for uploads. Supply workstation S3 access through `.env`:

```dotenv
AWS_S3_ENDPOINT=https://your-s3-endpoint
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_DEFAULT_REGION=us-east-1
```

Alternatively, use your normal AWS credential profile/provider chain. The workstation endpoint must
reach the same object store as your project's input Connection. The runner does not copy workstation
credentials into cluster Secrets. Adjust model IDs for the spoken language, then run:

```bash
uv run python scripts/run_experiment.py --dry-run
uv run python scripts/run_experiment.py
```

The real command uploads only the manifest-selected audio and source-aligned benchmark, verifies
checksums and submits optimization. Reference text and held-out questions remain local. Existing
conflicting objects are refused. For later indexing, it reuses those staged paths without uploading again.

To upload the bundled corpus instead, use `AUTORAG_DATASET_DIR=data` and
`AUTORAG_PROFILE=original-three` (or `wav-mp3` for the WAV derivative), with the same upload settings.
Its manifest is already present, so skip manifest preparation.

Follow the indexing and ask steps in the main README. A different directory also works:
pass it to `prepare_corpus.py --directory` and use that same relative path as `AUTORAG_DATASET_DIR`.
Never reuse an old corpus prefix or vector collection for a different dataset without understanding
the product's indexing behavior. Document your own data sources, usage rights and label review.
