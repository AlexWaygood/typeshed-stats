"""Script for regenerating examples in the examples/ directory."""
import argparse
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path

import markdown

from typeshed_stats.gather import gather_stats, tmpdir_typeshed
from typeshed_stats.serialize import stats_to_csv, stats_to_json, stats_to_markdown


def regenerate_examples(typeshed_dir: Path) -> None:
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


def regenerate_docs_page() -> None:
    """Regenerate the markdown page used for the static website."""
    markdown = Path("examples", "example.md").read_text(encoding="utf-8")
    updated_time = datetime.utcnow().strftime("%H:%M on %Y-%m-%d UTC")
    header = (
        "# Stats on typeshed's stubs\n"
        f"<i>Last updated at: <b>{updated_time}</b></i><hr>\n"
    )
    Path("stats_website", "stats.md").write_text(header + markdown, encoding="utf-8")
    print("Docs page successfully regenerated!")


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
        regenerate_examples(args.typeshed_dir)
    regenerate_docs_page()


if __name__ == "__main__":
    main()
    raise SystemExit(0)
