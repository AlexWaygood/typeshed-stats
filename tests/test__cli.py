import csv
import io
import json
import re
from collections.abc import Iterator, Sequence
from pathlib import Path
from unittest import mock

import pytest
from pytest_subtests import SubTests  # type: ignore[import]

import typeshed_stats._cli
import typeshed_stats.gather
from typeshed_stats._cli import SUPPORTED_EXTENSIONS, OutputOption, main
from typeshed_stats.gather import (
    PackageStats,
    PackageStatus,
    PyrightSetting,
    StubtestSetting,
)

# =========
# Utilities
# =========


@pytest.fixture
def args(typeshed: Path) -> list[str]:
    return ["--typeshed-dir", str(typeshed)]


@pytest.fixture
def mocked_gather_stats(
    random_PackageStats_sequence: Sequence[PackageStats],
) -> Iterator[None]:
    with mock.patch.object(
        typeshed_stats._cli, "gather_stats", return_value=random_PackageStats_sequence
    ):
        yield


def assert_argparsing_fails(
    args: list[str],
    *,
    capsys: pytest.CaptureFixture[str] | None = None,
    failure_message: str | None = None,
) -> None:
    """Helper function for lots of argparsing tests."""
    with pytest.raises(SystemExit) as exc_info:
        main(args)
    return_code = exc_info.value.code
    assert return_code == 2
    if failure_message is not None and capsys is not None:
        err = capsys.readouterr().err
        expected_message_found = bool(re.search(failure_message, err))
        assert expected_message_found


# ======================
# Tests for OutputOption
# ======================


@pytest.mark.parametrize("option_name", [option.name for option in OutputOption])
def test_OutputOption(option_name: str) -> None:
    option = OutputOption[option_name]
    extension = option.file_extension
    assert isinstance(extension, str)
    assert extension in SUPPORTED_EXTENSIONS
    assert extension.startswith(".")
    value_repr, option_repr = repr(option.value), repr(option)
    assert value_repr not in option_repr
    assert option.name in option_repr


def test_OutputOption___repr__() -> None:
    actual_repr = repr(OutputOption.PPRINT)
    assert actual_repr == "OutputOption.PPRINT(extension='.txt')"


def test_OutputOption_from_file_extension() -> None:
    markdown_result = OutputOption.from_file_extension(".md")
    assert markdown_result is OutputOption.MARKDOWN
    pprint_result = OutputOption.from_file_extension(".txt")
    assert pprint_result is OutputOption.PPRINT
    with pytest.raises(ValueError, match="Unsupported file extension"):
        OutputOption.from_file_extension(".xml")


def test_pprinting_conversion(
    random_PackageStats_sequence: Sequence[PackageStats],
) -> None:
    # No point in testing the exact type of the output here,
    # it's an implementation detail
    # Just test that it works without raising an exception
    result = OutputOption.PPRINT.convert(random_PackageStats_sequence)
    assert result is not None


@pytest.mark.usefixtures("mocked_gather_stats")
def test_each_output_option_has_code_written_for_it(
    args: list[str],
    capsys: pytest.CaptureFixture[str],
    typeshed: Path,
    subtests: SubTests,
) -> None:
    options_to_output = {}
    with pytest.raises(SystemExit) as exc_info:
        main(args + ["--pprint"])
    return_code = exc_info.value.code
    assert return_code == 0
    pprint_output = capsys.readouterr().out.strip()
    for option in OutputOption:
        if option is OutputOption.PPRINT:
            continue
        with pytest.raises(SystemExit) as exc_info:
            main(args + [f"--to-{option.name.lower()}"])
        return_code = exc_info.value.code
        assert return_code == 0
        options_to_output[option] = capsys.readouterr().out.strip()

    for option, output in options_to_output.items():
        with subtests.test(option=option.name):
            assert pprint_output not in output
            assert output != pprint_output

    num_different_outputs = len({pprint_output, *options_to_output.values()})
    expected_num_different_outputs = len(OutputOption)
    assert num_different_outputs == expected_num_different_outputs


# ============================================
# Misc tests for invalid argument combinations
# ============================================


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
    EXAMPLE_PACKAGE_NAME: str, args: list[str], further_args: list[str]
) -> None:
    args = [EXAMPLE_PACKAGE_NAME, *args, *further_args]
    assert_argparsing_fails(args)


# ========================
# Tests for --typeshed-dir
# ========================


@pytest.mark.parametrize("args", [[], ["foo"], ["--to-csv"]])
def test_argparse_fails_with_no_typeshed_dir_arg(
    capsys: pytest.CaptureFixture[str], args: list[str]
) -> None:
    message = "one of the arguments .+ is required"
    assert_argparsing_fails(args, capsys=capsys, failure_message=message)


def test_invalid_typeshed_dir_arg(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = ["--typeshed-dir", str(tmp_path)]
    message = "is not a valid typeshed directory"
    assert_argparsing_fails(args, capsys=capsys, failure_message=message)


# ==========================
# Tests for passing packages
# ==========================


@pytest.mark.fails_inexplicably_in_ci
def test_passing_packages(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], subtests: SubTests
) -> None:
    typeshed1, typeshed2 = tmp_path / "typeshed1", tmp_path / "typeshed2"

    for typeshed in typeshed1, typeshed2:
        typeshed.mkdir()
        (typeshed / "stdlib").mkdir()
        stubs_dir = typeshed / "stubs"
        stubs_dir.mkdir()
        (stubs_dir / "foo").mkdir()

    (typeshed2 / "stubs" / "bar").mkdir()

    args1 = ["foo", "--typeshed-dir", str(typeshed1), "--log", "CRITICAL"]
    args2 = ["--typeshed-dir", str(typeshed2), "--log", "CRITICAL", "foo", "bar"]

    params = [("one package", 1, args1), ("two packages", 2, args2)]

    for description, expected_len, args in params:
        with subtests.test(description=description):
            with (
                pytest.raises(SystemExit) as exc_info,
                mock.patch.object(
                    typeshed_stats.gather,
                    "get_package_status",
                    return_value=PackageStatus.UP_TO_DATE,
                ),
                mock.patch.object(
                    typeshed_stats.gather,
                    "get_stubtest_setting",
                    return_value=StubtestSetting.MISSING_STUBS_IGNORED,
                ),
                mock.patch.object(
                    typeshed_stats.gather,
                    "get_pyright_strictness",
                    return_value=PyrightSetting.STRICT_ON_SOME_FILES,
                ),
            ):
                main(args)
            return_code = exc_info.value.code
            assert return_code == 0
            out = capsys.readouterr().out
            results = eval(out, vars(typeshed_stats.gather) | globals())
            assert isinstance(results, dict)
            assert len(results) == expected_len
            assert all(isinstance(key, str) for key in results)
            assert all(isinstance(value, PackageStats) for value in results.values())
            assert results["foo"].package_name == "foo"


def test_invalid_packages_given(
    args: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    message = "'boto' does not have stubs in typeshed!"
    assert_argparsing_fails(args + ["boto"], capsys=capsys, failure_message=message)


# ===================================
# Tests for --to-file and --overwrite
# ===================================


def test_to_file_fails_if_parent_doesnt_exist(
    tmp_path: Path, args: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    file_in_fictitious_dir = tmp_path / "fiction" / "foo.json"
    args += ["--to-file", str(file_in_fictitious_dir)]
    message = "does not exist as a directory!"
    assert_argparsing_fails(args, capsys=capsys, failure_message=message)


def test_to_file_fails_if_parent_is_not_directory(
    tmp_path: Path, args: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    file = tmp_path / "file"
    file.write_text("", encoding="utf-8")
    writefile = file / "file2.json"
    args += ["--to-file", str(writefile)]
    message = "does not exist as a directory!"
    assert_argparsing_fails(args, capsys=capsys, failure_message=message)


def test_to_file_fails_if_file_exists(
    tmp_path: Path, args: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    # Setup the case where --overwrite=False,
    # and --to-file points to an already existing file
    file_name = "foo.json"
    already_existing_file = tmp_path / file_name
    already_existing_file.write_text("", encoding="utf-8")
    args += ["--to-file", str(already_existing_file)]
    message = f'{file_name}" already exists!'
    assert_argparsing_fails(args, capsys=capsys, failure_message=message)


@pytest.mark.usefixtures("mocked_gather_stats")
def test_overwrite_argument(args: list[str], tmp_path: Path) -> None:
    # Setup the case where --overwrite=True,
    # and --to-file points to an already existing file
    already_existing_file = tmp_path / "foo.json"
    already_existing_file.write_text("", encoding="utf-8")
    args += ["--to-file", str(already_existing_file), "--overwrite"]
    with pytest.raises(SystemExit) as exc_info:
        main(args)
    return_code = exc_info.value.code
    assert return_code == 0


# ================================
# Tests for various output options
# ================================


@pytest.mark.fails_inexplicably_in_ci
@pytest.mark.usefixtures("mocked_gather_stats")
def test_to_json(args: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    args += ["--log", "CRITICAL", "--to-json"]
    with pytest.raises(SystemExit) as exc_info:
        main(args)
    return_code = exc_info.value.code
    assert return_code == 0
    out = capsys.readouterr().out
    result = json.loads(out)
    assert isinstance(result, list)
    assert all(isinstance(item, dict) for item in result)
    assert all(isinstance(item["package_name"], str) for item in result)


@pytest.mark.usefixtures("mocked_gather_stats")
def test_to_csv(args: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    args += ["--log", "CRITICAL", "--to-csv"]
    with pytest.raises(SystemExit) as exc_info:
        main(args)
    return_code = exc_info.value.code
    assert return_code == 0
    csvfile = io.StringIO(capsys.readouterr().out.strip(), newline="")
    stats = list(csv.DictReader(csvfile))
    assert all(isinstance(item, dict) for item in stats)
    assert all(isinstance(item["package_name"], str) for item in stats)


# ========================
# Tests for --log argument
# ========================


def test_bad_log_argument(args: list[str]) -> None:
    args += ["--log", "FOO"]
    assert_argparsing_fails(args)


@pytest.mark.usefixtures("mocked_gather_stats")
@pytest.mark.parametrize(
    ("logging_level", "logging_expected"),
    [
        ("NOTSET", False),
        ("DEBUG", True),
        ("INFO", True),
        ("WARNING", False),
        ("ERROR", False),
        ("CRITICAL", False),
    ],
)
def test_logs_to_terminal_with_info_or_lower(
    args: list[str],
    logging_level: str,
    logging_expected: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    args += ["--log", logging_level]
    with pytest.raises(SystemExit) as exc_info:
        main(args)
    return_code = exc_info.value.code
    assert return_code == 0
    logging_occurred = bool(caplog.text.strip())
    assert logging_occurred is logging_expected


# ============================
# Tests for exception-handling
# ============================


def test_KeyboardInterrupt_caught(
    args: list[str], typeshed: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args += ["--log", "CRITICAL"]
    with (
        mock.patch.object(
            typeshed_stats.gather,
            "gather_stats_on_package",
            side_effect=KeyboardInterrupt(),
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main(args)

    stderr = capsys.readouterr().err
    num_stderr_lines = len(stderr.strip().splitlines())
    assert num_stderr_lines == 1
    assert "Interrupted!" in stderr
    return_code = exc_info.value.code
    assert return_code == 2
