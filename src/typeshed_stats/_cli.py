"""Command-line interface."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Callable, Sequence
from enum import Enum
from pathlib import Path
from typing import Annotated, NamedTuple, TypeAlias, cast

from .gather import PackageName, PackageStats, gather_stats
from .serialize import stats_to_csv, stats_to_json, stats_to_markdown

__all__ = ["OutputOption", "SUPPORTED_EXTENSIONS", "main"]


if sys.version_info < (3, 10):
    raise ImportError("Python 3.10+ is required!")


def _format_stats_for_pprinting(
    stats: Sequence[PackageStats],
) -> dict[PackageName, PackageStats]:
    # *Don't* stringify this one
    # It makes it harder for pprint or rich to format it nicely
    return {info_bundle.package_name: info_bundle for info_bundle in stats}


_CF: TypeAlias = Annotated[
    Callable[[Sequence[PackageStats]], object],
    "Function for converting a sequence of PackageStats into a certain format",
]


class OutputOption(Enum):
    """Enumeration of the different output options on the command line."""

    PPRINT = ".txt", cast(_CF, _format_stats_for_pprinting)
    JSON = ".json", cast(_CF, stats_to_json)
    CSV = ".csv", cast(_CF, stats_to_csv)
    MARKDOWN = ".md", cast(_CF, stats_to_markdown)

    @property
    def file_extension(self) -> str:
        """File extension associated with this file type."""
        return self.value[0]

    def convert(self, stats: Sequence[PackageStats]) -> object:
        """Convert a sequence of `PackageStats` objects into the specified format."""
        converter_function = self.value[1]
        return converter_function(stats)

    def __repr__(self) -> str:
        """repr(self)."""
        return f"OutputOption.{self.name}(extension={self.file_extension!r})"

    @classmethod
    def from_file_extension(cls, extension: str) -> OutputOption:
        """Return the enum member associated with a particular file extension."""
        try:
            return next(member for member in cls if member.file_extension == extension)
        except StopIteration:
            raise ValueError(f"Unsupported file extension {extension!r}") from None


SUPPORTED_EXTENSIONS = {option.file_extension for option in OutputOption}


def _write_stats(
    formatted_stats: object, writefile: Path | None, logger: logging.Logger
) -> None:
    if writefile is None:
        pprint: Callable[[object], None]
        try:
            from rich import print as pprint  # type: ignore[no-redef]
        except ImportError:
            if isinstance(formatted_stats, str):
                pprint = print
            else:
                from pprint import pprint  # type: ignore[no-redef]

        pprint(formatted_stats)
    else:
        newline = "" if writefile.suffix == ".csv" else "\n"
        if not isinstance(formatted_stats, str):
            formatted_stats = str(formatted_stats)
        with writefile.open("w", newline=newline) as f:
            f.write(formatted_stats)
        logger.info(f'Output successfully written to "{writefile}"!')


def _valid_log_argument(arg: str) -> int:
    try:
        return int(getattr(logging, arg.upper()))
    except AttributeError:
        raise argparse.ArgumentTypeError(f"Invalid logging level {arg!r}")


def _valid_writefile_argument(arg: str) -> Path:
    writefile = Path(arg)
    if writefile.suffix not in SUPPORTED_EXTENSIONS:
        raise argparse.ArgumentTypeError(
            f"Unrecognised file extension {writefile.suffix!r} passed to --file"
            f" (choose from {SUPPORTED_EXTENSIONS})"
        )
    return writefile


def _get_argument_parser() -> argparse.ArgumentParser:
    """Parse arguments and do basic argument validation.

    *Don't* do any querying of whether paths actually exist, etc.
    Leave that to _validate_options().
    """
    parser = argparse.ArgumentParser(
        prog="typeshed-stats", description="Tool to gather stats on typeshed"
    )
    parser.add_argument(
        "packages",
        type=str,
        nargs="*",
        action="extend",
        help=(
            "Packages to gather stats on"
            " (defaults to all third-party packages, plus the stdlib)"
        ),
    )
    parser.add_argument(
        "-t",
        "--typeshed-dir",
        type=Path,
        required=True,
        help="Path to the typeshed directory",
    )
    parser.add_argument(
        "-o",
        "--overwrite",
        action="store_true",
        help=(
            "Overwrite the path passed to `--file` if it already exists"
            " (defaults to False)"
        ),
    )
    parser.add_argument(
        "--log",
        type=_valid_log_argument,
        default=logging.INFO,
        help="Specify the level of logging (defaults to logging.INFO)",
    )

    output_options = parser.add_mutually_exclusive_group()
    output_options.add_argument(
        "--pprint",
        action="store_true",
        help="Pretty-print Python representations of the data (default output)",
    )
    output_options.add_argument(
        "--to-json", action="store_true", help="Print output as JSON"
    )
    output_options.add_argument(
        "--to-csv", action="store_true", help="Print output in csv format"
    )
    output_options.add_argument(
        "--to-markdown", action="store_true", help="Print output as formatted MarkDown"
    )
    output_options.add_argument(
        "-f",
        "--to-file",
        type=_valid_writefile_argument,
        help=(
            f"File to write output to. Extension must be one of {SUPPORTED_EXTENSIONS}"
        ),
    )

    return parser


class _CmdArgs:
    packages: list[str]
    typeshed_dir: Path
    overwrite: bool
    log: int
    pprint: bool
    to_json: bool
    to_csv: bool
    to_markdown: bool
    to_file: Path | None


class _Options(NamedTuple):
    """The return value of `_get_options()`.

    A tuple representing the validated options specified by a user on the command line.
    """

    packages: list[str]
    typeshed_dir: Path
    output_option: OutputOption
    writefile: Path | None
    logging_level: int


def _validate_options(args: _CmdArgs, *, parser: argparse.ArgumentParser) -> _Options:
    """After arguments have been parsed by argparse, do some further validation."""
    writefile = args.to_file

    if writefile:
        if not (writefile.parent.exists() and writefile.parent.is_dir()):
            parser.error(
                f'"{writefile}" is an invalid argument:'
                f" {writefile.parent} does not exist as a directory!"
            )
        if writefile.exists() and not args.overwrite:
            parser.error(
                f'"{writefile}" already exists!'
                "\n(Note: use --overwite"
                " if your intention was to overwrite an existing file)"
            )
        # Don't validate the file extension here
        # We already did that in _get_argument_parser
        output_option = OutputOption.from_file_extension(writefile.suffix)
    elif args.to_json:
        output_option = OutputOption.JSON
    elif args.to_csv:
        output_option = OutputOption.CSV
    elif args.to_markdown:
        output_option = OutputOption.MARKDOWN
    else:
        # --pprint is the default if no option in this group was specified
        output_option = OutputOption.PPRINT

    typeshed_dir = args.typeshed_dir
    stubs_dir = typeshed_dir / "stubs"
    for folder in typeshed_dir, (typeshed_dir / "stdlib"), stubs_dir:
        if not (folder.exists() and folder.is_dir()):
            parser.error(f'"{typeshed_dir}" is not a valid typeshed directory')

    for package_name in args.packages:
        if package_name != "stdlib":
            package_dir = stubs_dir / package_name
            if not (package_dir.exists() and package_dir.is_dir()):
                parser.error(f"{package_name!r} does not have stubs in typeshed!")

    packages = args.packages or os.listdir(stubs_dir) + ["stdlib"]

    return _Options(packages, typeshed_dir, output_option, writefile, args.log)


def _get_options() -> _Options:
    """Parse and validate options passed on the command line."""
    parser = _get_argument_parser()
    args: _CmdArgs = parser.parse_args(namespace=_CmdArgs())
    return _validate_options(args, parser=parser)


def _setup_logger(level: int) -> logging.Logger:
    logger = logging.getLogger("typeshed_stats")
    logger.setLevel(level)
    handler = logging.StreamHandler()
    handler.setLevel(level)
    logger.addHandler(handler)
    return logger


def _run() -> None:
    packages, typeshed_dir, output_option, writefile, logging_level = _get_options()
    logger = _setup_logger(logging_level)
    logger.info("Gathering stats...")
    stats = gather_stats(packages, typeshed_dir=typeshed_dir)
    logger.info("Formatting stats...")
    formatted_stats = output_option.convert(stats)
    logger.info("Writing stats...")
    _write_stats(formatted_stats, writefile, logger)


def main() -> None:
    """CLI entry point."""
    try:
        _run()
    except KeyboardInterrupt:
        sys.stderr.write("Interrupted!")
        code = 2
    else:
        code = 0
    raise SystemExit(code)
