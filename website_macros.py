"""Macros and variables for the mkdocs-macros plugin."""

import builtins
import datetime as dt
import json
import subprocess
import types
from enum import Enum
from pathlib import Path
from typing import Any, TypeGuard, get_args, get_origin

import attrs

import typeshed_stats.gather


def define_env(env: Any) -> None:
    """Define environment variables."""
    # Variables needed for cli.md
    help_result = subprocess.run(
        ["typeshed-stats", "--help"], text=True, capture_output=True
    )
    env.variables["cli_help"] = help_result.stdout + "\n"

    # Variables needed for gather.md
    @env.macro  # type: ignore[misc]
    def is_enum(x: object) -> TypeGuard[type[Enum]]:
        return isinstance(x, type) and issubclass(x, Enum)

    @env.macro  # type: ignore[misc]
    def get_field_description(typ: object) -> str:
        """Get a description of the type of a field in an `attrs` class.

        A helper function for the `gather.md.jinja` template.
        """
        if isinstance(typ, types.UnionType):
            return r" \| ".join(map(get_field_description, get_args(typ)))
        if isinstance(typ, types.GenericAlias):
            return (  # type: ignore[no-any-return]
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

    env.variables.update(gather=typeshed_stats.gather, attrs=attrs)

    # Variables needed for stats.md
    with Path("examples", "example.json").open(encoding="utf-8") as f:
        json_stats = json.load(f)

    env.variables.update(
        last_update_time=dt.datetime.utcnow().strftime("%H:%M UTC on %Y-%m-%d"),
        num_packages=len(json_stats),
        formatted_stats=Path("examples", "example.md").read_text(encoding="utf-8"),
        num_lines=sum(s["number_of_lines"] for s in json_stats),
    )
