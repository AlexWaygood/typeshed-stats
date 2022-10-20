import csv
import importlib
import io
import json
import sys
import textwrap
from collections.abc import Callable, Sequence
from os import PathLike
from pathlib import Path
from typing import TypeAlias
from unittest import mock

import attrs
import markdown
import pytest
from bs4 import BeautifulSoup
from pytest_subtests import SubTests  # type: ignore[import]

import typeshed_stats
import typeshed_stats.api
from typeshed_stats import (
    AnnotationStats,
    PackageStats,
    PackageStatus,
    PyrightSetting,
    StubtestSetting,
    gather_annotation_stats_on_file,
    gather_annotation_stats_on_package,
    get_package_line_number,
    get_pyright_strictness,
    get_stubtest_setting,
    stats_from_csv,
    stats_from_json,
    stats_to_csv,
    stats_to_html,
    stats_to_json,
    stats_to_markdown,
)

StrPath: TypeAlias = str | PathLike[str]


def maybe_stringize_path(path: Path, *, use_string_path: bool) -> Path | str:
    if use_string_path:
        return str(path)
    return path


# ===================
# _NiceReprEnum tests
# ===================


def test__NiceReprEnum_docstring_equals_enum_value() -> None:
    assert StubtestSetting.SKIPPED.__doc__ == StubtestSetting.SKIPPED.value


@pytest.mark.parametrize("obj", [StubtestSetting, StubtestSetting.SKIPPED])
def test__NiceReprEnum_docstring_in_help_output(
    obj: object, capsys: pytest.CaptureFixture[str]
) -> None:
    help(obj)
    assert "Stubtest is skipped" in capsys.readouterr().out


def test__NiceReprEnum_repr_str() -> None:
    assert repr(StubtestSetting.SKIPPED) == "StubtestSetting.SKIPPED"
    assert str(StubtestSetting.SKIPPED) == repr(StubtestSetting.SKIPPED)
    assert StubtestSetting.SKIPPED.value not in repr(StubtestSetting.SKIPPED)


@pytest.mark.parametrize(
    ("enum_member", "expected_formatted_name"),
    [
        (StubtestSetting.ERROR_ON_MISSING_STUB, "error on missing stub"),
        (PackageStatus.NO_LONGER_UPDATED, "no longer updated"),
        (PyrightSetting.STRICT_ON_SOME_FILES, "strict on some files"),
    ],
)
def test_formatted__NiceReprEnum_names(
    enum_member: typeshed_stats.api._NiceReprEnum, expected_formatted_name: str
) -> None:
    assert enum_member.formatted_name == expected_formatted_name


def test_str_value_for__NiceReprEnum_possible() -> None:
    class Good(typeshed_stats.api._NiceReprEnum):
        A_STRING = "foo"


def test_non_str_value_for__NiceReprEnum_impossible() -> None:
    with pytest.raises(AssertionError):

        class Bad(typeshed_stats.api._NiceReprEnum):
            NOT_A_STRING = 1


# =========================================
# Tests for collecting stats on annotations
# =========================================


def test__AnnotationStatsCollector___repr__() -> None:
    actual_repr = repr(typeshed_stats.api._AnnotationStatsCollector())
    expected_repr = f"_AnnotationStatsCollector(stats={AnnotationStats()})"
    assert actual_repr == expected_repr


@pytest.fixture(scope="session")
def example_stub_source() -> str:
    return textwrap.dedent(
        """
        import _typeshed
        import typing
        from _typeshed import Incomplete
        from collections.abc import Iterable
        from typing import Any

        a: int
        b: str = ...
        c: Any | None
        d: Any
        d: Incomplete
        e: Iterable[typing.Any]
        f: _typeshed.Incomplete
        g: _typeshed.StrPath

        class Spam:
            a: tuple[typing.Any, ...] | None
            b = ...
            c: int = ...
            d: typing.Sized

        def func1(arg): ...
        def func2(arg: int): ...
        def func3(arg: Incomplete | None = ...): ...
        def func4(arg: Any) -> Any: ...

        class Eggs:
            async def func5(self, arg): ...
            @staticmethod
            async def func6(arg: str) -> list[bytes]: ...
            def func7(arg: Any) -> _typeshed.Incomplete: ...
            @classmethod
            def class_method(cls, eggs: Incomplete): ...

        class Meta(type):
            @classmethod
            def metaclass_classmethod(metacls) -> str: ...
            @classmethod
            async def metaclass_classmethod2(mcls) -> typing.Any: ...
        """
    )


@pytest.fixture(scope="session")
def expected_stats_on_example_stub_file() -> AnnotationStats:
    return AnnotationStats(
        annotated_parameters=6,
        unannotated_parameters=2,
        annotated_returns=5,
        unannotated_returns=5,
        explicit_Incomplete_parameters=2,
        explicit_Incomplete_returns=1,
        explicit_Any_parameters=2,
        explicit_Any_returns=2,
        annotated_variables=11,
        explicit_Any_variables=4,
        explicit_Incomplete_variables=2,
    )


@pytest.mark.parametrize("use_string_path", [True, False])
def test_annotation_stats_on_file(
    subtests: SubTests,
    example_stub_source: str,
    expected_stats_on_example_stub_file: AnnotationStats,
    tmp_path: Path,
    use_string_path: bool,
) -> None:
    test_dot_pyi = tmp_path / "test.pyi"
    test_dot_pyi.write_text(example_stub_source, encoding="utf-8")
    path_to_pass = maybe_stringize_path(test_dot_pyi, use_string_path=use_string_path)
    stats = gather_annotation_stats_on_file(path_to_pass)

    for field in attrs.fields(AnnotationStats):
        field_name = field.name
        actual_stat = getattr(stats, field_name)
        expected_stat = getattr(expected_stats_on_example_stub_file, field_name)
        with subtests.test(
            field_name=field_name, expected_stat=expected_stat, actual_stat=actual_stat
        ):
            assert actual_stat == expected_stat


@pytest.mark.parametrize("use_string_path", [True, False])
def test_annotation_stats_on_package(
    subtests: SubTests,
    typeshed: Path,
    EXAMPLE_PACKAGE_NAME: str,
    example_stub_source: str,
    expected_stats_on_example_stub_file: AnnotationStats,
    use_string_path: bool,
) -> None:
    package_dir = typeshed / "stubs" / EXAMPLE_PACKAGE_NAME
    stdlib_dir = typeshed / "stdlib"

    for directory in (stdlib_dir, package_dir):
        for filename in ("test1.pyi", "test2.pyi"):
            (directory / filename).write_text(example_stub_source, encoding="utf-8")

    typeshed_dir_to_pass = maybe_stringize_path(
        typeshed, use_string_path=use_string_path
    )
    stdlib_stats = gather_annotation_stats_on_package(
        "stdlib", typeshed_dir=typeshed_dir_to_pass
    )
    package_stats = gather_annotation_stats_on_package(
        EXAMPLE_PACKAGE_NAME, typeshed_dir=typeshed_dir_to_pass
    )

    field_names = [field.name for field in attrs.fields(AnnotationStats)]

    for result_name, result in [("stdlib", stdlib_stats), ("package", package_stats)]:
        for field_name in field_names:
            actual_stat = getattr(result, field_name)
            expected_stat = 2 * getattr(expected_stats_on_example_stub_file, field_name)
            with subtests.test(
                result_name=result_name,
                field_name=field_name,
                expected_stat=expected_stat,
                actual_stat=actual_stat,
            ):
                assert actual_stat == expected_stat


# ==============================
# Tests for get_stubtest_setting
# ==============================


def test_get_stubtest_setting_stdlib(typeshed: Path) -> None:
    result = get_stubtest_setting("stdlib", typeshed_dir=typeshed)
    assert result is StubtestSetting.ERROR_ON_MISSING_STUB


def test_get_stubtest_setting_non_stdlib_no_stubtest_section(
    EXAMPLE_PACKAGE_NAME: str, typeshed: Path
) -> None:
    metadata = typeshed / "stubs" / EXAMPLE_PACKAGE_NAME / "METADATA.toml"
    metadata.write_text("\n")
    result = get_stubtest_setting(EXAMPLE_PACKAGE_NAME, typeshed_dir=typeshed)
    assert result is StubtestSetting.MISSING_STUBS_IGNORED


@pytest.mark.parametrize(
    ("metadata_contents", "expected_result", "use_string_path"),
    [
        ("", StubtestSetting.MISSING_STUBS_IGNORED, True),
        ("skip = false", StubtestSetting.MISSING_STUBS_IGNORED, False),
        ("ignore_missing_stub = true", StubtestSetting.MISSING_STUBS_IGNORED, True),
        ("skip = true", StubtestSetting.SKIPPED, False),
        ("skip = true\nignore_missing_stub = true", StubtestSetting.SKIPPED, True),
        ("skip = true\nignore_missing_stub = false", StubtestSetting.SKIPPED, False),
        ("ignore_missing_stub = false", StubtestSetting.ERROR_ON_MISSING_STUB, True),
    ],
)
def test_get_stubtest_setting_non_stdlib_with_stubtest_section(
    EXAMPLE_PACKAGE_NAME: str,
    typeshed: Path,
    metadata_contents: str,
    expected_result: StubtestSetting,
    use_string_path: bool,
) -> None:
    metadata = typeshed / "stubs" / EXAMPLE_PACKAGE_NAME / "METADATA.toml"
    metadata.write_text(f"[tool.stubtest]\n{metadata_contents}", encoding="utf-8")
    typeshed_dir_to_pass = maybe_stringize_path(
        typeshed, use_string_path=use_string_path
    )
    actual_result = get_stubtest_setting(
        EXAMPLE_PACKAGE_NAME, typeshed_dir=typeshed_dir_to_pass
    )
    assert actual_result is expected_result


# =================================
# Tests for get_package_line_number
# =================================


@pytest.mark.parametrize("use_string_path", [True, False])
class TestGetPackageLineNumber:
    def test_get_package_line_number_empty_package(
        self, EXAMPLE_PACKAGE_NAME: str, typeshed: Path, use_string_path: bool
    ) -> None:
        typeshed_dir_to_pass = maybe_stringize_path(
            typeshed, use_string_path=use_string_path
        )
        result = get_package_line_number(
            EXAMPLE_PACKAGE_NAME, typeshed_dir=typeshed_dir_to_pass
        )
        assert result == 0

    def test_get_package_line_number_single_file(
        self, EXAMPLE_PACKAGE_NAME: str, typeshed: Path, use_string_path: bool
    ) -> None:
        stub = typeshed / "stubs" / EXAMPLE_PACKAGE_NAME / "foo.pyi"
        stub.write_text("foo: int\nbar: str", encoding="utf-8")
        typeshed_dir_to_pass = maybe_stringize_path(
            typeshed, use_string_path=use_string_path
        )
        result = get_package_line_number(
            EXAMPLE_PACKAGE_NAME, typeshed_dir=typeshed_dir_to_pass
        )
        assert result == 2

    def test_get_package_line_number_multiple_files(
        self, EXAMPLE_PACKAGE_NAME: str, typeshed: Path, use_string_path: bool
    ) -> None:
        two_line_stub = "foo: int\nbar: str"
        top_level_stub = typeshed / "stubs" / EXAMPLE_PACKAGE_NAME / "foo.pyi"
        top_level_stub.write_text(two_line_stub, encoding="utf-8")
        subpkg = typeshed / "stubs" / EXAMPLE_PACKAGE_NAME / "subpkg"
        subpkg.mkdir()
        (subpkg / "bar.pyi").write_text(two_line_stub, encoding="utf-8")
        subpkg2 = typeshed / "stubs" / EXAMPLE_PACKAGE_NAME / "subpkg2"
        subpkg2.mkdir()
        for name in "spam.pyi", "eggs.pyi":
            (subpkg2 / name).write_text(two_line_stub, encoding="utf-8")
        typeshed_dir_to_pass = maybe_stringize_path(
            typeshed, use_string_path=use_string_path
        )
        result = get_package_line_number(
            EXAMPLE_PACKAGE_NAME, typeshed_dir=typeshed_dir_to_pass
        )
        assert result == 8


# =============================
# Tests for get_pyright_setting
# =============================


@pytest.mark.parametrize(
    ("excluded_path", "package_to_test", "pyright_setting_name", "use_string_path"),
    [
        ("stdlib", "stdlib", "NOT_STRICT", True),
        ("stdlib/tkinter", "stdlib", "STRICT_ON_SOME_FILES", False),
        ("stubs", "stdlib", "STRICT", True),
        ("stubs/aiofiles", "stdlib", "STRICT", False),
        ("stubs", "appdirs", "NOT_STRICT", True),
        ("stubs", "boto", "NOT_STRICT", False),
        ("stubs/boto", "appdirs", "STRICT", True),
        ("stubs/boto/auth.pyi", "boto", "STRICT_ON_SOME_FILES", False),
    ],
)
def test_get_pyright_setting(
    typeshed: Path,
    excluded_path: StrPath,
    package_to_test: str,
    pyright_setting_name: str,
    use_string_path: bool,
) -> None:
    pyrightconfig_template = textwrap.dedent(
        """
        {{
            "typeshedPath": ".",
            // A comment to make this invalid JSON
            "exclude": [
                "{}"
            ],
        }}
        """
    )
    pyrightconfig = pyrightconfig_template.format(excluded_path)
    with pytest.raises(json.JSONDecodeError):
        json.loads(pyrightconfig)
    pyrightconfig_path = typeshed / "pyrightconfig.stricter.json"
    pyrightconfig_path.write_text(pyrightconfig, encoding="utf-8")
    typeshed_dir_to_pass = maybe_stringize_path(
        typeshed, use_string_path=use_string_path
    )
    pyright_strictness = get_pyright_strictness(
        package_name=package_to_test, typeshed_dir=typeshed_dir_to_pass
    )
    expected_result = PyrightSetting[pyright_setting_name]
    assert pyright_strictness is expected_result


# =======================================
# Tests for serialisation/deserialisation
# =======================================


def test_conversion_to_from_dict(
    make_random_PackageStats: Callable[[], PackageStats]
) -> None:
    random_PackageStats = make_random_PackageStats()
    assert type(random_PackageStats) is PackageStats
    as_dict = random_PackageStats.to_dict()
    assert type(as_dict) is dict
    assert all(type(key) is str for key in as_dict)
    new_PackageStats = PackageStats.from_dict(as_dict)
    assert type(new_PackageStats) is PackageStats
    assert random_PackageStats is not new_PackageStats
    assert random_PackageStats == new_PackageStats


def test_conversion_to_and_from_json(
    random_PackageStats_sequence: Sequence[PackageStats],
) -> None:
    converted = stats_to_json(random_PackageStats_sequence)
    assert isinstance(converted, str)
    lst = json.loads(converted)
    assert isinstance(lst, list)
    assert all(isinstance(item, dict) and "package_name" in item for item in lst)
    new_package_stats = stats_from_json(converted)
    assert new_package_stats == random_PackageStats_sequence


def test_conversion_to_and_from_csv(
    random_PackageStats_sequence: Sequence[PackageStats],
) -> None:
    converted = stats_to_csv(random_PackageStats_sequence)
    assert isinstance(converted, str)
    with io.StringIO(converted, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        first_row = next(iter(reader))
    assert isinstance(first_row, dict)
    assert "package_name" in first_row
    first_PackageStats_item = random_PackageStats_sequence[0]
    assert first_row["package_name"] == first_PackageStats_item.package_name
    assert "annotated_parameters" in first_row
    assert (
        int(first_row["annotated_parameters"])
        == first_PackageStats_item.annotation_stats.annotated_parameters
    )
    new_list_of_info = stats_from_csv(converted)
    assert new_list_of_info == random_PackageStats_sequence


def test_markdown_and_htmlconversion(
    random_PackageStats_sequence: Sequence[PackageStats],
) -> None:
    converted_to_markdown = stats_to_markdown(random_PackageStats_sequence)
    html1 = markdown.markdown(converted_to_markdown)
    html2 = stats_to_html(random_PackageStats_sequence)
    assert html1 == html2
    soup = BeautifulSoup(html1, "html.parser")
    assert bool(soup.find()), "Invalid HTML produced!"


# ========================================
# Test the package doesn't import on <3.10
# ========================================


@mock.patch.object(sys, "version_info", new=(3, 9, 8, "final", 0))
@pytest.mark.parametrize("module_name", ["typeshed_stats", "typeshed_stats.api"])
def test_import_fails_on_less_than_3_point_10(module_name: str) -> None:
    for module_name in ("typeshed_stats", "typeshed_stats.api"):
        if module_name in sys.modules:
            del sys.modules[module_name]
    with pytest.raises(ImportError):
        importlib.import_module(module_name)
