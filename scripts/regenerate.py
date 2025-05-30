"""Script for regenerating examples and docs."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from contextlib import ExitStack
from pathlib import Path

from typeshed_stats.gather import (
    PackageInfo,
    gather_stats_on_multiple_packages,
    tmpdir_typeshed,
)
from typeshed_stats.serialize import stats_to_csv, stats_to_json, stats_to_markdown


def regenerate_examples(stats: Sequence[PackageInfo]) -> None:
    """Regenerate the examples in the examples/ directory."""
    print("Formatting stats...")
    path_to_formatted_stats = {
        "examples/example.json": stats_to_json(stats),
        "examples/example.csv": stats_to_csv(stats),
        "examples/example.md": stats_to_markdown(stats),
    }
    print("Writing stats...")
    for str_path, formatted_stats in path_to_formatted_stats.items():
        path = Path(str_path)
        newline = "" if path.suffix == ".csv" else None
        path.write_text(formatted_stats, encoding="utf-8", newline=newline)
    print("Examples successfully regenerated!")


def get_stats(args: argparse.Namespace) -> Sequence[PackageInfo]:
    """Get the stats."""
    stats: Sequence[PackageInfo] | None = None
    with ExitStack() as stack:
        if args.download_typeshed:
            print("Cloning typeshed into a temporary directory...")
            args.typeshed_dir = stack.enter_context(tmpdir_typeshed())
        print("Gathering stats...")
        stats = gather_stats_on_multiple_packages(typeshed_dir=args.typeshed_dir)
    assert stats is not None
    return stats


def get_argument_parser() -> argparse.ArgumentParser:
    """Get the argument parser."""
    parser = argparse.ArgumentParser("Script to regenerate examples")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-t", "--typeshed-dir", type=Path)
    group.add_argument("-d", "--download-typeshed", action="store_true")
    return parser


def main() -> None:
    """CLI entry point."""
    parser = get_argument_parser()
    stats = get_stats(parser.parse_args())
    regenerate_examples(stats)


if __name__ == "__main__":
    package_dir = Path("src", "typeshed_stats")
    in_root_dir = package_dir.exists() and package_dir.is_dir()
    assert in_root_dir, "This script must be run from the repository root!"
    main()
    raise SystemExit(0)
