"""Build a local evidence checklist from sample metadata, run receipts and reviewed answers."""

import argparse
from pathlib import Path

from lib.sample import (
    ROOT,
    cli,
    load_sample,
    read_json,
    render_config_questions,
    require,
    sha256,
    write_json,
)
from run_experiment import configuration, read_env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--optimization-receipt", type=Path)
    parser.add_argument("--indexing-receipt", type=Path)
    parser.add_argument("--pattern", type=Path)
    parser.add_argument(
        "--answers", type=Path, help="Reviewed responses in the format emitted by --answer-template"
    )
    parser.add_argument("--answer-template", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "work/evidence.json")
    args = parser.parse_args()
    config = configuration(read_env(args.env_file))
    manifest, files, _, holdout = load_sample(config["profile"], dataset_dir=config["dataset_dir"])
    questions = render_config_questions(holdout, config)
    if args.answer_template:
        require(
            not args.answer_template.exists(), "Answer worksheet exists; use a new path to preserve reviews"
        )
        write_json(
            args.answer_template,
            [
                {
                    "question": row["question"],
                    "answer": "",
                    "source_keys": [],
                    "supporting_excerpt": "",
                    "factual_pass": None,
                    "source_pass": None,
                    "review_status": "pending",
                }
                for row in questions
            ],
        )
    runs = {}
    for kind in ("optimization", "indexing"):
        path = getattr(args, f"{kind}_receipt")
        if path:
            receipt = read_json(path)
            require(receipt["kind"] == kind, f"Wrong receipt kind: {path}")
            runs[kind] = {
                key: receipt[key]
                for key in (
                    "pipeline_name",
                    "pipeline_id",
                    "pipeline_version_id",
                    "run_id",
                    "state",
                    "params_sha256",
                )
            }
            for key in ("pipeline_source", "package_path", "package_sha256"):
                if key in receipt:
                    runs[kind][key] = receipt[key]
    answers = read_json(args.answers) if args.answers else []
    expected = {row["question"]: set(row["correct_answer_document_keys"]) for row in questions}
    if args.answers:
        require(
            isinstance(answers, list) and len(answers) == len(expected), "Review every held-out question once"
        )
        require(
            {row["question"] for row in answers} == set(expected),
            "Answers do not match fixed holdout questions",
        )
        for row in answers:
            require(row["review_status"] == "reviewed", "Every answer must be reviewed against the recording")
            require(
                type(row["factual_pass"]) is bool and type(row["source_pass"]) is bool,
                "Set pass/fail explicitly",
            )
            if row["source_pass"]:
                require(isinstance(row["source_keys"], list), "source_keys must be a list")
                require(
                    bool(expected[row["question"]] & set(row["source_keys"])),
                    "Passing source must cite expected audio",
                )
                require(
                    bool(row["supporting_excerpt"].strip()), "Passing source requires a supporting excerpt"
                )
            require(bool(row["answer"].strip()), "Record the observed answer, including any abstention")
    write_json(
        args.output,
        {
            "schema_version": 1,
            "status": "local_checklist_not_a_product_certification",
            "profile": config["profile"],
            "rights_status": manifest["rights_status"],
            "label_review_status": manifest["label_review_status"],
            "corpus": {
                "clips": len(files),
                "bytes": sum(f["bytes"] for f in files),
                "seconds": sum(f["duration_seconds"] for f in files),
                "sha256": {f["object_key"]: f["sha256"] for f in files},
            },
            "runs": runs,
            "selected_pattern_sha256": sha256(args.pattern) if args.pattern else None,
            "holdout": {
                "total": len(holdout),
                "reviewed": len(answers),
                "factual_pass": sum(row["factual_pass"] for row in answers),
                "source_pass": sum(row["source_pass"] for row in answers),
                "answers": answers,
            },
            "still_required": [
                "Record RHOAI/OCP/DSPA versions, execution-image/modelcar digests and ASR model revision",
                "Verify full audio coverage, transcripts, selected collection, metrics and worked Q&A",
                "Record M4A, UI, CPU/GPU and disconnected limitations from actual product runs",
                "Review evidence for private information before sharing",
            ],
        },
    )
    print(f"Wrote local evidence checklist: {args.output}")


if __name__ == "__main__":
    cli(main)
