"""Validate bundled or custom corpus integrity without cluster credentials."""

import argparse

from lib.sample import cli, load_sample, require


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="wav-mp3")
    parser.add_argument("--dataset-dir", default="data")
    parser.add_argument(
        "--release", action="store_true", help="Also require cleared data rights and human label review"
    )
    args = parser.parse_args()
    profile = args.profile
    manifest, files, benchmark, holdout = load_sample(profile, dataset_dir=args.dataset_dir)
    if args.release:
        require(manifest["rights_status"] == "cleared", "Public redistribution clearance is pending")
        require(manifest["label_review_status"] == "verified_against_audio", "Human label review is pending")
    print(
        f"{profile}: {len(files)} verified clips, "
        f"{len(benchmark)} optimization / {len(holdout)} holdout questions"
    )
    print(
        f"{sum(f['bytes'] for f in files):,} bytes; {sum(f['duration_seconds'] for f in files):.1f} seconds"
    )
    print(f"Rights: {manifest['rights_status']}; label review: {manifest['label_review_status']}")


if __name__ == "__main__":
    cli(main)
