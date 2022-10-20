import argparse
from pathlib import Path

import pytest

from typeshed_stats._cli import (
    SUPPORTED_EXTENSIONS,
    OutputOption,
    _CmdArgs,
    _Options,
    _validate_options,
)

# ======================
# Tests for OutputOption
# ======================


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


# =============================================
# Tests for the logic in _get_argument_parser()
# =============================================


def assert_argparsing_fails(
    args: list[str],
    parser: argparse.ArgumentParser,
    capsys: pytest.CaptureFixture[str] | None = None,
    *,
    failure_message: str | None = None,
) -> None:
    """Helper function for lots of tests regarding _get_argument_parser()."""
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(args)
    assert exc_info.value.code == 2
    if failure_message is not None and capsys is not None:
        assert failure_message in capsys.readouterr().err


@pytest.mark.parametrize("args", [[], ["foo"], ["--to-csv"]])
def test_argparse_fails_with_no_typeshed_dir_arg(
    parser: argparse.ArgumentParser, capsys: pytest.CaptureFixture[str], args: list[str]
) -> None:
    assert_argparsing_fails(
        args, parser, capsys, failure_message="the following arguments are required"
    )


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
    assert_argparsing_fails(args, parser)


def test_argparse_minimal_arguments(
    parser: argparse.ArgumentParser, LOGGING_LEVELS: tuple[int, ...]
) -> None:
    args = parser.parse_args(["--typeshed-dir", "."])
    assert isinstance(args.packages, list)
    assert len(args.packages) == 0
    assert isinstance(args.typeshed_dir, Path)
    assert args.overwrite is False
    assert args.log in LOGGING_LEVELS
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


# ==========================================
# Tests for the logic in _validate_options()
# ==========================================


@pytest.fixture
def args(parser: argparse.ArgumentParser) -> _CmdArgs:
    return parser.parse_args(["--typeshed-dir", "."], namespace=_CmdArgs())


def assert__validate_options_fails(
    args: _CmdArgs,
    parser: argparse.ArgumentParser,
    capsys: pytest.CaptureFixture[str],
    *,
    failure_message: str,
) -> None:
    """Helper method for lots of tests about _validate_options()."""
    with pytest.raises(SystemExit) as exc_info:
        _validate_options(args, parser=parser)
    assert exc_info.value.code == 2
    assert failure_message in capsys.readouterr().err


def test_to_file_fails_if_parent_doesnt_exist(
    tmp_path: Path,
    args: _CmdArgs,
    parser: argparse.ArgumentParser,
    capsys: pytest.CaptureFixture[str],
) -> None:
    file_in_fictitious_dir = tmp_path / "fiction" / "foo.json"
    args.to_file = file_in_fictitious_dir
    assert__validate_options_fails(
        args, parser, capsys, failure_message="does not exist as a directory!"
    )


def test_to_file_fails_if_parent_is_not_directory(
    tmp_path: Path,
    args: _CmdArgs,
    parser: argparse.ArgumentParser,
    capsys: pytest.CaptureFixture[str],
) -> None:
    file = tmp_path / "file"
    file.write_text("")
    args.to_file = file / "file2.json"
    assert__validate_options_fails(
        args, parser, capsys, failure_message="does not exist as a directory!"
    )


def test_to_file_fails_if_file_exists(
    tmp_path: Path,
    args: _CmdArgs,
    parser: argparse.ArgumentParser,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Setup the case where --overwrite=False,
    # and --to-file points to an already existing file
    already_existing_file = tmp_path / "foo.json"
    already_existing_file.write_text("")
    args.to_file = already_existing_file

    assert__validate_options_fails(
        args, parser, capsys, failure_message='foo.json" already exists!'
    )


def test_invalid_typeshed_dir_arg(
    tmp_path: Path,
    args: _CmdArgs,
    parser: argparse.ArgumentParser,
    capsys: pytest.CaptureFixture[str],
) -> None:
    args.typeshed_dir = tmp_path
    assert__validate_options_fails(
        args, parser, capsys, failure_message="is not a valid typeshed directory"
    )


def test_invalid_packages_given(
    typeshed: Path,
    args: _CmdArgs,
    parser: argparse.ArgumentParser,
    capsys: pytest.CaptureFixture[str],
) -> None:
    args.typeshed_dir = typeshed
    args.packages = ["boto"]
    assert__validate_options_fails(
        args, parser, capsys, failure_message="'boto' does not have stubs in typeshed!"
    )


def test_arg_validation_minimal_options(
    typeshed: Path,
    args: _CmdArgs,
    parser: argparse.ArgumentParser,
    LOGGING_LEVELS: tuple[int, ...],
) -> None:
    (typeshed / "stubs" / "boto").mkdir()
    args.typeshed_dir = typeshed
    options = _validate_options(args, parser=parser)
    assert isinstance(options, _Options)
    assert isinstance(options.packages, list)
    assert "stdlib" in options.packages
    assert "boto" in options.packages
    assert options.typeshed_dir == typeshed
    assert options.writefile is None
    assert options.logging_level in LOGGING_LEVELS
    assert options.output_option is OutputOption.PPRINT


@pytest.mark.parametrize(
    ("passed_argument", "expected_result"),
    [("to_json", "JSON"), ("to_csv", "CSV"), ("to_markdown", "MARKDOWN")],
)
def test_output_options(
    typeshed: Path,
    args: _CmdArgs,
    parser: argparse.ArgumentParser,
    passed_argument: str,
    expected_result: str,
) -> None:
    args.typeshed_dir = typeshed
    args.pprint = False
    setattr(args, passed_argument, True)
    options = _validate_options(args, parser=parser)
    assert options.output_option is OutputOption[expected_result]


def test_overwrite_argument(
    tmp_path: Path,
    args: _CmdArgs,
    parser: argparse.ArgumentParser,
    capsys: pytest.CaptureFixture[str],
    typeshed: Path,
) -> None:
    # Setup the case where --overwrite=True,
    # and --to-file points to an already existing file
    already_existing_file = tmp_path / "foo.json"
    already_existing_file.write_text("")
    args.to_file = already_existing_file
    args.overwrite = True
    args.typeshed_dir = typeshed

    options = _validate_options(args, parser=parser)
    assert options.writefile == already_existing_file
