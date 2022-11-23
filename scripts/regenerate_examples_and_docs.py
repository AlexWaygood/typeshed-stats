"""Script for regenerating examples in the examples/ directory."""
import argparse
import shutil
import textwrap
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
        "examples/example.html": markdown.markdown(markdownified_stats) + "\n",
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
    updated_time = datetime.utcnow().strftime("%H:%M UTC on %Y-%m-%d")
    header = textwrap.dedent(
        f"""\
        ---
        hide:
          - navigation
          - footer
        ---

        # Statistics on typeshed's stubs
        <i>These statistics were last updated at: <b>{updated_time}</b>.</i>
        <i>For up-to-date statistics, consider using the CLI instead.</i>
        <hr>
        """
    )
    stats_path = Path("stats_website", "stats.md")
    stats_path.write_text(f"{header}\n{markdown}", encoding="utf-8")
    shutil.copyfile("examples/example.csv", "stats_website/stats_as_csv.csv")
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
    package_dir = Path("src", "typeshed_stats")
    in_root_dir = package_dir.exists() and package_dir.is_dir()
    assert in_root_dir, "This script must be run from the repository root!"
    main()
    raise SystemExit(0)
