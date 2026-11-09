# AutoRAG audio sample

Use this sample to run an audio RAG experiment on OpenShift AI. The pipeline reads recordings
from S3, transcribes them with Docling ASR and optimizes RAG patterns against a question-and-answer
benchmark. You can then select a pattern, index your full corpus and ask questions grounded in
the recordings.

The bundled dataset contains English MP3 recordings, 20 benchmark questions and reference
transcripts under [data/rag/audio/sample/](data/rag/audio/sample/README.md). You can also
[use your own recordings](data/README.md).

## Choose how to run

| Walkthrough | What you will do |
| --- | --- |
| [Run via UI](docs/run-via-ui.md) | Prepare your project Connections, create a run in the AutoRAG dashboard, inspect patterns and run indexing. |
| [Run via code](docs/run-via-code.md) | Fill one `.env` file and use the Python runner to upload data, submit experiments, download results and run indexing. |

Both paths execute the experiment on OpenShift AI.

## Before you start

You need access to an OpenShift AI cluster and created project or option to create one.
Prepare a pipeline server in that project, S3 storage, MaaS embedding and generation models,
and a Milvus, PGVector or Neo4j database. Add the corresponding secrets to the same project;
the UI walkthrough also requires Connections that appear in the dashboard selectors.

Each walkthrough starts with its setup checklist. See [prerequisites](docs/prerequisites.md) for
project creation, Connection setup, required secret keys and ASR requirements.

For cluster installation and configuration, use the
[Red Hat OpenShift AI Self-Managed 3.5 documentation](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.5).
The walkthroughs link to the relevant product setup procedures.

## More information

- [Data preparation and benchmark format](data/README.md)
- [Compatibility](docs/compatibility.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Validation and acceptance checklist](docs/validation.md)
- [Local development checks](docs/run-via-code.md#local-development-checks)

A complete product walkthrough with recorded optimization/indexing runs and a grounded answer
remains to be documented. Public corpus redistribution clearance and listening review remain
pending. Helper code is Apache-2.0; corpus rights are separate. See [NOTICE](NOTICE) and
[data provenance](data/rag/audio/sample/README.md).
