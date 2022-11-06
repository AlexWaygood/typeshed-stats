"""Script for regenerating examples in the examples/ directory."""
import argparse
from contextlib import ExitStack
from pathlib import Path

import markdown

from typeshed_stats.gather import gather_stats, tmpdir_typeshed
from typeshed_stats.serialize import stats_to_csv, stats_to_json, stats_to_markdown


def regenerate_stats(typeshed_dir: Path) -> None:
    """Regenerate the stats, write them to the examples/ directory."""
    print("Gathering stats...")
    stats = gather_stats(typeshed_dir=typeshed_dir)
    print("Formatting stats...")
    markdownified_stats = stats_to_markdown(stats)
    path_to_formatted_stats = {
        "examples/example.json": stats_to_json(stats),
        "examples/example.csv": stats_to_csv(stats),
        "examples/example.md": markdownified_stats,
        "examples/example.html": markdown.markdown(markdownified_stats),
    }
    print("Writing stats...")
    for path, formatted_stats in path_to_formatted_stats.items():
        newline = "" if Path(path).suffix == ".csv" else None
        with open(path, "w", encoding="utf-8", newline=newline) as f:
            f.write(formatted_stats)
    print("Examples successfully regenerated!")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser("Script to regenerate examples")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-t", "--typeshed-dir", type=Path)
    group.add_argument("-d", "--download-typeshed", action="store_true")
    args = parser.parse_args()
    with ExitStack() as stack:
        if args.download_typeshed:
            print("Cloning typeshed into a temporary directory...")
            args.typeshed_dir = stack.enter_context(tmpdir_typeshed())
        regenerate_stats(args.typeshed_dir)


if __name__ == "__main__":
    main()
    raise SystemExit(0)
