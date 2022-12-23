"""Script for regenerating examples and docs."""

from __future__ import annotations

import argparse
import builtins
import shutil
import subprocess
import textwrap
import types
from collections.abc import Sequence
from contextlib import ExitStack
from datetime import datetime
from enum import Enum
from functools import partial
from pathlib import Path
from typing import get_args, get_origin

import attrs
import tabulate

import typeshed_stats.gather
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
    for path, formatted_stats in path_to_formatted_stats.items():
        newline = "" if Path(path).suffix == ".csv" else None
        with open(path, "w", encoding="utf-8", newline=newline) as f:
            f.write(formatted_stats)
    print("Examples successfully regenerated!")


def regenerate_stats_markdown_page(stats: Sequence[PackageInfo]) -> None:
    """Regenerate the markdown page used for the static website."""
    markdown = Path("examples", "example.md").read_text(encoding="utf-8")
    updated_time = datetime.utcnow().strftime("%H:%M UTC on %Y-%m-%d")
    total_typeshed_stublines = sum(s.number_of_lines for s in stats)
    header = textwrap.dedent(
        f"""\
        ---
        hide:
          - navigation
          - footer
        ---

        <!-- NOTE: This file is generated. Do not edit manually! -->

        # Statistics on typeshed's stubs

        Typeshed currently contains stubs for {len(stats)} packages
        (including the stdlib stubs as a "single package"),
        for a total of {total_typeshed_stublines:,} non-empty lines of code.

        <i>Note: these statistics were last updated at: <b>{updated_time}</b>.</i>
        <i>For up-to-date statistics, consider using [the CLI tool](https://pypi.org/project/typeshed-stats/) instead.</i>
        <hr>
        """
    )
    stats_path = Path("stats_website", "stats.md")
    stats_path.write_text(f"{header}\n{markdown}", encoding="utf-8")
    shutil.copyfile("examples/example.csv", "stats_website/stats_as_csv.csv")
    print("Docs page successfully regenerated!")


generate_table = partial(tabulate.tabulate, tablefmt="github")


def _get_field_description(typ: object) -> str:
    if isinstance(typ, types.UnionType):
        return "|".join(map(_get_field_description, get_args(typ)))
    if isinstance(typ, types.GenericAlias):
        return (
            _get_field_description(get_origin(typ))
            + "["
            + ", ".join(map(_get_field_description, get_args(typ)))
            + "]"
        )
    if isinstance(typ, type):
        typ_name = typ.__name__
        if typ_name in typeshed_stats.gather.__all__:
            return f"[`{typ_name}`][typeshed_stats.gather.{typ_name}]"
        if typ_name in dir(builtins):
            return f"[`{typ_name}`][{typ_name}]"
        if typ_name == "Path":
            return "[`Path`][pathlib.Path]"
        return f"`{typ_name}`"
    return f"`{typ}`"


def regenerate_gather_api_docs() -> None:
    """Regenerate the API docs for `typeshed_stats/gather.py`."""
    docs = textwrap.dedent(
        f"""\
        ---
        hide:
          - footer
          - navigation
        ---

        <!-- NOTE: This file is generated. Do not edit manually! -->

        {typeshed_stats.gather.__doc__}
        """
    )
    for name in typeshed_stats.gather.__all__:
        docs += textwrap.dedent(
            f"""\
            <hr>

            ::: typeshed_stats.gather.{name}
                options:
                  show_root_heading: true

            """
        )
        if name == "PackageName":
            continue
        thing = getattr(typeshed_stats.gather, name)
        if isinstance(thing, type):
            if issubclass(thing, Enum):
                docs += "**Members:**\n\n"
                docs += generate_table(
                    [[f"`{member.name}`", member.__doc__] for member in thing],
                    headers=["Name", "Description"],
                )
            elif attrs.has(thing):
                rows = []
                for field in attrs.fields(thing):
                    typ_description = _get_field_description(field.type)
                    rows.append([f"`{field.name}`", typ_description])
                docs += "**Attributes:**\n\n"
                docs += generate_table(rows, headers=["Name", "Type"])
            docs += "\n"
    docs = docs.strip() + "\n"
    Path("stats_website", "gather.md").write_text(docs, encoding="utf-8")
    print("API docs successfully regenerated for `typeshed_stats.gather`!")


def regenerate_cli_docs() -> None:
    """Regenerate the CLI docs."""
    help_result = subprocess.run(
        ["typeshed-stats", "--help"], text=True, capture_output=True
    )
    docs = textwrap.dedent(
        """\
        ---
        hide:
          - footer
          - navigation
        ---

        <!-- NOTE: This file is generated. Do not edit manually! -->

        To install the CLI, simply run `pip install typeshed-stats[rich]`.
        """
    )
    docs += f"\n```console\n{help_result.stdout}\n```\n"
    Path("stats_website", "cli.md").write_text(docs, encoding="utf-8")
    print("CLI docs successfully regenerated for `typeshed_stats`!")


# I think we need the type: ignore here
# because mypy is worried that ExitStack() might suppress exceptions.
# I guess that's reasonable, thought it's somewhat annoying in this case.
def get_stats(args: argparse.Namespace) -> Sequence[PackageInfo]:  # type: ignore[return]
    """Get the stats."""
    with ExitStack() as stack:
        if args.download_typeshed:
            print("Cloning typeshed into a temporary directory...")
            args.typeshed_dir = stack.enter_context(tmpdir_typeshed())
        print("Gathering stats...")
        return gather_stats_on_multiple_packages(typeshed_dir=args.typeshed_dir)


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
    regenerate_stats_markdown_page(stats)
    regenerate_gather_api_docs()
    regenerate_cli_docs()


if __name__ == "__main__":
    package_dir = Path("src", "typeshed_stats")
    in_root_dir = package_dir.exists() and package_dir.is_dir()
    assert in_root_dir, "This script must be run from the repository root!"
    main()
    raise SystemExit(0)
