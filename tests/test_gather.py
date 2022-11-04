from __future__ import annotations

import json
import os
import random
import textwrap
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, nullcontext
from pathlib import Path
from typing import TypeAlias
from unittest import mock

import aiohttp
import attrs
import pytest
from packaging.version import Version
from pytest_subtests import SubTests  # type: ignore[import]

import typeshed_stats
import typeshed_stats.gather
from typeshed_stats.gather import (
    AnnotationStats,
    PackageStats,
    PackageStatus,
    PyrightSetting,
    StubtestSetting,
    _get_pypi_data,
    gather_annotation_stats_on_file,
    gather_annotation_stats_on_package,
    gather_stats,
    get_package_size,
    get_package_status,
    get_pyright_strictness,
    get_stubtest_setting,
    tmpdir_typeshed,
)


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
    out = capsys.readouterr().out
    assert "Stubtest is skipped" in out


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
    maybe_stringize_path: Callable[[Path], Path | str],
) -> None:
    test_dot_pyi = tmp_path / "test.pyi"
    test_dot_pyi.write_text(example_stub_source, encoding="utf-8")
    stats = gather_annotation_stats_on_file(maybe_stringize_path(test_dot_pyi))

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
    maybe_stringize_path: Callable[[Path], Path | str],
) -> None:
    package_dir = typeshed / "stubs" / EXAMPLE_PACKAGE_NAME
    stdlib_dir = typeshed / "stdlib"

    for directory in (stdlib_dir, package_dir):
        for filename in ("test1.pyi", "test2.pyi"):
            (directory / filename).write_text(example_stub_source, encoding="utf-8")

    typeshed_dir_to_pass = maybe_stringize_path(typeshed)
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
    ("metadata_contents", "expected_result_name"),
    [
        ("", "MISSING_STUBS_IGNORED"),
        ("skip = false", "MISSING_STUBS_IGNORED"),
        ("ignore_missing_stub = true", "MISSING_STUBS_IGNORED"),
        ("skip = true", "SKIPPED"),
        ("skip = true\nignore_missing_stub = true", "SKIPPED"),
        ("skip = true\nignore_missing_stub = false", "SKIPPED"),
        ("ignore_missing_stub = false", "ERROR_ON_MISSING_STUB"),
    ],
)
def test_get_stubtest_setting_non_stdlib_with_stubtest_section(
    EXAMPLE_PACKAGE_NAME: str,
    typeshed: Path,
    metadata_contents: str,
    expected_result_name: str,
    maybe_stringize_path: Callable[[Path], Path | str],
) -> None:
    write_metadata_text(
        typeshed, EXAMPLE_PACKAGE_NAME, f"[tool.stubtest]\n{metadata_contents}"
    )
    actual_result = get_stubtest_setting(
        EXAMPLE_PACKAGE_NAME, typeshed_dir=maybe_stringize_path(typeshed)
    )
    expected_result = StubtestSetting[expected_result_name]
    assert actual_result is expected_result


# =================================
# Tests for get_package_status
# =================================


@pytest.mark.parametrize(
    ("package_name", "expected_result"),
    [("stdlib", PackageStatus.STDLIB), ("gdb", PackageStatus.NOT_ON_PYPI)],
)
async def test_get_package_status_special_cases(
    package_name: str,
    expected_result: PackageStatus,
    maybe_stringize_path: Callable[[Path], Path | str],
) -> None:
    typeshed_dir = maybe_stringize_path(Path("."))
    status = await get_package_status(package_name, typeshed_dir=typeshed_dir)
    assert status is expected_result


@pytest.mark.parametrize(
    ("metadata_to_write", "expected_result_name"),
    [
        ('obsolete_since = "3.1.0"', "OBSOLETE"),
        ("no_longer_updated = true", "NO_LONGER_UPDATED"),
    ],
)
async def test_get_package_status_no_pypi_requests_required(
    EXAMPLE_PACKAGE_NAME: str,
    typeshed: Path,
    maybe_stringize_path: Callable[[Path], Path | str],
    metadata_to_write: str,
    expected_result_name: str,
) -> None:
    write_metadata_text(typeshed, EXAMPLE_PACKAGE_NAME, metadata_to_write)
    status = await get_package_status(
        EXAMPLE_PACKAGE_NAME, typeshed_dir=maybe_stringize_path(typeshed)
    )
    expected_result = PackageStatus[expected_result_name]
    assert status is expected_result


@pytest.mark.parametrize(
    ("typeshed_version", "pypi_version", "expected_result_name"),
    [
        ("0.8.*", "0.8.3", "UP_TO_DATE"),
        ("0.8.*", "0.9.3", "OUT_OF_DATE"),
        ("0.8.*", "1.8", "OUT_OF_DATE"),
        ("1.*", "1.1", "UP_TO_DATE"),
        ("1.*", "1.1.1", "UP_TO_DATE"),
        ("1.*", "2", "OUT_OF_DATE"),
        ("1.0.*", "1.0.1", "UP_TO_DATE"),
        ("1.0.*", "1.0.2", "UP_TO_DATE"),
        ("1.0.*", "1.1", "OUT_OF_DATE"),
        ("1.64.72", "1.64.72", "UP_TO_DATE"),
        ("1.64.72", "1.64.73", "OUT_OF_DATE"),
        ("2022.9.13", "2022.9.13", "UP_TO_DATE"),
        ("2022.9.13", "2022.10.22", "OUT_OF_DATE"),
    ],
)
async def test_get_package_status_with_mocked_pypi_requests(
    EXAMPLE_PACKAGE_NAME: str,
    typeshed: Path,
    maybe_stringize_path: Callable[[Path], Path | str],
    typeshed_version: str,
    pypi_version: str,
    expected_result_name: str,
) -> None:
    write_metadata_text(
        typeshed, EXAMPLE_PACKAGE_NAME, f'version = "{typeshed_version}"'
    )
    typeshed_dir_to_pass = maybe_stringize_path(typeshed)
    with mock.patch.object(
        typeshed_stats.gather,
        "_get_pypi_data",
        autospec=True,
        return_value={"info": {"version": pypi_version}},
    ):
        status = await get_package_status(
            EXAMPLE_PACKAGE_NAME, typeshed_dir=typeshed_dir_to_pass
        )
    expected_result = PackageStatus[expected_result_name]
    assert status is expected_result


_GetSessionCallable: TypeAlias = Callable[
    [], AbstractAsyncContextManager[aiohttp.ClientSession | None]
]


@pytest.mark.requires_network
@pytest.mark.parametrize(
    ("package_name", "get_session"),
    [
        ("emoji", aiohttp.ClientSession),
        ("flake8-bugbear", aiohttp.ClientSession),
        ("SQLAlchemy", nullcontext),
    ],
)
async def test__get_pypi_data(
    package_name: str, get_session: _GetSessionCallable
) -> None:
    async with get_session() as session:
        data = await _get_pypi_data(package_name, session)
    assert isinstance(data, dict)
    assert all(isinstance(key, str) for key in data)
    assert "info" in data
    info = data["info"]
    assert isinstance(info, dict)
    assert all(isinstance(key, str) for key in info)
    assert "version" in info
    version = info["version"]
    Version(version)


# =================================
# Tests for get_package_size
# =================================


def test_get_package_size_empty_package(
    EXAMPLE_PACKAGE_NAME: str,
    typeshed: Path,
    maybe_stringize_path: Callable[[Path], Path | str],
) -> None:
    typeshed_dir_to_pass = maybe_stringize_path(typeshed)
    result = get_package_size(EXAMPLE_PACKAGE_NAME, typeshed_dir=typeshed_dir_to_pass)
    assert result == 0


def test_get_package_size_single_file(
    EXAMPLE_PACKAGE_NAME: str,
    typeshed: Path,
    maybe_stringize_path: Callable[[Path], Path | str],
) -> None:
    stub = typeshed / "stubs" / EXAMPLE_PACKAGE_NAME / "foo.pyi"
    stub.write_text("foo: int\nbar: str", encoding="utf-8")
    typeshed_dir_to_pass = maybe_stringize_path(typeshed)
    result = get_package_size(EXAMPLE_PACKAGE_NAME, typeshed_dir=typeshed_dir_to_pass)
    assert result == 2


def test_get_package_size_multiple_files(
    EXAMPLE_PACKAGE_NAME: str,
    typeshed: Path,
    maybe_stringize_path: Callable[[Path], Path | str],
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
    typeshed_dir_to_pass = maybe_stringize_path(typeshed)
    result = get_package_size(EXAMPLE_PACKAGE_NAME, typeshed_dir=typeshed_dir_to_pass)
    assert result == 8


# ================================
# Tests for get_pyright_strictness
# ================================


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
    maybe_stringize_path: Callable[[Path], Path | str],
    pyrightconfig_template: str,
) -> None:
    pyrightconfig = pyrightconfig_template.format(f'"{excluded_path}"')
    with pytest.raises(json.JSONDecodeError):
        json.loads(pyrightconfig)
    pyrightconfig_path = typeshed / "pyrightconfig.stricter.json"
    pyrightconfig_path.write_text(pyrightconfig, encoding="utf-8")
    pyright_strictness = get_pyright_strictness(
        package_name=package_to_test, typeshed_dir=maybe_stringize_path(typeshed)
    )
    expected_result = PyrightSetting[pyright_setting_name]
    assert pyright_strictness is expected_result


# =========================
# Tests for tmpdir_typeshed
# =========================


@pytest.mark.requires_network
def test_tmpdir_typeshed() -> None:
    with tmpdir_typeshed() as typeshed:
        typeshed = typeshed  # noqa: SIM909
        assert isinstance(typeshed, Path)
        assert typeshed.exists()
        assert typeshed.is_dir()
        stubs_dir, stdlib_dir = typeshed / "stubs", typeshed / "stdlib"
        assert stubs_dir.exists()
        assert stubs_dir.is_dir()
        assert stdlib_dir.exists()
        assert stdlib_dir.is_dir()
    assert not typeshed.exists()
    assert not stubs_dir.exists()
    assert not stdlib_dir.exists()


# ======================
# Tests for gather_stats
# ======================


@pytest.mark.parametrize("pass_none", [True, False])
def test_gather_stats_no_network_access(
    typeshed: Path,
    example_stub_source: str,
    maybe_stringize_path: Callable[[Path], Path | str],
    pyrightconfig_template: str,
    EXAMPLE_PACKAGE_NAME: str,
    pass_none: bool,
) -> None:
    # The typeshed fixture comes with a package directory
    # for EXAMPLE_PACKAGE_NAME already built.
    # This is useful for most tests, but not for this one;
    # the first thing to do here is to remove it.
    (typeshed / "stubs" / EXAMPLE_PACKAGE_NAME).rmdir()

    pyrightconfig_path = typeshed / "pyrightconfig.stricter.json"
    pyrightconfig_path.write_text(pyrightconfig_template.format(""), encoding="utf-8")

    package_names = {"emoji", "protobuf", "appdirs"}
    for package_name in package_names:
        package_dir = typeshed / "stubs" / package_name
        package_dir.mkdir()
        write_metadata_text(typeshed, package_name, "\n")
        source_dir = package_dir / package_name
        source_dir.mkdir()
        (source_dir / "foo.pyi").write_text(example_stub_source, encoding="utf-8")

    typeshed_dir_to_pass = maybe_stringize_path(typeshed)

    packages_to_pass: set[str] | None
    packages_to_pass = None if pass_none else (package_names | {"stdlib"})

    with mock.patch.object(
        typeshed_stats.gather,
        "get_package_status",
        autospec=True,
        return_value=PackageStatus.UP_TO_DATE,
    ):
        results = gather_stats(packages_to_pass, typeshed_dir=typeshed_dir_to_pass)

    assert all(isinstance(item, PackageStats) for item in results)
    package_names_in_results = {item.package_name for item in results}
    expected_package_names = package_names | {"stdlib"}
    assert package_names_in_results == expected_package_names


@pytest.mark.requires_network
def test_gather_stats_integrates_with_tmpdir_typeshed() -> None:
    with tmpdir_typeshed() as typeshed:
        available_stubs = os.listdir(typeshed / "stubs")
        package_names = {
            random.choice(available_stubs) for _ in range(random.randint(3, 10))
        }
        print(f"Testing with {package_names}")
        results = gather_stats(package_names, typeshed_dir=typeshed)

    assert all(isinstance(item, PackageStats) for item in results)
    package_names_in_results = {item.package_name for item in results}
    assert package_names_in_results == package_names


def test_exceptions_bubble_up(typeshed: Path) -> None:
    with pytest.raises(KeyError), mock.patch.object(
        typeshed_stats.gather,
        "gather_stats_on_package",
        autospec=True,
        side_effect=KeyError,
    ):
        gather_stats(typeshed_dir=typeshed)
