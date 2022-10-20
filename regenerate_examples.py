"""Script for regenerating examples in the examples/ directory."""
import argparse
from pathlib import Path

from typeshed_stats import gather_stats, stats_to_csv, stats_to_json, stats_to_markdown


def regenerate_stats(typeshed_dir: Path) -> None:
    """Regenerate the stats, write them to the examples/ directory."""
    print("Gathering stats...")
    stats = gather_stats(typeshed_dir=typeshed_dir)
    print("Formatting stats...")
    path_to_formatted_stats = {
        "examples/example.json": stats_to_json(stats),
        "examples/example.csv": stats_to_csv(stats),
        "examples/example.md": stats_to_markdown(stats),
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
    parser.add_argument("-t", "--typeshed-dir", type=Path, required=True)
    args = parser.parse_args()
    regenerate_stats(args.typeshed_dir)


if __name__ == "__main__":
    main()
    raise SystemExit(0)
