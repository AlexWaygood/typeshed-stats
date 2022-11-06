"""Command-line interface."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable, Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal, TypeAlias, cast, get_args

from .gather import PackageName, PackageStats, gather_stats, tmpdir_typeshed
from .serialize import stats_to_csv, stats_to_html, stats_to_json, stats_to_markdown

__all__ = ["OutputOption", "SUPPORTED_EXTENSIONS", "main"]


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
    HTML = ".html", cast(_CF, stats_to_html)

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
        with writefile.open("w", newline=newline, encoding="utf-8") as f:
            f.write(formatted_stats)
        logger.info(f'Output successfully written to "{writefile}"!')


_LoggingLevels: TypeAlias = Literal[
    "NOTSET", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
]


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
        "--log",
        choices=get_args(_LoggingLevels),
        default="INFO",
        help="Specify the level of logging (defaults to logging.INFO)",
        dest="logging_level",
    )

    output_options = parser.add_mutually_exclusive_group()
    output_options.add_argument(
        "--pprint",
        action="store_const",
        const=OutputOption.PPRINT,
        dest="output_option",
        help="Pretty-print Python representations of the data (default output)",
    )
    output_options.add_argument(
        "--to-json",
        action="store_const",
        const=OutputOption.JSON,
        dest="output_option",
        help="Print output as JSON to the terminal",
    )
    output_options.add_argument(
        "--to-csv",
        action="store_const",
        const=OutputOption.CSV,
        dest="output_option",
        help="Print output in csv format to the terminal",
    )
    output_options.add_argument(
        "--to-markdown",
        action="store_const",
        const=OutputOption.MARKDOWN,
        dest="output_option",
        help="Print output as formatted MarkDown to the terminal",
    )
    output_options.add_argument(
        "--to-html",
        action="store_const",
        const=OutputOption.HTML,
        dest="output_option",
        help="Print output as formatted HTML to the terminal",
    )
    output_options.add_argument(
        "-f",
        "--to-file",
        type=Path,
        help=(
            f"Write output to WRITEFILE instead of printing to the terminal."
            f" The file format will be inferred by the file extension."
            f" The file extension must be one of {SUPPORTED_EXTENSIONS}."
        ),
        dest="writefile",
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

    typeshed_options = parser.add_mutually_exclusive_group(required=True)
    typeshed_options.add_argument(
        "-t",
        "--typeshed-dir",
        type=Path,
        help="Path to a local clone of typeshed, to be used as the basis for analysis",
    )
    typeshed_options.add_argument(
        "-d",
        "--download-typeshed",
        action="store_true",
        help=(
            "Download a fresh copy of typeshed into a temporary directory,"
            " and use that as the basis for analysis"
        ),
    )

    return parser


# Has to be a dataclass (attrs does class-level defaults differently)
@dataclass(init=False)
class _CmdArgs:
    logging_level: _LoggingLevels
    packages: list[str]
    typeshed_dir: Path | None
    download_typeshed: bool
    overwrite: bool
    writefile: Path | None
    # OutputOption defaults to PPRINT if no argument was specified on the command line
    output_option: OutputOption = OutputOption.PPRINT


def _determine_output_option(
    args: _CmdArgs, *, parser: argparse.ArgumentParser
) -> OutputOption:
    writefile = args.writefile
    if not writefile:
        return args.output_option
    if not writefile.suffix:
        parser.error(f"{writefile!r} has no file extension!")
    if writefile.suffix not in SUPPORTED_EXTENSIONS:
        parser.error(
            f"Unrecognised file extension {writefile.suffix!r} passed to --file"
            f" (choose from {SUPPORTED_EXTENSIONS})"
        )
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
    return OutputOption.from_file_extension(writefile.suffix)


def _validate_packages(
    package_names: list[str], typeshed_dir: Path, *, parser: argparse.ArgumentParser
) -> None:
    stubs_dir = typeshed_dir / "stubs"
    for package_name in package_names:
        if package_name != "stdlib":
            package_dir = stubs_dir / package_name
            if not (package_dir.exists() and package_dir.is_dir()):
                parser.error(f"{package_name!r} does not have stubs in typeshed!")


def _validate_typeshed_dir(
    typeshed_dir: Path, *, parser: argparse.ArgumentParser
) -> None:
    for folder in typeshed_dir, (typeshed_dir / "stdlib"), (typeshed_dir / "stubs"):
        if not (folder.exists() and folder.is_dir()):
            parser.error(f'"{typeshed_dir}" is not a valid typeshed directory')


def _setup_logger(str_level: _LoggingLevels) -> logging.Logger:
    assert str_level in get_args(_LoggingLevels)
    logger = logging.getLogger("typeshed_stats")
    level = getattr(logging, str_level)
    assert isinstance(level, int)
    logger.setLevel(level)
    handler = logging.StreamHandler()
    handler.setLevel(level)
    logger.addHandler(handler)
    return logger


def _run(argv: Sequence[str] | None = None) -> None:
    parser = _get_argument_parser()
    args: _CmdArgs = parser.parse_args(argv, namespace=_CmdArgs())
    logger = _setup_logger(args.logging_level)

    with ExitStack() as stack:
        if args.download_typeshed:
            logger.info("Cloning typeshed into a temporary directory...")
            typeshed_dir = stack.enter_context(tmpdir_typeshed())
        else:
            assert args.typeshed_dir is not None
            typeshed_dir = args.typeshed_dir
            _validate_typeshed_dir(typeshed_dir, parser=parser)

        packages: list[str] | None = args.packages or None
        if packages:
            _validate_packages(packages, typeshed_dir, parser=parser)

        output_option = _determine_output_option(args, parser=parser)

        logger.info("Gathering stats...")
        stats = gather_stats(packages, typeshed_dir=typeshed_dir)

    logger.info("Formatting stats...")
    formatted_stats = output_option.convert(stats)
    logger.info("Writing stats...")
    _write_stats(formatted_stats, args.writefile, logger)


def main(argv: Sequence[str] | None = None) -> None:
    """CLI entry point."""
    try:
        _run(argv)
    except KeyboardInterrupt:
        sys.stderr.write("Interrupted!")
        code = 2
    else:
        code = 0
    raise SystemExit(code)
