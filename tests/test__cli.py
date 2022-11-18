import csv
import io
import json
import os
import re
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path
from unittest import mock

# Make sure not to import rich or markdown here, since they're optional dependencies
# Some tests assert behaviour that's predicated on these modules not yet being imported
import pytest
from bs4 import BeautifulSoup
from pytest_mock import MockerFixture
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

from .conftest import random_package_name

# =========
# Utilities
# =========


@pytest.fixture
def args(typeshed: Path) -> list[str]:
    return ["--typeshed-dir", str(typeshed)]


@pytest.fixture
def mocked_gather_stats(
    random_PackageStats_sequence: Sequence[PackageStats], mocker: MockerFixture
) -> None:
    mocker.patch.object(
        typeshed_stats._cli,
        "gather_stats",
        autospec=True,
        return_value=random_PackageStats_sequence,
    )


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
        assert expected_message_found, err


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


# ===========================================
# Test that it fails with an unknown argument
# ===========================================


def test_program_fails_with_unknown_argument(args: list[str]) -> None:
    bad_arg = "--foo"
    args.append(bad_arg)
    assert_argparsing_fails(args, failure_message=f"unrecognised arguments: {bad_arg}")


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


@pytest.fixture(params=[1, 2], ids=["one_package", "two_packages"])
def typeshed_with_packages(
    tmp_path: Path, EXAMPLE_PACKAGE_NAME: str, request: pytest.FixtureRequest
) -> Path:
    typeshed = tmp_path
    (typeshed / "stdlib").mkdir()
    stubs_dir = typeshed / "stubs"
    stubs_dir.mkdir()
    (stubs_dir / EXAMPLE_PACKAGE_NAME).mkdir()
    for _ in range(request.param - 1):
        (stubs_dir / random_package_name()).mkdir()
    return typeshed


class TestPassingPackages:
    _capsys: pytest.CaptureFixture[str]
    _guaranteed_package_name: str

    LOGGING_ARGS = ("--log", "CRITICAL")

    @pytest.fixture(autouse=True)
    def _setup_and_teardown(
        self,
        mocker: MockerFixture,
        EXAMPLE_PACKAGE_NAME: str,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        patches_to_apply = [
            ("get_package_status", PackageStatus.UP_TO_DATE),
            ("get_stubtest_setting", StubtestSetting.MISSING_STUBS_IGNORED),
            ("get_pyright_strictness", PyrightSetting.STRICT_ON_SOME_FILES),
        ]

        for function_name, return_value in patches_to_apply:
            mocker.patch.object(
                typeshed_stats.gather,
                function_name,
                autospec=True,
                return_value=return_value,
            )

        mocker.patch.dict(
            vars(self), _guaranteed_package_name=EXAMPLE_PACKAGE_NAME, _capsys=capsys
        )

    def _assert_correct_results_printed_to_stdout(
        self, expected_length_of_results: int
    ) -> None:
        stdout = self._capsys.readouterr().out.replace("\N{ESCAPE}", " ").strip()
        results = eval(stdout, vars(typeshed_stats.gather) | globals())
        assert isinstance(results, dict)
        assert len(results) == expected_length_of_results
        assert all(isinstance(key, str) for key in results)
        assert all(isinstance(value, PackageStats) for value in results.values())
        guaranteed_package_name = self._guaranteed_package_name
        assert results[guaranteed_package_name].package_name == guaranteed_package_name

    def test_passing_packages_before_typeshed_dir(
        self, typeshed_with_packages: Path
    ) -> None:
        packages_to_pass = os.listdir(typeshed_with_packages / "stubs")
        expected_length_of_results = len(packages_to_pass)
        args = [
            *packages_to_pass,
            "--typeshed-dir",
            str(typeshed_with_packages),
            *self.LOGGING_ARGS,
        ]
        assert_returncode_0(args)
        self._assert_correct_results_printed_to_stdout(expected_length_of_results)

    def test_passing_packages_after_typeshed_dir(
        self, typeshed_with_packages: Path
    ) -> None:
        packages_to_pass = os.listdir(typeshed_with_packages / "stubs")
        expected_length_of_results = len(packages_to_pass)
        args = [
            "--typeshed-dir",
            str(typeshed_with_packages),
            *self.LOGGING_ARGS,
            *packages_to_pass,
        ]
        assert_returncode_0(args)
        self._assert_correct_results_printed_to_stdout(expected_length_of_results)


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


class ToFileOptionTestsBase:
    _dir: Path
    _args: list[str]
    _capsys: pytest.CaptureFixture[str]

    @pytest.fixture(autouse=True)
    def _setup_and_teardown(
        self,
        tmp_path: Path,
        args: list[str],
        capsys: pytest.CaptureFixture[str],
        mocker: MockerFixture,
    ) -> None:
        mocker.patch.dict(vars(self), _dir=tmp_path, _args=args, _capsys=capsys)


class TestToFileOptionFailureCases(ToFileOptionTestsBase):
    def _assert_fails_with_message(self, message: str) -> None:
        assert_argparsing_fails(
            self._args, capsys=self._capsys, failure_message=message
        )

    @pytest.mark.parametrize(
        ("to_file_args", "failure_message"),
        [
            pytest.param(
                ["--to-file", "bar"],
                "has no file extension",
                id="to_file_with_no_file_extension",
            ),
            pytest.param(
                ["--to-file", "bar.xml"],
                "Unrecognised file extension",
                id="to_file_with_unknown_file_extension",
            ),
            pytest.param(
                ["--to-csv", "--to-file", "bar.csv"],
                "not allowed with argument",
                id="to_file_with_other_output_option",
            ),
        ],
    )
    def test_basic_failure_cases(
        self, to_file_args: list[str], failure_message: str
    ) -> None:
        self._args += to_file_args
        self._assert_fails_with_message(failure_message)

    def test_overwrite_store_true(self, EXAMPLE_PACKAGE_NAME: str) -> None:
        self._args += [
            EXAMPLE_PACKAGE_NAME,
            "--to-file",
            "bar.csv",
            "--overwrite",
            "foo",
        ]
        self._assert_fails_with_message("unrecognized arguments")

    def test_to_file_fails_if_parent_doesnt_exist(self) -> None:
        file_in_fictitious_dir = self._dir / "fiction" / "foo.json"
        self._args += ["--to-file", str(file_in_fictitious_dir)]
        self._assert_fails_with_message("does not exist as a directory!")

    def test_to_file_fails_if_parent_is_not_directory(self) -> None:
        file = self._dir / "file"
        file.write_text("", encoding="utf-8")
        writefile = file / "file2.json"
        self._args += ["--to-file", str(writefile)]
        self._assert_fails_with_message("does not exist as a directory!")

    def test_to_file_fails_if_file_exists(self) -> None:
        # Setup the case where --overwrite=False,
        # and --to-file points to an already existing file
        file_name = "foo.json"
        already_existing_file = self._dir / file_name
        already_existing_file.write_text("", encoding="utf-8")
        self._args += ["--to-file", str(already_existing_file)]
        self._assert_fails_with_message(f'{file_name}" already exists!')


@pytest.mark.usefixtures("mocked_gather_stats")
class TestToFileSuccessCases(ToFileOptionTestsBase):
    def _assert_args_succeed(self) -> None:
        assert_returncode_0(self._args)

    def test_to_file_csv(self) -> None:
        dest = self._dir / "foo.csv"
        self._args += ["--to-file", str(dest)]
        self._assert_args_succeed()
        with dest.open(encoding="utf-8", newline="") as csvfile:
            stats = list(csv.DictReader(csvfile))
        assert all(isinstance(item, dict) for item in stats)
        assert all(isinstance(item["package_name"], str) for item in stats)

    def test_to_file_json(self) -> None:
        dest = self._dir / "foo.json"
        self._args += ["--to-file", str(dest)]
        self._assert_args_succeed()
        with dest.open(encoding="utf-8") as jsonfile:
            result = json.load(jsonfile)
        assert isinstance(result, list)
        assert all(isinstance(item, dict) for item in result)
        assert all(isinstance(item["package_name"], str) for item in result)

    def test_to_file_markdown(self) -> None:
        dest = self._dir / "foo.md"
        self._args += ["--to-file", str(dest)]
        self._assert_args_succeed()
        import markdown

        with dest.open(encoding="utf-8") as markdown_file:
            markdown.markdown(markdown_file.read())

    def test_to_file_html(self) -> None:
        dest = self._dir / "foo.html"
        self._args += ["--to-file", str(dest)]
        self._assert_args_succeed()
        with dest.open(encoding="utf-8") as htmlfile:
            soup = BeautifulSoup(htmlfile.read(), "html.parser")
        assert bool(soup.find()), "Invalid HTML produced!"

    def test_to_file_txt(self) -> None:
        dest = self._dir / "foo.txt"
        self._args += ["--to-file", str(dest)]
        self._assert_args_succeed()
        with dest.open(encoding="utf-8") as txtfile:
            source = txtfile.read()
        results = eval(source, vars(typeshed_stats.gather) | globals())
        assert isinstance(results, dict)
        assert all(isinstance(key, str) for key in results)
        assert all(isinstance(value, PackageStats) for value in results.values())

    def test_overwrite_argument(self) -> None:
        # Setup the case where --overwrite=True,
        # and --to-file points to an already existing file
        already_existing_file = self._dir / "foo.json"
        already_existing_file.write_text("", encoding="utf-8")
        self._args += ["--to-file", str(already_existing_file), "--overwrite"]
        self._assert_args_succeed()


# ================================
# Tests for various output options
# ================================


@pytest.fixture
def disabled_rich() -> Iterator[None]:
    assert "rich" not in sys.modules
    with mock.patch.dict("sys.modules", rich=None):
        yield


@pytest.fixture
def mocked_pprint_dot_pprint(mocker: MockerFixture) -> mock.MagicMock:
    return mocker.patch("pprint.pprint", autospec=True)


class OutputOptionsPrintingToTerminalTestsBase:
    _args: list[str]
    _capsys: pytest.CaptureFixture[str]

    @pytest.fixture(autouse=True)
    def _setup_and_teardown(
        self, args: list[str], capsys: pytest.CaptureFixture[str], mocker: MockerFixture
    ) -> None:
        mocker.patch.dict(
            vars(self), _args=(args + ["--log", "CRITICAL"]), _capsys=capsys
        )


class TestOutputOptionsToTerminalFailureCases(OutputOptionsPrintingToTerminalTestsBase):
    def _assert_fails_with_message(self, message: str) -> None:
        assert_argparsing_fails(self._args, failure_message=message)

    @pytest.mark.parametrize(
        "option",
        [
            (
                "--pprint"
                if option is OutputOption.PPRINT
                else _OutputOption_to_argparse(option)
            )
            for option in OutputOption
        ],
    )
    def test_bad_use_of_output_option(
        self, option: str, EXAMPLE_PACKAGE_NAME: str
    ) -> None:
        bogus_argument = "foo"
        self._args += [EXAMPLE_PACKAGE_NAME, option, bogus_argument]
        self._assert_fails_with_message(f"unrecognized arguments: {bogus_argument}")

    @pytest.mark.parametrize(
        "options",
        [
            ["--pprint", "--to-csv"],
            ["--to-csv", "--to-markdown"],
            ["--to-csv", "--to-json", "--to-markdown"],
        ],
    )
    def test_passing_multiple_options_fails(self, options: list[str]) -> None:
        self._args += options
        self._assert_fails_with_message("not allowed with argument")


@pytest.mark.usefixtures("mocked_gather_stats")
class TestOutputOptionsToTerminalSuccessCases(OutputOptionsPrintingToTerminalTestsBase):
    def _assert_outputoption_works(self, option: str) -> None:
        args = self._args + [option]
        assert_returncode_0(args)

    def _get_stdout(self) -> str:
        return self._capsys.readouterr().out.strip()

    def test_to_json(self) -> None:
        self._assert_outputoption_works("--to-json")
        result = json.loads(self._get_stdout())
        assert isinstance(result, list)
        assert all(isinstance(item, dict) for item in result)
        assert all(isinstance(item["package_name"], str) for item in result)

    def test_to_csv(self) -> None:
        self._assert_outputoption_works("--to-csv")
        csvfile = io.StringIO(self._get_stdout(), newline="")
        stats = list(csv.DictReader(csvfile))
        assert all(isinstance(item, dict) for item in stats)
        assert all(isinstance(item["package_name"], str) for item in stats)

    def test_to_markdown(self) -> None:
        self._assert_outputoption_works("--to-markdown")
        result = self._get_stdout()
        import markdown

        markdown.markdown(result)

    def test_to_html(self) -> None:
        self._assert_outputoption_works("--to-html")
        result = self._capsys.readouterr().out.strip()
        soup = BeautifulSoup(result, "html.parser")
        assert bool(soup.find()), "Invalid HTML produced!"

    def test_pprint_option_with_rich_available(self) -> None:
        rich_mock = mock.MagicMock()
        with mock.patch.dict(sys.modules, rich=rich_mock):
            self._assert_outputoption_works("--pprint")
        rich_mock.print.assert_called_once()

    @pytest.mark.usefixtures("disabled_rich")
    def test_pprint_option_with_rich_unavailable(
        self, mocked_pprint_dot_pprint: mock.MagicMock
    ) -> None:
        self._assert_outputoption_works("--pprint")
        mocked_pprint_dot_pprint.assert_called_once()

    @pytest.mark.usefixtures("disabled_rich")
    @pytest.mark.parametrize(
        "option",
        [
            _OutputOption_to_argparse(option)
            for option in OutputOption
            if option is not OutputOption.PPRINT
        ],
    )
    def test_other_options_with_rich_unavailable(
        self, option: str, mocked_pprint_dot_pprint: mock.MagicMock
    ) -> None:
        self._assert_outputoption_works(option)
        mocked_pprint_dot_pprint.assert_not_called()


# ========================
# Tests for --log argument
# ========================


@pytest.mark.parametrize("bad_arg", ["FOO", "getLogger"])
def test_bad_log_argument(args: list[str], bad_arg: str) -> None:
    args += ["--log", bad_arg]
    assert_argparsing_fails(
        args, failure_message=f"invalid choice: {bad_arg!r} (choose from"
    )


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


# ====================================
# Tests for KeyboardInterrupt-handling
# ====================================


def test_KeyboardInterrupt_caught(
    args: list[str], typeshed: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args += ["--log", "CRITICAL"]
    with pytest.raises(SystemExit) as exc_info, mock.patch.object(
        typeshed_stats.gather,
        "gather_stats_on_package",
        autospec=True,
        side_effect=KeyboardInterrupt(),
    ):
        main(args)

    stderr = capsys.readouterr().err
    num_stderr_lines = len(stderr.strip().splitlines())
    assert num_stderr_lines == 1
    assert "Interrupted!" in stderr
    return_code = exc_info.value.code
    assert return_code == 2


# ========================================
# Integration test for --download-typeshed
# ========================================


@pytest.mark.requires_network
def test_integration_with_download_typeshed(caplog: pytest.LogCaptureFixture) -> None:
    assert_returncode_0(["--download-typeshed"])
    assert "Cloning typeshed" in caplog.text
