"""Command-line interface."""

import logging
from collections.abc import Callable, Sequence
from enum import Enum
from pathlib import Path
from typing import Literal, NamedTuple

from .api import (
    PackageName,
    PackageStats,
    gather_stats,
    stats_to_csv,
    stats_to_json,
    stats_to_markdown,
)

__all__ = ["OutputOption", "SUPPORTED_EXTENSIONS", "main"]


def _format_stats_for_pprinting(
    stats: Sequence[PackageStats],
) -> dict[PackageName, PackageStats]:
    # *Don't* stringify this one
    # It makes it harder for pprint or rich to format it nicely
    return {info_bundle.package_name: info_bundle for info_bundle in stats}


class OutputOption(Enum):
    """Enumeration of the different output options on the command line."""

    PPRINT = ".txt", _format_stats_for_pprinting
    JSON = ".json", stats_to_json
    CSV = ".csv", stats_to_csv
    MARKDOWN = ".md", stats_to_markdown

    @property
    def file_extension(self) -> str:
        """File extension associated with this file type."""
        return self.value[0]  # type: ignore[no-any-return]

    def convert(self, stats: Sequence[PackageStats]) -> object:
        """Convert a sequence of `PackageStats` objects into the specified format."""
        converter_function = self.value[1]
        return converter_function(stats)

    def __repr__(self) -> str:
        """repr(self)."""
        return f"OutputOption.{self.name}(extension={self.file_extension})"


SUPPORTED_EXTENSIONS = [option.file_extension for option in OutputOption]


def _format_stats(
    stats: Sequence[PackageStats],
    output_option: OutputOption | Literal["PPRINT", "JSON", "CSV", "MARKDOWN"],
) -> object:
    if not isinstance(output_option, OutputOption):
        output_option = OutputOption[output_option]
    return output_option.convert(stats)


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


class _Options(NamedTuple):
    """The return value of `_get_options()`.

    A tuple representing the options specified by a user on the command line.
    """

    packages: list[str]
    typeshed_dir: Path
    output_option: OutputOption
    writefile: Path | None
    logging_level: int


# Ignore flake8 complaining about the function getting too complex.
# I'd rather keep all argument-parsing logic in one place.
def _get_options() -> _Options:  # noqa: C901
    """Parse options passed on the command line."""
    import argparse
    import os

    def _valid_log_argument(arg: str) -> int:
        try:
            return int(getattr(logging, arg.upper()))
        except AttributeError:
            raise argparse.ArgumentTypeError(f"Invalid logging level {arg!r}")

    parser = argparse.ArgumentParser(description="Script to gather stats on typeshed")
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
        type=Path,
        help=(
            f"File to write output to. Extension must be one of {SUPPORTED_EXTENSIONS}"
        ),
    )

    args = parser.parse_args()
    writefile: Path | None = args.to_file

    if writefile:
        suffix = writefile.suffix
        try:
            output_option = next(
                option for option in OutputOption if option.file_extension == suffix
            )
        except StopIteration:
            raise TypeError(
                f"Unrecognised file extension {suffix!r} passed to --file"
                f" (choose from {SUPPORTED_EXTENSIONS})"
            ) from None
        if writefile.exists() and not args.overwrite:
            raise TypeError(f'"{writefile}" already exists!')
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
        if not folder.exists() and folder.is_dir():
            raise TypeError(f'"{typeshed_dir}" is not a valid typeshed directory')

    packages = args.packages or os.listdir(stubs_dir) + ["stdlib"]

    return _Options(packages, typeshed_dir, output_option, writefile, args.log)


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
    formatted_stats = _format_stats(stats, output_option)
    _write_stats(formatted_stats, writefile, logger)


def main() -> None:
    """CLI entry point."""
    try:
        _run()
    except KeyboardInterrupt:
        print("Interrupted!")
        code = 1
    else:
        code = 0
    raise SystemExit(code)
