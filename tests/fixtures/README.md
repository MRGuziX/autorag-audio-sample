# Pipeline parameter snapshots

These JSON files contain only names/types/defaults from local `pipelines-components` Python
signatures at `6f11d3e0` (2026-10-23). They exist for offline helper tests, have no executable DAG
and are not product packages or evidence of an installed version.

- Optimization: `pipelines/training/autorag/documents_rag_optimization_pipeline/pipeline.py`
- Indexing: `pipelines/data_processing/autorag/documents_indexing_pipeline/pipeline.py`

An existing locally compiled indexing YAML lacked `preset` despite the source signature exposing it.
The helper tests ensure that such a version mismatch fails visibly. For a live run, the runner
automatically pins, snapshots and validates against the complete installed spec.
