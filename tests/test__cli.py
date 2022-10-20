import argparse
import logging
from pathlib import Path

import pytest

from typeshed_stats._cli import SUPPORTED_EXTENSIONS, OutputOption, _get_argument_parser


@pytest.mark.parametrize("option", list(OutputOption))
def test_OutputOption(option: OutputOption) -> None:
    assert isinstance(option.file_extension, str)
    assert option.file_extension in SUPPORTED_EXTENSIONS
    assert option.file_extension.startswith(".")
    assert repr(option.value) not in repr(option)
    assert option.name in repr(option)


def test_OutputOption___repr__() -> None:
    assert repr(OutputOption.PPRINT) == "OutputOption.PPRINT(extension='.txt')"


def test_OutputOption_from_file_extension() -> None:
    assert OutputOption.from_file_extension(".md") is OutputOption.MARKDOWN
    assert OutputOption.from_file_extension(".txt") is OutputOption.PPRINT
    with pytest.raises(ValueError, match="Unsupported file extension"):
        OutputOption.from_file_extension(".xml")


@pytest.fixture(scope="session")
def parser() -> argparse.ArgumentParser:
    parser = _get_argument_parser()
    assert isinstance(parser, argparse.ArgumentParser)
    return parser


@pytest.mark.parametrize("args", [[], ["foo"], ["--to-csv"]])
def test_argparse_fails_with_no_typeshed_dir_arg(
    parser: argparse.ArgumentParser, capsys: pytest.CaptureFixture[str], args: list[str]
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(args)
    assert exc_info.value.code == 2
    assert "the following arguments are required" in capsys.readouterr().err


@pytest.mark.parametrize(
    "further_args",
    [
        # unknown argument
        ["--foo"],
        # --overwrite has a store_true action
        ["--overwrite", "foo"],
        # tests for --log
        ["--log", "foo"],
        ["--log", "getLogger"],
        # tests for the output_options group individually (except --to-file)
        ["--pprint", "foo"],
        ["--to-json", "foo"],
        ["--to-csv", "foo"],
        ["--to-markdown", "foo"],
        # tests for the output_options group in combination
        ["--pprint", "--to-csv"],
        ["--to-csv", "--to-markdown"],
        ["--to-csv", "--to-json", "--to-markdown"],
        # tests for the --to-file option
        ["--to-file", "bar"],
        ["--to-file", "bar.xml"],
        ["--to-csv", "--to-file", "bar.csv"],
    ],
)
def test_misc_invalid_args(
    parser: argparse.ArgumentParser, EXAMPLE_PACKAGE_NAME: str, further_args: list[str]
) -> None:
    args = [EXAMPLE_PACKAGE_NAME, "--typeshed-dir", "."] + further_args
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(args)
    assert exc_info.value.code == 2


def test_minimal_arguments(parser: argparse.ArgumentParser) -> None:
    args = parser.parse_args(["--typeshed-dir", "."])
    assert isinstance(args.packages, list)
    assert len(args.packages) == 0
    assert isinstance(args.typeshed_dir, Path)
    assert args.overwrite is False
    assert isinstance(args.log, int)
    assert args.log == logging.INFO
    assert not any([args.pprint, args.to_json, args.to_csv, args.to_markdown])
    assert args.to_file is None


@pytest.mark.parametrize(
    ("passed_args", "num_packages"),
    [
        (["foo", "--typeshed-dir", "."], 1),
        (["--typeshed-dir", ".", "--log", "INFO", "foo", "bar"], 2),
    ],
)
def test_passing_packages(
    parser: argparse.ArgumentParser, passed_args: list[str], num_packages: int
) -> None:
    args = parser.parse_args(passed_args)
    assert isinstance(args.packages, list)
    assert all(isinstance(package, str) for package in args.packages)
    assert len(args.packages) == num_packages
    assert isinstance(args.typeshed_dir, Path)


@pytest.mark.parametrize(
    "log_argument", ["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"]
)
def test_log_argument(parser: argparse.ArgumentParser, log_argument: str) -> None:
    args = parser.parse_args(["--typeshed-dir", ".", "--log", log_argument])
    assert isinstance(args.typeshed_dir, Path)
    assert isinstance(args.log, int)


NON_FILE_OUTPUT_OPTIONS = ["--pprint", "--to-json", "--to-csv", "--to-markdown"]


def translate_option(option: str) -> str:
    return option.strip("-").replace("-", "_")


@pytest.mark.parametrize("selected_option", NON_FILE_OUTPUT_OPTIONS)
def test_mutually_exclusive_output_specification(
    parser: argparse.ArgumentParser, selected_option: str
) -> None:
    args = parser.parse_args(["--typeshed-dir", ".", selected_option])
    assert getattr(args, translate_option(selected_option)) is True
    assert not any(
        getattr(args, translate_option(option))
        for option in NON_FILE_OUTPUT_OPTIONS
        if option != selected_option
    )


@pytest.mark.parametrize("extension", SUPPORTED_EXTENSIONS)
def test_to_file_argument(
    parser: argparse.ArgumentParser, EXAMPLE_PACKAGE_NAME: str, extension: str
) -> None:
    filename = f"{EXAMPLE_PACKAGE_NAME}{extension}"
    args = parser.parse_args(["--typeshed-dir", ".", "--to-file", filename])
    assert isinstance(args.to_file, Path)
    assert not any(
        getattr(args, translate_option(option)) for option in NON_FILE_OUTPUT_OPTIONS
    )
