"""Test api.py."""

import contextlib
import csv
import io
import json
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Final

import attrs
import markdown
import pytest
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
    stats_from_csv,
    stats_from_json,
    stats_to_csv,
    stats_to_html,
    stats_to_json,
    stats_to_markdown,
)

# ==========
# _NiceReprEnum tests
# ============


def test__NiceReprEnum_docstring_is_enum_value() -> None:
    assert StubtestSetting.SKIPPED.__doc__ == StubtestSetting.SKIPPED.value


@pytest.mark.parametrize("obj", [StubtestSetting, StubtestSetting.SKIPPED])
def test__NiceReprEnum_docstring_in_help(obj: object) -> None:
    with io.StringIO() as tmp_stdout:
        with contextlib.redirect_stdout(tmp_stdout):
            help(obj)
        assert "Stubtest is skipped" in tmp_stdout.getvalue()


def test__NiceReprEnum_repr_str() -> None:
    assert repr(StubtestSetting.SKIPPED) == "StubtestSetting.SKIPPED"
    assert str(StubtestSetting.SKIPPED) == repr(StubtestSetting.SKIPPED)
    assert StubtestSetting.SKIPPED.value not in repr(StubtestSetting.SKIPPED)


@pytest.mark.parametrize(
    "enum_member,expected_formatted_name",
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


def test_non_str_value_for__NiceReprEnum_impossible() -> None:
    class Good(typeshed_stats.api._NiceReprEnum):
        A_STRING = "foo"

    with pytest.raises(AssertionError):

        class Bad(typeshed_stats.api._NiceReprEnum):
            NOT_A_STRING = 1


# =======================================
# Tests for serialisation/deserialisation
# =======================================


info_on_foo: Final = PackageStats(
    "foo",
    8,
    PackageStatus.UP_TO_DATE,
    StubtestSetting.MISSING_STUBS_IGNORED,
    PyrightSetting.STRICT,
    AnnotationStats(),
)
list_of_info: Final = [info_on_foo, info_on_foo]


def test_conversion_to_and_from_json() -> None:
    converted = stats_to_json(list_of_info)
    assert isinstance(converted, str)
    lst = json.loads(converted)
    assert isinstance(lst, list)
    assert all(isinstance(item, dict) and "package_name" in item for item in lst)
    new_list_of_info = stats_from_json(converted)
    assert new_list_of_info == list_of_info


def test_conversion_to_and_from_csv() -> None:
    converted = stats_to_csv(list_of_info)
    assert isinstance(converted, str)
    with io.StringIO(converted, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        first_row = next(iter(reader))
    assert isinstance(first_row, dict)
    assert "package_name" in first_row and first_row["package_name"] == "foo"
    assert "annotated_parameters" in first_row
    assert first_row["annotated_parameters"] == "0"
    new_list_of_info = stats_from_csv(converted)
    assert new_list_of_info == list_of_info


def test_markdown_conversion() -> None:
    converted_to_markdown = stats_to_markdown(list_of_info)
    html1 = markdown.markdown(converted_to_markdown)
    html2 = stats_to_html(list_of_info)
    assert html1 == html2


# =========================================
# Tests for collecting stats on annotations
# =========================================


EXAMPLE_SOURCE: Final = """
import _typeshed
import typing
from _typeshed import Incomplete
from typing import Any

a: int
b: str = ...
c: Any
d: Any
d: Incomplete
e: typing.Any
f: _typeshed.Incomplete

class Spam:
    a: typing.Any
    b = ...
    c: int = ...

def func1(arg): ...
def func2(arg: int): ...
def func3(arg: Incomplete): ...
def func4(arg: Any) -> Any: ...

class Eggs:
    async def func5(self, arg): ...
    @staticmethod
    async def func6(arg: str) -> list[bytes]: ...
    def func7(arg: Any) -> _typeshed.Incomplete: ...
"""

EXPECTED_STATS_ON_EXAMPLE: Final = AnnotationStats(
    annotated_parameters=5,
    unannotated_parameters=2,
    annotated_returns=3,
    unannotated_returns=4,
    explicit_Incomplete_parameters=1,
    explicit_Incomplete_returns=1,
    explicit_Any_parameters=2,
    explicit_Any_returns=1,
    annotated_variables=9,
    explicit_Any_variables=4,
    explicit_Incomplete_variables=2,
)


def test_annotation_stats_on_file(subtests: SubTests) -> None:
    with tempfile.TemporaryDirectory() as td:
        test_path = Path(td, "test.pyi")
        with open(test_path, "w", encoding="utf-8") as tmpfile:
            tmpfile.write(EXAMPLE_SOURCE)
        stats = gather_annotation_stats_on_file(test_path)

    for field in attrs.fields(AnnotationStats):  # type: ignore[arg-type]
        field_name = field.name
        with subtests.test(field_name=field_name):
            assert getattr(stats, field_name) == getattr(
                EXPECTED_STATS_ON_EXAMPLE, field_name
            )


EXAMPLE_PACKAGE_NAME: Final = "package"


@contextlib.contextmanager
def _setup_typeshed() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as td:
        typeshed = Path(td)
        (typeshed / "stdlib").mkdir()
        stubs_dir = typeshed / "stubs"
        stubs_dir.mkdir()
        (stubs_dir / EXAMPLE_PACKAGE_NAME).mkdir()
        yield typeshed


def test_annotation_stats_on_package(subtests: SubTests) -> None:
    with _setup_typeshed() as typeshed:
        package_dir = typeshed / "stubs" / EXAMPLE_PACKAGE_NAME
        stdlib_dir = typeshed / "stdlib"

        for directory in (stdlib_dir, package_dir):
            for filename in ("test1.pyi", "test2.pyi"):
                with open(directory / filename, "w", encoding="utf-8") as tmpfile:
                    tmpfile.write(EXAMPLE_SOURCE)

        stdlib_stats = gather_annotation_stats_on_package(
            "stdlib", typeshed_dir=typeshed
        )
        package_stats = gather_annotation_stats_on_package(
            EXAMPLE_PACKAGE_NAME, typeshed_dir=typeshed
        )

    field_names = [field.name for field in attrs.fields(AnnotationStats)]  # type: ignore[arg-type]

    for result_name, result in [("stdlib", stdlib_stats), ("package", package_stats)]:
        for field_name in field_names:
            with subtests.test(result_name=result_name, field_name=field_name):
                assert getattr(result, field_name) == (
                    2 * getattr(EXPECTED_STATS_ON_EXAMPLE, field_name)
                )
