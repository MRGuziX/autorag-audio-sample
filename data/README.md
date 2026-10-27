# Included audio and provenance

The original Polish story recordings and 11-question benchmark were used in RHOAIENG-80950.
They were copied for this private sample from `autox-ci` revision
`ccc7a06e59e70cb466d170df5389cb2f895d1c83`, under its audio test-data directory.
Tomasz authorised their use in this private repository on 2026-10-26. Public redistribution/license
clearance remains pending; the code license does not grant rights to these recordings or stories.

The stories are fictional. This small narrative corpus demonstrates product mechanics; its scores
do not measure enterprise, multilingual or transcription quality in general.

| Profile | Clips | Optimization questions | Held-out questions |
| --- | --- | --- | --- |
| `wav-mp3` | Original anteater MP3, original termites WAV, converted capybara WAV | 11 | 3 draft |
| `original-three` | Original anteater MP3, termites WAV and capybara M4A | 11 | 3 draft |

`manifest.json` records hashes, sizes, durations, codecs, source and profile membership. Benchmark
source keys are relative `audio/<filename>` values; staging adds your configured S3 prefix. Primary
and original-format benchmarks have corresponding source extensions.

The original capybara file is preserved byte-for-byte at
`validation/original/capybara_story.m4a`. Its default-profile WAV derivative was created with:

```bash
ffmpeg -nostdin -hide_banner -loglevel error -n \
  -i data/validation/original/capybara_story.m4a \
  -vn -ac 1 -ar 16000 -c:a pcm_s16le data/audio/capybara_story.wav
```

This conversion keeps the story available while original M4A product compatibility is checked.
It is not an M4A product fix or proof that an installed AutoRAG image can decode the original.

`reference/*.txt` contains the written story text from the original benchmark ticket. It is not a
verified ASR transcript or a completed listening audit. The added held-out questions were drafted
from that text and need independent listening review before quality claims. Avoid cross-story
battle-start-time questions: the written perspectives disagree about noon versus 13:00.

Reference text and held-out questions are never staged into the audio corpus. The original benchmark
was generated with assistance from Gemini according to its source ticket; labels require human
review regardless of how they were created.

`validate_sample.py --release` checks manifest clearance/review status in addition to integrity.
It deliberately fails while these remain pending. Changing status fields is a record of an actual
review/clearance decision, not a way to bypass it.
