# Experiment data

The same two paths select local files and their destinations in S3:

```dotenv
AUTORAG_INPUT_DATA_KEYS=["data/rag/audio/sample/documents"]
AUTORAG_TEST_DATA_KEY=data/rag/audio/sample/benchmark.json
```

The bundled Polish recordings and benchmark are ready in those locations. Their provenance is in
[the sample README](rag/audio/sample/README.md).

## Use your own recordings

1. Drop WAV, MP3 or M4A recordings into `data/rag/audio/users/documents/`.
2. Add `data/rag/audio/users/benchmark.json` with your questions and expected answers.
3. Change both dataset paths in `.env`:

```dotenv
AUTORAG_INPUT_DATA_KEYS=["data/rag/audio/users/documents"]
AUTORAG_TEST_DATA_KEY=data/rag/audio/users/benchmark.json
AUTORAG_UPLOAD_TEST_DATASETS=true
```

Then run:

```bash
uv run python scripts/run_experiment.py
```

With uploads enabled, the runner reads these local repository-relative paths, uploads to the same
keys in S3, then submits the OpenShift experiment. Set `AUTORAG_UPLOAD_TEST_DATASETS=false` to use
objects already in S3; local files are then unnecessary. No separate upload paths are needed.
The workstation S3 endpoint and credentials must reach the same storage as the input Connection.
Uploads use one bucket and Connection for recordings and benchmark.

The benchmark is a JSON list. Use recording keys matching the selected documents directory:

```json
[
  {
    "question": "What time does the maintenance window begin?",
    "correct_answers": ["22:00", "10 PM"],
    "correct_answer_document_keys": ["data/rag/audio/users/documents/briefing.wav"]
  }
]
```

Use facts from your recordings. Keep reference text outside `documents/`. Files under
`data/rag/audio/users/` are ignored by Git. Decoding and transcription happen on OpenShift.
No preparation command, metadata file or local FFmpeg installation is required.

Use fresh dataset paths when changing recordings; conflicting objects are refused. Optional
`--dry-run` validates local settings and upload inputs without connecting or uploading.
Indexing reuses the selected S3 paths without uploading again.
