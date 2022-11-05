import csv
import io
import json
import re
import sys
from collections.abc import Iterator, Sequence
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

import markdown
import pytest
from bs4 import BeautifulSoup
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
        typeshed_stats._cli,
        "gather_stats",
        autospec=True,
        return_value=random_PackageStats_sequence,
    ):
        yield


def assert_returncode_0(args: list[str]) -> None:
    """Assert the return code is 0 when running `main` with the specified args."""
    with pytest.raises(SystemExit) as exc_info:
        main(args)
    code = exc_info.value.code
    assert code == 0


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


def _OutputOption_to_argparse(option: OutputOption) -> str:
    return f"--to-{option.name.lower()}"


# ===============================
# Tests for the OutputOption enum
# ===============================


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
    assert_returncode_0(args + ["--pprint"])
    pprint_output = capsys.readouterr().out.strip()
    for option in OutputOption:
        if option is OutputOption.PPRINT:
            continue
        assert_returncode_0(args + [_OutputOption_to_argparse(option)])
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
        pytest.param(["--foo"], id="Unknown_argument"),
        # --overwrite has a store_true action
        pytest.param(["--overwrite", "foo"], id="Bad_use_of_overwrite"),
        # tests for --log
        pytest.param(["--log", "foo"], id="Unknown_log_option1"),
        pytest.param(["--log", "getLogger"], id="Unknown_log_option2"),
        # tests for the output_options group individually (except --to-file)
        pytest.param(["--pprint", "foo"], id="Bad_use_of_pprint"),
        pytest.param(["--to-json", "foo"], id="Bad_use_of_to_json"),
        pytest.param(["--to-csv", "foo"], id="Bad_use_of_to_csv"),
        pytest.param(["--to-markdown", "foo"], id="Bad_use_of_to_markdown"),
        pytest.param(["--to-html", "foo"], id="Bad_use_of_to_html"),
        # tests for the output_options group in combination
        pytest.param(["--pprint", "--to-csv"], id="Multiple_output_options1"),
        pytest.param(["--to-csv", "--to-markdown"], id="Multiple_output_options2"),
        pytest.param(
            ["--to-csv", "--to-json", "--to-markdown"], id="Multiple_output_options3"
        ),
        # tests for the --to-file option
        pytest.param(["--to-file", "bar"], id="to_file_with_no_file_extension"),
        pytest.param(
            ["--to-file", "bar.xml"], id="to_file_with_unknown_file_extension"
        ),
        pytest.param(
            ["--to-csv", "--to-file", "bar.csv"], id="to_file_with_other_output_option"
        ),
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

    patches_to_apply = [
        ("get_package_status", PackageStatus.UP_TO_DATE),
        ("get_stubtest_setting", StubtestSetting.MISSING_STUBS_IGNORED),
        ("get_pyright_strictness", PyrightSetting.STRICT_ON_SOME_FILES),
    ]

    with ExitStack() as stack:
        for function_name, return_value in patches_to_apply:
            stack.enter_context(
                mock.patch.object(
                    typeshed_stats.gather,
                    function_name,
                    autospec=True,
                    return_value=return_value,
                )
            )

        for description, expected_len, args in params:
            with subtests.test(description=description):
                assert_returncode_0(args)
                out = capsys.readouterr().out.strip()
                results = eval(out, vars(typeshed_stats.gather) | globals())
                assert isinstance(results, dict)
                assert len(results) == expected_len
                assert all(isinstance(key, str) for key in results)
                assert all(
                    isinstance(value, PackageStats) for value in results.values()
                )
                assert results["foo"].package_name == "foo"


def test_invalid_packages_given(
    args: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    message = "'boto' does not have stubs in typeshed!"
    assert_argparsing_fails(args + ["boto"], capsys=capsys, failure_message=message)


@pytest.mark.usefixtures("mocked_gather_stats")
def test_passing_stdlib_as_package(args: list[str]) -> None:
    assert_returncode_0(args + ["stdlib"])


# ===================================
# Tests for --to-file and --overwrite
# ===================================


class TestToFileOption:
    @pytest.fixture(autouse=True)
    def _setup(
        self, tmp_path: Path, args: list[str], capsys: pytest.CaptureFixture[str]
    ) -> Iterator[None]:
        self._dir = tmp_path
        self._args = args
        self._capsys = capsys
        yield
        del self._dir, self._args, self._capsys

    def test_to_file_fails_if_parent_doesnt_exist(self) -> None:
        file_in_fictitious_dir = self._dir / "fiction" / "foo.json"
        args = self._args + ["--to-file", str(file_in_fictitious_dir)]
        message = "does not exist as a directory!"
        assert_argparsing_fails(args, capsys=self._capsys, failure_message=message)

    def test_to_file_fails_if_parent_is_not_directory(self) -> None:
        file = self._dir / "file"
        file.write_text("", encoding="utf-8")
        writefile = file / "file2.json"
        args = self._args + ["--to-file", str(writefile)]
        message = "does not exist as a directory!"
        assert_argparsing_fails(args, capsys=self._capsys, failure_message=message)

    def test_to_file_fails_if_file_exists(self) -> None:
        # Setup the case where --overwrite=False,
        # and --to-file points to an already existing file
        file_name = "foo.json"
        already_existing_file = self._dir / file_name
        already_existing_file.write_text("", encoding="utf-8")
        args = self._args + ["--to-file", str(already_existing_file)]
        message = f'{file_name}" already exists!'
        assert_argparsing_fails(args, capsys=self._capsys, failure_message=message)

    @pytest.mark.usefixtures("mocked_gather_stats")
    def test_overwrite_argument(self) -> None:
        # Setup the case where --overwrite=True,
        # and --to-file points to an already existing file
        already_existing_file = self._dir / "foo.json"
        already_existing_file.write_text("", encoding="utf-8")
        args = self._args + ["--to-file", str(already_existing_file), "--overwrite"]
        assert_returncode_0(args)


# ================================
# Tests for various output options
# ================================


@pytest.fixture
def disabled_rich_and_mocked_pprint() -> Iterator[None]:
    with mock.patch.dict("sys.modules", rich=None), mock.patch(
        "pprint.pprint", autospec=True
    ):
        yield


@pytest.mark.usefixtures("mocked_gather_stats")
class TestOutputOptionsPrintingToTerminal:
    @pytest.fixture(autouse=True)
    def _setup(
        self, args: list[str], capsys: pytest.CaptureFixture[str]
    ) -> Iterator[None]:
        self._args = args + ["--log", "CRITICAL"]
        self._capsys = capsys
        yield
        del self._args, self._capsys

    def _assert_outputoption_works(self, option: str) -> None:
        args = self._args + [option]
        assert_returncode_0(args)

    @pytest.mark.fails_inexplicably_in_ci
    def test_to_json(self) -> None:
        self._assert_outputoption_works("--to-json")
        result = json.loads(self._capsys.readouterr().out.strip())
        assert isinstance(result, list)
        assert all(isinstance(item, dict) for item in result)
        assert all(isinstance(item["package_name"], str) for item in result)

    def test_to_csv(self) -> None:
        self._assert_outputoption_works("--to-csv")
        csvfile = io.StringIO(self._capsys.readouterr().out.strip(), newline="")
        stats = list(csv.DictReader(csvfile))
        assert all(isinstance(item, dict) for item in stats)
        assert all(isinstance(item["package_name"], str) for item in stats)

    def test_to_markdown(self) -> None:
        self._assert_outputoption_works("--to-markdown")
        result = self._capsys.readouterr().out.strip()
        markdown.markdown(result)

    def test_to_html(self) -> None:
        self._assert_outputoption_works("--to-html")
        result = self._capsys.readouterr().out.strip()
        soup = BeautifulSoup(result, "html.parser")
        assert bool(soup.find()), "Invalid HTML produced!"

    def test_pprint_rich_available(self) -> None:
        rich_mock = mock.MagicMock()
        with mock.patch.dict(sys.modules, rich=rich_mock):
            self._assert_outputoption_works("--pprint")
        rich_mock.print.assert_called_once()

    @pytest.mark.usefixtures("disabled_rich_and_mocked_pprint")
    def test_pprint_no_rich_available(self) -> None:
        self._assert_outputoption_works("--pprint")
        mocked_pprint = sys.modules["pprint"]
        mocked_pprint.pprint.assert_called_once()

    @pytest.mark.usefixtures("disabled_rich_and_mocked_pprint")
    @pytest.mark.parametrize(
        "option",
        [
            _OutputOption_to_argparse(option)
            for option in OutputOption
            if option is not OutputOption.PPRINT
        ],
    )
    def test_other_options_no_rich_available(self, option: str) -> None:
        self._assert_outputoption_works(option)
        mocked_pprint = sys.modules["pprint"]
        mocked_pprint.pprint.assert_not_called()


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
        pytest.param("NOTSET", False, id="NOTSET_logging_not_expected"),
        pytest.param("DEBUG", True, id="DEBUG_logging_expected"),
        pytest.param("INFO", True, id="INFO_logging_expected"),
        pytest.param("WARNING", False, id="WARNING_logging_not_expected"),
        pytest.param("ERROR", False, id="ERROR_logging_not_expected"),
        pytest.param("CRITICAL", False, id="CRITICAL_logging_not_expected"),
    ],
)
def test_logs_to_terminal_with_info_or_lower(
    args: list[str],
    logging_level: str,
    logging_expected: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    args += ["--log", logging_level]
    assert_returncode_0(args)
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
            autospec=True,
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
