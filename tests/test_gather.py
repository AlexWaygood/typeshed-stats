from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Any, final
from unittest import mock

import aiohttp
import attrs
import pytest
from pytest_subtests import SubTests  # type: ignore[import]

import typeshed_stats
import typeshed_stats.gather
from typeshed_stats.gather import (
    AnnotationStats,
    PackageStatus,
    PyrightSetting,
    StubtestSetting,
    gather_annotation_stats_on_file,
    gather_annotation_stats_on_package,
    get_package_size,
    get_package_status,
    get_pyright_strictness,
    get_stubtest_setting,
)


def maybe_stringize_path(path: Path, *, use_string_path: bool) -> Path | str:
    if use_string_path:
        return str(path)
    return path


def write_metadata_text(typeshed: Path, package_name: str, data: str) -> None:
    metadata = typeshed / "stubs" / package_name / "METADATA.toml"
    metadata.write_text(data, encoding="utf-8")


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
    enum_member: typeshed_stats.gather._NiceReprEnum, expected_formatted_name: str
) -> None:
    assert enum_member.formatted_name == expected_formatted_name


def test_str_value_for__NiceReprEnum_possible() -> None:
    class Good(typeshed_stats.gather._NiceReprEnum):
        A_STRING = "foo"


def test_non_str_value_for__NiceReprEnum_impossible() -> None:
    with pytest.raises(AssertionError):

        class Bad(typeshed_stats.gather._NiceReprEnum):
            NOT_A_STRING = 1


# =========================================
# Tests for collecting stats on annotations
# =========================================


def test__AnnotationStatsCollector___repr__() -> None:
    actual_repr = repr(typeshed_stats.gather._AnnotationStatsCollector())
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
    write_metadata_text(typeshed, EXAMPLE_PACKAGE_NAME, "\n")
    result = get_stubtest_setting(EXAMPLE_PACKAGE_NAME, typeshed_dir=typeshed)
    assert result is StubtestSetting.MISSING_STUBS_IGNORED


@pytest.mark.parametrize(
    ("metadata_contents", "expected_result"),
    [
        ("", StubtestSetting.MISSING_STUBS_IGNORED),
        ("skip = false", StubtestSetting.MISSING_STUBS_IGNORED),
        ("ignore_missing_stub = true", StubtestSetting.MISSING_STUBS_IGNORED),
        ("skip = true", StubtestSetting.SKIPPED),
        ("skip = true\nignore_missing_stub = true", StubtestSetting.SKIPPED),
        ("skip = true\nignore_missing_stub = false", StubtestSetting.SKIPPED),
        ("ignore_missing_stub = false", StubtestSetting.ERROR_ON_MISSING_STUB),
    ],
)
def test_get_stubtest_setting_non_stdlib_with_stubtest_section(
    EXAMPLE_PACKAGE_NAME: str,
    typeshed: Path,
    metadata_contents: str,
    expected_result: StubtestSetting,
    use_string_path: bool,
) -> None:
    write_metadata_text(
        typeshed, EXAMPLE_PACKAGE_NAME, f"[tool.stubtest]\n{metadata_contents}"
    )
    typeshed_dir_to_pass = maybe_stringize_path(
        typeshed, use_string_path=use_string_path
    )
    actual_result = get_stubtest_setting(
        EXAMPLE_PACKAGE_NAME, typeshed_dir=typeshed_dir_to_pass
    )
    assert actual_result is expected_result


# =================================
# Tests for get_package_status
# =================================


@pytest.mark.parametrize(
    ("package_name", "expected_result"),
    [("stdlib", PackageStatus.STDLIB), ("gdb", PackageStatus.NOT_ON_PYPI)],
)
async def test_get_package_status_special_cases(
    package_name: str, expected_result: PackageStatus, use_string_path: bool
) -> None:
    typeshed_dir = maybe_stringize_path(Path("."), use_string_path=use_string_path)
    status = await get_package_status(package_name, typeshed_dir=typeshed_dir)
    assert status is expected_result


@pytest.mark.parametrize(
    ("metadata_to_write", "expected_result"),
    [
        ('obsolete_since = "3.1.0"', PackageStatus.OBSOLETE),
        ("no_longer_updated = true", PackageStatus.NO_LONGER_UPDATED),
    ],
)
async def test_get_package_status_no_pypi_requests_required(
    EXAMPLE_PACKAGE_NAME: str,
    typeshed: Path,
    use_string_path: bool,
    metadata_to_write: str,
    expected_result: PackageStatus,
) -> None:
    write_metadata_text(typeshed, EXAMPLE_PACKAGE_NAME, metadata_to_write)
    typeshed_dir_to_pass = maybe_stringize_path(
        typeshed, use_string_path=use_string_path
    )
    status = await get_package_status(
        EXAMPLE_PACKAGE_NAME, typeshed_dir=typeshed_dir_to_pass
    )
    assert status is expected_result


@final
@attrs.define
class MockResponse:
    version: str

    async def json(self) -> dict[str, Any]:
        return {"info": {"version": self.version}}

    async def __aenter__(self) -> MockResponse:
        return self

    async def __aexit__(self, *args: object) -> None:
        pass

    def raise_for_status(self) -> None:
        pass


@pytest.mark.parametrize(
    ("typeshed_version", "pypi_version", "expected_result"),
    [
        ("0.8.*", "0.8.3", PackageStatus.UP_TO_DATE),
        ("0.8.*", "0.9.3", PackageStatus.OUT_OF_DATE),
        ("0.8.*", "1.8", PackageStatus.OUT_OF_DATE),
        ("1.*", "1.1", PackageStatus.UP_TO_DATE),
        ("1.*", "1.1.1", PackageStatus.UP_TO_DATE),
        ("1.*", "2", PackageStatus.OUT_OF_DATE),
        ("1.0.*", "1.0.1", PackageStatus.UP_TO_DATE),
        ("1.0.*", "1.0.2", PackageStatus.UP_TO_DATE),
        ("1.0.*", "1.1", PackageStatus.OUT_OF_DATE),
        ("1.64.72", "1.64.72", PackageStatus.UP_TO_DATE),
        ("1.64.72", "1.64.73", PackageStatus.OUT_OF_DATE),
        ("2022.9.13", "2022.9.13", PackageStatus.UP_TO_DATE),
        ("2022.9.13", "2022.10.22", PackageStatus.OUT_OF_DATE),
    ],
)
async def test_get_package_status_with_mocked_pypi_requests(
    EXAMPLE_PACKAGE_NAME: str,
    typeshed: Path,
    use_string_path: bool,
    typeshed_version: str,
    pypi_version: str,
    expected_result: PackageStatus,
) -> None:
    write_metadata_text(
        typeshed, EXAMPLE_PACKAGE_NAME, f'version = "{typeshed_version}"'
    )
    typeshed_dir_to_pass = maybe_stringize_path(
        typeshed, use_string_path=use_string_path
    )
    with mock.patch.object(
        aiohttp.ClientSession, "get", return_value=MockResponse(pypi_version)
    ):
        status = await get_package_status(
            EXAMPLE_PACKAGE_NAME, typeshed_dir=typeshed_dir_to_pass
        )
    assert status is expected_result


# =================================
# Tests for get_package_size
# =================================


def test_get_package_size_empty_package(
    EXAMPLE_PACKAGE_NAME: str, typeshed: Path, use_string_path: bool
) -> None:
    typeshed_dir_to_pass = maybe_stringize_path(
        typeshed, use_string_path=use_string_path
    )
    result = get_package_size(EXAMPLE_PACKAGE_NAME, typeshed_dir=typeshed_dir_to_pass)
    assert result == 0


def test_get_package_size_single_file(
    EXAMPLE_PACKAGE_NAME: str, typeshed: Path, use_string_path: bool
) -> None:
    stub = typeshed / "stubs" / EXAMPLE_PACKAGE_NAME / "foo.pyi"
    stub.write_text("foo: int\nbar: str", encoding="utf-8")
    typeshed_dir_to_pass = maybe_stringize_path(
        typeshed, use_string_path=use_string_path
    )
    result = get_package_size(EXAMPLE_PACKAGE_NAME, typeshed_dir=typeshed_dir_to_pass)
    assert result == 2


def test_get_package_size_multiple_files(
    EXAMPLE_PACKAGE_NAME: str, typeshed: Path, use_string_path: bool
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
    result = get_package_size(EXAMPLE_PACKAGE_NAME, typeshed_dir=typeshed_dir_to_pass)
    assert result == 8


# =============================
# Tests for get_pyright_setting
# =============================


@pytest.mark.parametrize(
    ("excluded_path", "package_to_test", "pyright_setting_name"),
    [
        ("stdlib", "stdlib", "NOT_STRICT"),
        ("stdlib/tkinter", "stdlib", "STRICT_ON_SOME_FILES"),
        ("stubs", "stdlib", "STRICT"),
        ("stubs/aiofiles", "stdlib", "STRICT"),
        ("stubs", "appdirs", "NOT_STRICT"),
        ("stubs", "boto", "NOT_STRICT"),
        ("stubs/boto", "appdirs", "STRICT"),
        ("stubs/boto/auth.pyi", "boto", "STRICT_ON_SOME_FILES"),
    ],
)
def test_get_pyright_setting(
    typeshed: Path,
    excluded_path: str,
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
