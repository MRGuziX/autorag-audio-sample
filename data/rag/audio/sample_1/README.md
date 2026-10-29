# English story recordings

This dataset contains the three recordings supplied from the user's Downloads directory:

| Recording | Reference text | Benchmark questions |
| --- | --- | --- |
| `documents/story_10.mp3` | `reference/story_10.txt` | 7 |
| `documents/story_100.mp3` | `reference/story_100.txt` | 7 |
| `documents/story_1015.mp3` | `reference/story_1015.txt` | 6 |

The reference files are automatic Whisper transcripts of the recordings, created locally on
2026-10-29. They are provided for comparison and benchmark review, and have not undergone a full
human listening review. Names and unusual phrases may contain transcription errors. Story claims
and numerical inconsistencies are retained rather than silently corrected.

Only `documents/` and `benchmark.json` are uploaded by the runner. Reference text stays local.

```dotenv
AUTORAG_INPUT_DATA_KEYS=["data/rag/audio/sample_1/documents"]
AUTORAG_TEST_DATA_KEY=data/rag/audio/sample_1/benchmark.json
```
