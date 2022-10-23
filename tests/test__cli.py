import argparse
import contextlib
import logging
from collections.abc import Sequence
from pathlib import Path
from unittest import mock

import aiohttp
import pytest
from pytest_subtests import SubTests  # type: ignore[import]

import typeshed_stats._cli
import typeshed_stats.gather
from typeshed_stats._cli import (
    SUPPORTED_EXTENSIONS,
    OutputOption,
    _CmdArgs,
    _Options,
    _validate_options,
    main,
)
from typeshed_stats.gather import PackageStats

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


def test_pprinting_conversion(
    random_PackageStats_sequence: Sequence[PackageStats],
) -> None:
    # No point in testing the exact type of the output here,
    # it's an implementation detail
    # Just test that it works without raising an exception
    assert OutputOption.PPRINT.convert(random_PackageStats_sequence) is not None


def test_each_output_option_has_code_written_for_it(
    capsys: pytest.CaptureFixture[str],
    random_PackageStats_sequence: Sequence[PackageStats],
    typeshed: Path,
    subtests: SubTests,
) -> None:
    options_to_output = {}
    with mock.patch.object(
        typeshed_stats._cli, "gather_stats", return_value=random_PackageStats_sequence
    ):
        with pytest.raises(SystemExit):
            main(["--typeshed-dir", str(typeshed), "--pprint"])
        pprint_output = capsys.readouterr().out.strip()
        for option in OutputOption:
            if option is OutputOption.PPRINT:
                continue
            with pytest.raises(SystemExit):
                main(["--typeshed-dir", str(typeshed), f"--to-{option.name.lower()}"])
            options_to_output[option] = capsys.readouterr().out.strip()

    for option, output in options_to_output.items():
        with subtests.test(option=option.name):
            assert pprint_output not in output
            assert output != pprint_output

    num_different_outputs = len({pprint_output, *options_to_output.values()})
    expected_num_different_outputs = len(OutputOption)
    assert num_different_outputs == expected_num_different_outputs


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
        ["--to-html", "foo"],
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


NON_FILE_OUTPUT_OPTIONS = ["--pprint"] + [
    f"--to-{member.name.lower()}"
    for member in OutputOption
    if member is not OutputOption.PPRINT
]


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


# =============================================
# Tests for logging during the script execution
# =============================================


@pytest.mark.parametrize(
    ("logging_level", "logging_expected"),
    [
        (logging.NOTSET, False),
        (logging.DEBUG, True),
        (logging.INFO, True),
        (logging.WARNING, False),
        (logging.ERROR, False),
        (logging.CRITICAL, False),
    ],
)
def test_logs_to_terminal_with_info_or_lower(
    logging_level: int,
    logging_expected: bool,
    random_PackageStats_sequence: Sequence[PackageStats],
    caplog: pytest.LogCaptureFixture,
) -> None:
    options = _Options(["boto"], Path("."), OutputOption.PPRINT, None, logging_level)
    with (
        pytest.raises(SystemExit),
        mock.patch.object(typeshed_stats._cli, "_get_options", return_value=options),
        mock.patch.object(typeshed_stats._cli, "_write_stats", return_value=None),
        mock.patch.object(
            typeshed_stats._cli,
            "gather_stats",
            return_value=random_PackageStats_sequence,
        ),
    ):
        main()
    logging_occurred = bool(caplog.text.strip())
    assert logging_occurred is logging_expected


# ============================
# Tests for exception-handling
# ============================


def _exception_handling_test_helper(raised_exception: BaseException) -> None:
    options = _Options(["boto"], Path("."), OutputOption.PPRINT, None, logging.CRITICAL)
    with (
        mock.patch.object(
            aiohttp, "ClientSession", return_value=contextlib.nullcontext()
        ),
        mock.patch.object(typeshed_stats._cli, "_get_options", return_value=options),
        mock.patch.object(
            typeshed_stats.gather,
            "gather_stats_on_package",
            side_effect=raised_exception,
        ),
    ):
        main()


def test_KeyboardInterrupt_caught(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        _exception_handling_test_helper(KeyboardInterrupt())
    stderr = capsys.readouterr().err
    num_stderr_lines = len(stderr.strip().splitlines())
    assert num_stderr_lines == 1
    assert "Interrupted!" in stderr
    return_code = exc_info.value.code
    assert return_code == 2


def test_other_exceptions_not_caught() -> None:
    # TODO: Why can't I use capsys to assert that the number of stderr lines is > 1??
    with pytest.raises(KeyError):
        _exception_handling_test_helper(KeyError())
