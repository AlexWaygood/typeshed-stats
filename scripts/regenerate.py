"""Script for regenerating examples and docs."""

from __future__ import annotations

import argparse
import builtins
import re
import shutil
import subprocess
import types
from collections.abc import Sequence
from contextlib import ExitStack
from datetime import datetime
from enum import Enum
from functools import cache
from pathlib import Path
from typing import get_args, get_origin

import attrs
import jinja2

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


@cache
def _get_jinja_environment() -> jinja2.Environment:
    return jinja2.Environment(loader=jinja2.FileSystemLoader("scripts/templates"))


def regenerate_stats_markdown_page(stats: Sequence[PackageInfo]) -> None:
    """Regenerate the markdown page used for the static website."""
    formatted_stats = Path("examples", "example.md").read_text(encoding="utf-8")
    updated_time = datetime.utcnow().strftime("%H:%M UTC on %Y-%m-%d")
    total_typeshed_stublines = sum(s.number_of_lines for s in stats)
    template = _get_jinja_environment().get_template("stats.md.jinja")
    page = template.render(
        num_stats=len(stats),
        lines_of_code=total_typeshed_stublines,
        updated_time=updated_time,
        formatted_stats=formatted_stats
    )
    stats_path = Path("stats_website", "stats.md")
    stats_path.write_text(page, encoding="utf-8")
    shutil.copyfile("examples/example.csv", "stats_website/stats_as_csv.csv")
    print("Docs page successfully regenerated!")


def get_field_description(typ: object) -> str:
    """Get a description of the type of a field in an `attrs` class.

    A helper function for the `gather.md.jinja` template.
    """
    if isinstance(typ, types.UnionType):
        return r" \| ".join(map(get_field_description, get_args(typ)))
    if isinstance(typ, types.GenericAlias):
        return (
            get_field_description(get_origin(typ))
            + "["
            + ", ".join(map(get_field_description, get_args(typ)))
            + "]"
        )
    if isinstance(typ, type):
        typ_name = typ.__name__
        if typ_name in typeshed_stats.gather.__all__:
            return f"[`{typ_name}`][typeshed_stats.gather.{typ_name}]"
        if typ_name in dir(builtins):
            return f"[`{typ_name}`][{typ_name}]"
        if typ is Path:
            return "[`Path`][pathlib.Path]"
        if typ is types.NoneType:  # noqa: E721
            return "[`None`][None]"
        return f"`{typ_name}`"
    return f"`{typ}`"


def regenerate_gather_api_docs() -> None:
    """Regenerate the API docs for `typeshed_stats/gather.py`."""
    template = _get_jinja_environment().get_template("gather.md.jinja")
    rendered = template.render(
        gather=typeshed_stats.gather,
        is_enum=lambda x: isinstance(x, type) and issubclass(x, Enum),
        attrs=attrs,
        get_field_description=get_field_description,
    )
    docs = re.sub(r"\n{3,}", "\n\n", rendered).strip() + "\n"
    Path("stats_website", "gather.md").write_text(docs, encoding="utf-8")
    print("API docs successfully regenerated for `typeshed_stats.gather`!")


def regenerate_cli_docs() -> None:
    """Regenerate the CLI docs."""
    help_result = subprocess.run(
        ["typeshed-stats", "--help"], text=True, capture_output=True
    )
    template = _get_jinja_environment().get_template("cli.md.jinja")
    docs = template.render(cli_help=help_result.stdout) + "\n"
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
