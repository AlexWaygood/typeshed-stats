"""Test the package."""

import builtins
import contextlib
import csv
import importlib
import io
import json
import pkgutil
import tempfile
import types
from pathlib import Path
from typing import Final

import markdown
import pytest

import typeshed_stats
import typeshed_stats.api
from typeshed_stats import (
    AnnotationStats,
    PackageStats,
    PackageStatus,
    PyrightSetting,
    StubtestSetting,
    gather_annotation_stats_on_file,
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


def test_formatted__NiceReprEnum_names() -> None:
    assert (
        StubtestSetting.ERROR_ON_MISSING_STUB.formatted_name == "error on missing stub"
    )
    assert PackageStatus.NO_LONGER_UPDATED.formatted_name == "no longer updated"
    assert PyrightSetting.STRICT_ON_SOME_FILES.formatted_name == "strict on some files"


def test_non_str_value_for__NiceReprEnum_impossible() -> None:
    class Good(typeshed_stats.api._NiceReprEnum):
        A_STRING = "foo"

    with pytest.raises(AssertionError):

        class Bad(typeshed_stats.api._NiceReprEnum):
            NOT_A_STRING = 1


# =================
# Tests for __all__
# =================


ALL_MODULES: Final = [typeshed_stats] + [
    importlib.import_module(f"typeshed_stats.{m.name}")
    for m in pkgutil.iter_modules(typeshed_stats.__path__)
]


@pytest.mark.parametrize("module", ALL_MODULES)
def test___all___alphabetisation(module: types.ModuleType) -> None:
    assert module.__all__ == sorted(module.__all__)


def _is_from_other_module(obj: object) -> bool:
    return getattr(obj, "__module__", "typeshed_stats") != "typeshed_stats"


@pytest.mark.parametrize("module", ALL_MODULES)
def test_all_public_names_in___all__(module: types.ModuleType) -> None:
    """Test that all names not in `__all__` are marked as private."""
    assert set(module.__all__) >= {
        name
        for name, value in vars(module).items()
        if not (
            name.startswith("_")
            or isinstance(value, types.ModuleType)
            or _is_from_other_module(value)
            or name in vars(builtins)
        )
    }


def test___init___imports_everything_public_from_submodules() -> None:
    all_as_set = set(typeshed_stats.__all__)
    submodule_alls_combined = set(sum((mod.__all__ for mod in ALL_MODULES), start=[]))
    assert (
        all_as_set >= submodule_alls_combined
    ), f"Missing names: {submodule_alls_combined - all_as_set!r}"


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


def test_annotation_stats_on_file() -> None:
    with tempfile.TemporaryDirectory() as td:
        test_path = Path(td, "test.py")
        with test_path.open("w", encoding="utf-8") as tmpfile:
            tmpfile.write(EXAMPLE_SOURCE)
        stats = gather_annotation_stats_on_file(test_path)

    assert stats.annotated_parameters == 5
    assert stats.unannotated_parameters == 2
    assert stats.annotated_returns == 3
    assert stats.unannotated_returns == 4
    assert stats.explicit_Incomplete_parameters == 1
    assert stats.explicit_Incomplete_returns == 1
    assert stats.explicit_Any_parameters == 2
    assert stats.explicit_Any_returns == 1
    assert stats.annotated_variables == 9
    assert stats.explicit_Any_variables == 4
    assert stats.explicit_Incomplete_variables == 2
