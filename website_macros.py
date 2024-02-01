# pyright: reportUnusedFunction=false
"""Macros and variables for the mkdocs-macros plugin."""

import builtins
import csv
import datetime as dt
import shutil
import subprocess
import types
from abc import abstractmethod
from collections.abc import Callable
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, TypeGuard, TypeVar, get_args, get_origin

import attrs
import markdown

import typeshed_stats.gather
import typeshed_stats.serialize

CF = TypeVar("CF", bound=Callable[..., Any])


class Env(Protocol):
    """Protocol representing the `mkdocs_macros.MacrosPlugin` object."""

    variables: dict[str, Any]
    conf: dict[str, Any]

    @abstractmethod
    def macro(self, /, func: CF) -> CF:
        """Register a function as a macro."""


def define_env(env: Env) -> None:
    """Define environment variables."""
    # Variables needed for cli.md
    help_result = subprocess.run(
        ["typeshed-stats", "--help"], text=True, capture_output=True
    )
    env.variables["cli_help"] = help_result.stdout + "\n"

    # Variables needed for serialize.md
    env.variables["serialize"] = typeshed_stats.serialize

    # Variables needed for gather.md
    @env.macro
    def is_enum(x: object) -> TypeGuard[type[Enum]]:
        return isinstance(x, type) and issubclass(x, Enum)

    @env.macro
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
            if typ is types.NoneType:
                return "[`None`][None]"
            return f"`{typ_name}`"
        return f"`{typ}`"

    env.variables.update(gather=typeshed_stats.gather, attrs=attrs)

    # Variables needed for stats.md and stats-csv.md
    stats_as_csv: list[dict[str, str | int]] = []
    with Path("examples", "example.csv").open(newline="", encoding="utf-8") as csvfile:
        for line in csv.DictReader(csvfile):
            row: dict[str, str | int] = {}
            for key, val in line.items():
                if val.isdigit():
                    row[key] = int(val)
                elif key == "upstream_url":
                    row[key] = "(unknown)" if val == "-" else f"[{val}]({val})"
                else:
                    row[key] = val
            stats_as_csv.append(row)

    @env.macro
    def is_int(x: object) -> TypeGuard[int]:
        return isinstance(x, int)

    env.variables.update(
        last_update_time=dt.datetime.utcnow().strftime("%H:%M UTC on %Y-%m-%d"),
        num_packages=len(stats_as_csv),
        formatted_stats=Path("examples", "example.md").read_text(encoding="utf-8"),
        num_lines=sum(int(s["number_of_lines"]) for s in stats_as_csv),
        stats_as_csv=stats_as_csv,
        markdown=markdown,
    )


def on_post_build(env: Env) -> None:
    """Define post-build actions."""
    shutil.copyfile(
        Path("examples", "example.csv"), Path(env.conf["site_dir"], "stats_as_csv.csv")
    )
