# Troubleshooting

| Symptom | Check / next action |
| --- | --- |
| Local validation reports a placeholder | Fill the named variable in `.env`; example placeholders are not real model IDs. |
| Manifest checksum or size mismatch | Confirm the intended audio. For your own corpus, regenerate with `prepare_corpus.py --replace-manifest` after reviewing changes; do not edit hashes to conceal accidental changes. |
| A benchmark source is outside the profile | Use relative `audio/<filename>` keys matching each selected clip. Staging renders the S3 prefix. |
| S3 upload finds unexpected objects | Use a fresh dedicated prefix. The uploader never deletes an existing object. Switching between M4A and WAV profiles needs a new prefix. |
| S3 returns 403 | Check workstation credentials, endpoint/region and list/get/put permissions; the workstation profile is separate from the cluster Connection. |
| Conditional S3 creation is unsupported | Use S3-compatible storage with conditional PutObject support. The sample uploader does not overwrite conflicting objects. |
| KFP returns 401/403 | Check `RHOAI_KFP_URL`, project and permissions. Refresh `RHOAI_TOKEN` if set; otherwise refresh `oc login`. A nonempty `.env` token takes precedence over `oc`. |
| Run record already exists | A fixed `AUTORAG_RUN_NAME` was used before. Inspect its receipt/UI first, then choose a new name for an intentional new experiment. |
| S3 objects not found | Confirm both `.env` path variables and buckets. AutoX CI may have removed its fixtures; use a fresh prefix and the documented local upload mode if needed. |
| Installed pipeline spec differs | Inspect the exact intended version again and review changes before resubmission. |
| Unknown pipeline parameter | Check current installed names/types; old examples and newer generated patterns can target different versions. |
| Model ID or optimization metric rejected | Confirm actual MaaS model IDs/capabilities and the installed evaluator's accepted metric spelling. |
| Missing `HF_MODEL_DIR` / invalid local model | Check the product image/modelcar delivery and complete Transformers-format model files. Do not enable downloads or grant cache write access as a workaround. |
| Empty or inaccurate transcript | Inspect per-file extraction output and language/model quality; listening review is required. A successful container exit is insufficient. |
| Original M4A fails | Record exact image, ffmpeg version, file checksum and inner error. RHAI-8244 tracks product behavior. Compare with the WAV profile without claiming the conversion fixes product M4A support. |
| Extraction OOM, quota or timeout | Record requested/available resources, audio duration and failure stage; use shorter clips or the supported resource configuration. Historical turbo guidance may not apply. |
| TLS/private CA failure | Configure the appropriate workstation CA bundle and project Connection CA. Retain TLS verification. |
| Correct fact but no audio citation | Check retrieved source keys/excerpts and the actual collection. A plausible answer from model memory does not prove this path. |
| Query misses indexed clips | Verify database, embedding model/dimensions, selected pattern and collection binding all match the managed indexing run. |
| No chunk timestamps | Check whether the pattern uses the supported hybrid/Docling path. The speed/recursive profile does not retain this provenance. |
| Missing starter kit or different API | Check artifacts and documentation for the selected product version. Do not invent an endpoint or claim an untested deployment. |
| Wait timeout / uncertain submission | Inspect the receipt and existing run name in the UI. A timeout does not cancel the run; never blindly resubmit. |

Record product defects separately from sample changes. Keep full logs and private endpoints in
private evidence storage; review anything copied to issues or public documentation.
