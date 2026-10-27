"""Create an integrity manifest for your own audio/ and benchmark.json directory."""

import argparse
import json
import subprocess
from pathlib import Path

from lib.sample import ROOT, cli, load_sample, local_path, require, sha256, write_json


def build_manifest(directory: Path, language: str) -> dict:
    files = []
    audio_dir = directory / "audio"
    require(audio_dir.is_dir(), f"Create {audio_dir} and place your clips there")
    for path in sorted(audio_dir.iterdir()):
        require(
            path.is_file() and path.suffix.lower() in {".wav", ".mp3", ".m4a"},
            f"Unexpected audio entry: {path}",
        )
        require(path.resolve().is_relative_to(directory.resolve()), f"Audio symlink leaves dataset: {path}")
        require(path.suffix == path.suffix.lower(), f"Use lowercase extensions: {path.name}")
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=codec_name,sample_rate,channels",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        require(result.returncode == 0, f"ffprobe failed for {path.name}: {result.stderr.strip()}")
        probe = json.loads(result.stdout)
        require(bool(probe.get("streams")), f"No audio stream found in {path.name}")
        stream = next((s for s in probe["streams"] if "sample_rate" in s), None)
        require(stream is not None, f"No audio stream found in {path.name}")
        files.append(
            {
                "id": path.name,
                "path": f"audio/{path.name}",
                "object_key": f"audio/{path.name}",
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
                "duration_seconds": float(probe["format"]["duration"]),
                "codec": stream["codec_name"],
                "sample_rate": int(stream["sample_rate"]),
                "channels": stream["channels"],
                "language": language,
                "source": "User-supplied audio; record authorship and license in your dataset README",
            }
        )
    require(bool(files), "Add at least one audio clip")
    return {
        "schema_version": 1,
        "rights_status": "pending",
        "label_review_status": "pending",
        "files": files,
        "profiles": {
            "custom": {
                "files": [entry["id"] for entry in files],
                "benchmark": "benchmark.json",
                "holdout": "holdout.json" if (directory / "holdout.json").is_file() else None,
            }
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--directory", default="samples/user", help="Dataset directory relative to the repository"
    )
    parser.add_argument("--language", required=True, help="Spoken language code, e.g. en or pl")
    parser.add_argument("--replace-manifest", action="store_true")
    args = parser.parse_args()
    directory = local_path(args.directory)
    destination = directory / "manifest.json"
    require(
        not destination.exists() or args.replace_manifest,
        "Manifest exists; review changes and use --replace-manifest",
    )
    manifest = build_manifest(directory, args.language)
    load_sample("custom", root=ROOT, dataset_dir=args.directory, manifest=manifest)
    write_json(destination, manifest)
    print(f"Prepared {len(manifest['files'])} clips: {destination}")
    print(f"In .env set AUTORAG_DATASET_DIR={args.directory}, AUTORAG_PROFILE=custom and a fresh S3 prefix.")


if __name__ == "__main__":
    cli(main)
