# Included audio and provenance

The original Polish story recordings and 11-question benchmark were used in RHOAIENG-80950.
They were copied for this private sample from `autox-ci` revision
`ccc7a06e59e70cb466d170df5389cb2f895d1c83`, under its audio test-data directory.
Tomasz authorised their use in this private repository on 2026-10-26. Public redistribution/license
clearance remains pending; the code license does not grant rights to these recordings or stories.

Use the default dataset paths in `.env`:

```dotenv
AUTORAG_INPUT_DATA_KEYS=["data/rag/audio/sample/documents"]
AUTORAG_TEST_DATA_KEY=data/rag/audio/sample/benchmark.json
```

The three recordings are `documents/anteater_story.mp3`, `documents/termites_story.wav` and
`documents/capybara_story.m4a`. The benchmark contains 11 optimization questions referencing their
full keys. The local paths and uploaded S3 keys are identical. Reference text remains local.

The stories are fictional. This small narrative corpus demonstrates product mechanics; its scores
do not measure enterprise, multilingual or transcription quality in general.

`reference/*.txt` contains the written story text from the original benchmark ticket. It is not a
verified ASR transcript or a completed listening audit. Labels need independent listening review
before quality claims. Avoid cross-story battle
start-time questions: the written perspectives disagree about noon versus 13:00.

The original benchmark was generated with assistance from Gemini according to its source ticket.
Labels require human review regardless of how they were created. Record listening review and public
redistribution clearance in the validation record when completed.
