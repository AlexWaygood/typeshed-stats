# pyright: reportPrivateUsage=false,reportUnusedClass=false
from __future__ import annotations

import json
import os
import random
import sys
import textwrap
import types
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, nullcontext
from dataclasses import dataclass, field
from itertools import chain
from pathlib import Path
from typing import Final, TypeAlias
from unittest import mock

# Make sure not to import rich here, since it's an optional dependency
# Some tests assert behaviour that's predicated on rich not yet being imported
import aiohttp
import pytest
from packaging.specifiers import SpecifierSet
from packaging.version import Version
from pytest_mock import MockerFixture
from pytest_subtests import SubTests

import typeshed_stats.gather
from typeshed_stats.gather import (
    AnnotationStats,
    CompletenessLevel,
    PackageStatus,
    PyrightSetting,
    StubtestStrictness,
    StubVersion,
    UploadStatus,
    _get_pypi_data,
    gather_annotation_stats_on_file,
    gather_annotation_stats_on_package,
    gather_stats_on_file,
    gather_stats_on_multiple_packages,
    get_completeness_level,
    get_package_extra_description,
    get_package_size,
    get_package_status,
    get_pyright_setting_for_package,
    get_stub_distribution_name,
    get_stubtest_allowlist_length,
    get_stubtest_ci_platforms,
    get_stubtest_strictness,
    get_upload_status,
    get_upstream_url,
    get_version,
    tmpdir_typeshed,
)

from .conftest import PYRIGHTCONFIG_TEMPLATE, write_metadata_text

# ===================
# _NiceReprEnum tests
# ===================


def test__NiceReprEnum_docstring_equals_enum_value() -> None:
    assert StubtestStrictness.SKIPPED.__doc__ == StubtestStrictness.SKIPPED.value


@pytest.mark.parametrize("obj", [StubtestStrictness, StubtestStrictness.SKIPPED])
def test__NiceReprEnum_docstring_in_help_output(
    obj: object, capsys: pytest.CaptureFixture[str]
) -> None:
    help(obj)
    out = capsys.readouterr().out
    assert "Stubtest is skipped" in out


def test__NiceReprEnum_repr_str() -> None:
    assert repr(StubtestStrictness.SKIPPED) == "StubtestStrictness.SKIPPED"
    assert str(StubtestStrictness.SKIPPED) == repr(StubtestStrictness.SKIPPED)
    assert StubtestStrictness.SKIPPED.value not in repr(StubtestStrictness.SKIPPED)


@pytest.mark.parametrize(
    ("enum_member", "expected_formatted_name"),
    [
        pytest.param(
            StubtestStrictness.ERROR_ON_MISSING_STUB,
            "error on missing stub",
            id="StubtestStrictness",
        ),
        pytest.param(
            PackageStatus.NO_LONGER_UPDATED, "no longer updated", id="PackageStatus"
        ),
        pytest.param(
            PyrightSetting.STRICT_ON_SOME_FILES,
            "strict on some files",
            id="PyrightSetting",
        ),
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
            NOT_A_STRING = 1  # pyright: ignore[reportArgumentType]


# =========================================
# Tests for collecting stats on annotations
# =========================================


def test__SingleAnnotationAnalyzer___repr__() -> None:
    actual_repr = repr(typeshed_stats.gather._SingleAnnotationAnalyzer())
    expected_repr = (
        "_SingleAnnotationAnalyzer(analysis=_SingleAnnotationAnalysis("
        "Any_in_annotation=False, Incomplete_in_annotation=False"
        "))"
    )
    assert actual_repr == expected_repr


def test__AnnotationStatsCollector___repr__() -> None:
    actual_repr = repr(typeshed_stats.gather._AnnotationStatsCollector())
    expected_repr = f"_AnnotationStatsCollector(stats={AnnotationStats()})"
    assert actual_repr == expected_repr


def test_annotation_stats_on_file(
    subtests: SubTests,
    example_stub_source: str,
    expected_stats_on_example_stub_file: AnnotationStats,
    tmp_path: Path,
    maybe_stringize_path: Callable[[Path], Path | str],
    AnnotationStats_fieldnames: tuple[str, ...],
) -> None:
    test_dot_pyi = tmp_path / "test.pyi"
    test_dot_pyi.write_text(example_stub_source, encoding="utf-8")
    stats = gather_annotation_stats_on_file(maybe_stringize_path(test_dot_pyi))

    for field_name in AnnotationStats_fieldnames:
        actual_stat = getattr(stats, field_name)
        expected_stat = getattr(expected_stats_on_example_stub_file, field_name)
        with subtests.test(
            field_name=field_name, expected_stat=expected_stat, actual_stat=actual_stat
        ):
            assert actual_stat == expected_stat


@pytest.fixture
def typeshed_with_pyi_packages(
    typeshed: Path, EXAMPLE_PACKAGE_NAME: str, example_stub_source: str
) -> Path:
    package_dir = typeshed / "stubs" / EXAMPLE_PACKAGE_NAME
    stdlib_dir = typeshed / "stdlib"

    for directory in (stdlib_dir, package_dir):
        for filename in ("test1.pyi", "test2.pyi"):
            (directory / filename).write_text(example_stub_source, encoding="utf-8")

    return typeshed


@pytest.fixture(params=[True, False], ids=["test_stdlib", "test_package"])
def package_to_test(request: pytest.FixtureRequest, EXAMPLE_PACKAGE_NAME: str) -> str:
    return "stdlib" if request.param else EXAMPLE_PACKAGE_NAME


def test_annotation_stats_on_package(
    subtests: SubTests,
    typeshed_with_pyi_packages: Path,
    expected_stats_on_example_stub_file: AnnotationStats,
    maybe_stringize_path: Callable[[Path], Path | str],
    AnnotationStats_fieldnames: tuple[str, ...],
    package_to_test: str,
) -> None:
    typeshed_dir_to_pass = maybe_stringize_path(typeshed_with_pyi_packages)
    result = gather_annotation_stats_on_package(
        package_to_test, typeshed_dir=typeshed_dir_to_pass
    )
    for field_name in AnnotationStats_fieldnames:
        actual_stat = getattr(result, field_name)
        expected_stat = 2 * getattr(expected_stats_on_example_stub_file, field_name)
        with subtests.test(
            field_name=field_name, expected_stat=expected_stat, actual_stat=actual_stat
        ):
            assert actual_stat == expected_stat


# =======================================
# Tests for get_package_extra_description
# =======================================


def test_get_package_extra_description_stdlib() -> None:
    result = get_package_extra_description("stdlib", typeshed_dir=".")
    assert result is None


def test_get_package_extra_description_with_no_description(
    typeshed: Path,
    EXAMPLE_PACKAGE_NAME: str,
    maybe_stringize_path: Callable[[Path], Path | str],
) -> None:
    write_metadata_text(typeshed, EXAMPLE_PACKAGE_NAME, "\n")
    result = get_package_extra_description(
        EXAMPLE_PACKAGE_NAME, typeshed_dir=maybe_stringize_path(typeshed)
    )
    assert result is None


def test_get_package_extra_description_with_description(
    typeshed: Path,
    EXAMPLE_PACKAGE_NAME: str,
    maybe_stringize_path: Callable[[Path], Path | str],
) -> None:
    description = "foo bar baz"
    write_metadata_text(
        typeshed, EXAMPLE_PACKAGE_NAME, f"extra_description = {description!r}"
    )
    result = get_package_extra_description(
        EXAMPLE_PACKAGE_NAME, typeshed_dir=maybe_stringize_path(typeshed)
    )
    assert result == description


# ==============================
# Tests for get_stubtest_strictness
# ==============================


def test_get_stubtest_strictness_stdlib(typeshed: Path) -> None:
    result = get_stubtest_strictness("stdlib", typeshed_dir=typeshed)
    assert result is StubtestStrictness.ERROR_ON_MISSING_STUB


def test_get_stubtest_strictness_non_stdlib_no_stubtest_section(
    EXAMPLE_PACKAGE_NAME: str, typeshed: Path
) -> None:
    write_metadata_text(typeshed, EXAMPLE_PACKAGE_NAME, "\n")
    result = get_stubtest_strictness(EXAMPLE_PACKAGE_NAME, typeshed_dir=typeshed)
    assert result is StubtestStrictness.ERROR_ON_MISSING_STUB


@pytest.mark.parametrize(
    ("metadata_contents", "expected_result_name"),
    [
        pytest.param("", "ERROR_ON_MISSING_STUB", id="empty_metadata"),
        pytest.param("skip = false", "ERROR_ON_MISSING_STUB", id="skip=False"),
        pytest.param(
            "ignore_missing_stub = true",
            "MISSING_STUBS_IGNORED",
            id="ignore_missing_stub=true",
        ),
        pytest.param("skip = true", "SKIPPED", id="explicitly_skipped_stubtest"),
        pytest.param("ci_platforms = []", "SKIPPED", id="implicitly_skipped_stubtest"),
        pytest.param(
            "skip = true\nignore_missing_stub = true", "SKIPPED", id="skipped_stubtest2"
        ),
        pytest.param(
            "skip = true\nignore_missing_stub = false",
            "SKIPPED",
            id="skipped_stubtest3",
        ),
        pytest.param(
            "ignore_missing_stub = false",
            "ERROR_ON_MISSING_STUB",
            id="ignore_missing_stub=false",
        ),
    ],
)
def test_get_stubtest_strictness_non_stdlib_with_stubtest_section(
    EXAMPLE_PACKAGE_NAME: str,
    typeshed: Path,
    metadata_contents: str,
    expected_result_name: str,
    maybe_stringize_path: Callable[[Path], Path | str],
) -> None:
    write_metadata_text(
        typeshed, EXAMPLE_PACKAGE_NAME, f"[tool.stubtest]\n{metadata_contents}"
    )
    actual_result = get_stubtest_strictness(
        EXAMPLE_PACKAGE_NAME, typeshed_dir=maybe_stringize_path(typeshed)
    )
    expected_result = StubtestStrictness[expected_result_name]
    assert actual_result is expected_result


# ==============================
# Tests for get_stubtest_platform
# ==============================


def test_get_stubtest_platform_stdlib() -> None:
    result = get_stubtest_ci_platforms("stdlib", typeshed_dir=Path("."))
    assert len(result) == len(set(result))
    assert set(result) == {"linux", "darwin", "win32"}
    assert sorted(result) == result


@pytest.mark.parametrize(
    ("metadata_contents", "expected_result"),
    [
        pytest.param("[tool.stubtest]\nskip = true", [], id="Skipped stubtest"),
        pytest.param(
            "[tool.stubtest]\nci_platforms = ['win32', 'darwin']",
            ["darwin", "win32"],
            id="Platforms specified",
        ),
        pytest.param("", ["linux"], id="Empty_metadata"),
        pytest.param(
            "[tool.stubtest]\nignore_missing_stub = true",
            ["linux"],
            id="Platforms unspecified",
        ),
    ],
)
def test_get_stubtest_platform_non_stdlib(
    metadata_contents: str,
    expected_result: list[str],
    EXAMPLE_PACKAGE_NAME: str,
    typeshed: Path,
    maybe_stringize_path: Callable[[Path], Path | str],
) -> None:
    write_metadata_text(typeshed, EXAMPLE_PACKAGE_NAME, metadata_contents)
    actual_result = get_stubtest_ci_platforms(
        EXAMPLE_PACKAGE_NAME, typeshed_dir=maybe_stringize_path(typeshed)
    )
    assert actual_result == expected_result
    assert actual_result == sorted(actual_result)


# ==============================
# Tests for get_stubtest_allowlist_length
# ==============================


def test_get_stubtest_allowlist_length_stdlib(
    typeshed: Path, maybe_stringize_path: Callable[[Path], Path | str]
) -> None:
    tests_dir = typeshed / "stdlib" / "@tests"
    tests_dir.mkdir()
    allowlist_dir = tests_dir / "stubtest_allowlists"
    allowlist_dir.mkdir()
    (allowlist_dir / "darwin.txt").write_text(
        textwrap.dedent(
            """\
            foo
            bar
            # a comment
            baz
            """
        )
    )
    (allowlist_dir / "py3_common.txt").write_text(
        textwrap.dedent(
            """\
            bob
            alice
            steve


            # a comment
            """
        )
    )
    result = get_stubtest_allowlist_length(
        "stdlib", typeshed_dir=maybe_stringize_path(typeshed)
    )
    assert type(result) is int
    assert result == 6


def test_get_stubtest_allowlist_length_non_stdlib_no_allowlist(
    EXAMPLE_PACKAGE_NAME: str,
    typeshed: Path,
    maybe_stringize_path: Callable[[Path], Path | str],
) -> None:
    result = get_stubtest_allowlist_length(
        EXAMPLE_PACKAGE_NAME, typeshed_dir=maybe_stringize_path(typeshed)
    )
    assert type(result) is int
    assert result == 0


def test_get_stubtest_allowlist_length_non_stdlib_with_allowlist(
    EXAMPLE_PACKAGE_NAME: str,
    typeshed: Path,
    maybe_stringize_path: Callable[[Path], Path | str],
) -> None:
    allowlist_dir = typeshed / "stubs" / EXAMPLE_PACKAGE_NAME / "@tests"
    allowlist_dir.mkdir()
    (allowlist_dir / "stubtest_allowlist.txt").write_text(
        textwrap.dedent(
            """\
            foo
            bar
            # a comment
            baz
            """
        )
    )
    (allowlist_dir / "stubtest_allowlist_win32.txt").write_text(
        textwrap.dedent(
            """\
            bob
            alice
            steve


            # a comment
            """
        )
    )
    result = get_stubtest_allowlist_length(
        EXAMPLE_PACKAGE_NAME, typeshed_dir=maybe_stringize_path(typeshed)
    )
    assert type(result) is int
    assert result == 6


# =================================
# Tests for get_package_status
# =================================


@pytest.mark.parametrize(
    ("package_name", "expected_result_name"),
    [
        pytest.param("stdlib", "STDLIB", id="stdlib"),
        pytest.param("gdb", "NOT_ON_PYPI", id="gdb"),
    ],
)
async def test_get_package_status_special_cases(
    package_name: str,
    expected_result_name: str,
    maybe_stringize_path: Callable[[Path], Path | str],
) -> None:
    typeshed_dir = maybe_stringize_path(Path("."))
    status = await get_package_status(package_name, typeshed_dir=typeshed_dir)
    expected_result = PackageStatus[expected_result_name]
    assert status is expected_result


@pytest.mark.parametrize(
    ("metadata_to_write", "expected_result_name"),
    [
        pytest.param('obsolete_since = "3.1.0"', "OBSOLETE", id="obsolete"),
        pytest.param(
            "no_longer_updated = true", "NO_LONGER_UPDATED", id="no_longer_updated"
        ),
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
        pytest.param("0.8.*", "0.8.3", "UP_TO_DATE", id="case1"),
        pytest.param("0.8.*", "0.9.3", "OUT_OF_DATE", id="case2"),
        pytest.param("0.8.*", "1.8", "OUT_OF_DATE", id="case3"),
        pytest.param("1.*", "1.1", "UP_TO_DATE", id="case4"),
        pytest.param("1.*", "1.1.1", "UP_TO_DATE", id="case5"),
        pytest.param("1.*", "2", "OUT_OF_DATE", id="case6"),
        pytest.param("1.0.*", "1.0.1", "UP_TO_DATE", id="case7"),
        pytest.param("1.0.*", "1.0.2", "UP_TO_DATE", id="case8"),
        pytest.param("1.0.*", "1.1", "OUT_OF_DATE", id="case9"),
        pytest.param("1.64.72", "1.64.72", "UP_TO_DATE", id="case10"),
        pytest.param("1.64.72", "1.64.73", "OUT_OF_DATE", id="case11"),
        pytest.param("2022.9.13", "2022.9.13", "UP_TO_DATE", id="case12"),
        pytest.param("2022.9.13", "2022.10.22", "OUT_OF_DATE", id="case13"),
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

    # mock.patch has to be inline here,
    # since pypi_version is being parametrized
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
# Tests for get_upload_status
# =================================


def test_get_upload_status_stdlib() -> None:
    result = get_upload_status("stdlib", typeshed_dir=Path("."))
    assert result is UploadStatus.NOT_CURRENTLY_UPLOADED


@pytest.mark.parametrize(
    ("metadata_text", "expected_result_name"),
    [
        pytest.param("upload = false", "NOT_CURRENTLY_UPLOADED", id="not_uploaded"),
        pytest.param("upload = true", "UPLOADED", id="explicitly_uploaded"),
        pytest.param("", "UPLOADED", id="implicitly_uploaded"),
    ],
)
def test_get_upload_status_non_stdlib(
    metadata_text: str,
    expected_result_name: str,
    typeshed: Path,
    EXAMPLE_PACKAGE_NAME: str,
    maybe_stringize_path: Callable[[Path], Path | str],
) -> None:
    write_metadata_text(typeshed, EXAMPLE_PACKAGE_NAME, metadata_text)
    actual_result = get_upload_status(
        EXAMPLE_PACKAGE_NAME, typeshed_dir=maybe_stringize_path(typeshed)
    )
    expected_result = UploadStatus[expected_result_name]
    assert actual_result is expected_result


# =================================
# Tests for get_version
# =================================


def test_get_version_stdlib() -> None:
    result = get_version("stdlib", typeshed_dir=Path("."))
    assert result == StubVersion("==0.0.0")


@pytest.mark.parametrize(
    ("metadata_text", "expected_result"),
    [
        pytest.param(
            'version = "0.4.*"', StubVersion("==0.4.*"), id="implicit_eqeq_star"
        ),
        pytest.param('version = "~=2.32.4"', StubVersion("~=2.32.4"), id="tilde"),
    ],
)
def test_get_version_non_stdlib(
    metadata_text: str,
    expected_result: str,
    typeshed: Path,
    EXAMPLE_PACKAGE_NAME: str,
    maybe_stringize_path: Callable[[Path], Path | str],
) -> None:
    write_metadata_text(typeshed, EXAMPLE_PACKAGE_NAME, metadata_text)
    actual_result = get_version(
        EXAMPLE_PACKAGE_NAME, typeshed_dir=maybe_stringize_path(typeshed)
    )
    assert actual_result == expected_result


def test_get_version_no_version(
    typeshed: Path,
    EXAMPLE_PACKAGE_NAME: str,
    maybe_stringize_path: Callable[[Path], Path | str],
) -> None:
    write_metadata_text(typeshed, EXAMPLE_PACKAGE_NAME, "")
    with pytest.raises(KeyError):
        get_version(EXAMPLE_PACKAGE_NAME, typeshed_dir=maybe_stringize_path(typeshed))


# =================================
# Tests for get_upstream_url
# =================================


def test_upstream_url_stdlib() -> None:
    result = get_upstream_url("stdlib", typeshed_dir=Path("."))
    assert result == "https://github.com/python/cpython"


@pytest.mark.parametrize(
    ("metadata_text", "expected_upstream_url"),
    [
        pytest.param(
            'upstream_repository = "https://github.com/psf/requests"',
            "https://github.com/psf/requests",
            id="upstream_repo_given",
        ),
        pytest.param("", None, id="upstream_repo_not_given"),
    ],
)
def test_get_upstream_url_non_stdlib(
    metadata_text: str,
    expected_upstream_url: str,
    typeshed: Path,
    EXAMPLE_PACKAGE_NAME: str,
    maybe_stringize_path: Callable[[Path], Path | str],
) -> None:
    write_metadata_text(typeshed, EXAMPLE_PACKAGE_NAME, metadata_text)
    actual_result = get_upstream_url(
        EXAMPLE_PACKAGE_NAME, typeshed_dir=maybe_stringize_path(typeshed)
    )
    assert actual_result == expected_upstream_url
    assert type(actual_result) is type(expected_upstream_url)


# =================================
# Tests for get_completeness_level
# =================================


def test_get_completeness_level_stdlib() -> None:
    result = get_completeness_level("stdlib", typeshed_dir=Path("."))
    assert result is CompletenessLevel.STDLIB


@pytest.mark.parametrize(
    ("metadata_text", "expected_completeness_level"),
    [
        pytest.param("partial_stub = true", "PARTIAL", id="partial"),
        pytest.param("partial_stub = false", "COMPLETE", id="explicitly_complete"),
        pytest.param("", "COMPLETE", id="implicitly_complete"),
    ],
)
def test_get_completeness_level_non_stdlib(
    metadata_text: str,
    expected_completeness_level: str,
    typeshed: Path,
    EXAMPLE_PACKAGE_NAME: str,
    maybe_stringize_path: Callable[[Path], Path | str],
) -> None:
    write_metadata_text(typeshed, EXAMPLE_PACKAGE_NAME, metadata_text)
    actual_result = get_completeness_level(
        EXAMPLE_PACKAGE_NAME, typeshed_dir=maybe_stringize_path(typeshed)
    )
    expected_result = CompletenessLevel[expected_completeness_level]
    assert actual_result is expected_result


# ======================================
# Tests for get_stub_distribution_name()
# ======================================


def test_get_stub_distribution_name_stdlib() -> None:
    result = get_stub_distribution_name("stdlib", typeshed_dir=Path("."))
    assert result == "-"


def test_get_stub_distribution_name_not_in_metadata(
    typeshed: Path,
    EXAMPLE_PACKAGE_NAME: str,
    maybe_stringize_path: Callable[[Path], Path | str],
) -> None:
    write_metadata_text(typeshed, EXAMPLE_PACKAGE_NAME, "\n")
    actual_result = get_stub_distribution_name(
        EXAMPLE_PACKAGE_NAME, typeshed_dir=maybe_stringize_path(typeshed)
    )
    assert actual_result == f"types-{EXAMPLE_PACKAGE_NAME}"


def test_get_stub_distribution_name_in_metadata(
    typeshed: Path,
    EXAMPLE_PACKAGE_NAME: str,
    maybe_stringize_path: Callable[[Path], Path | str],
) -> None:
    write_metadata_text(
        typeshed, EXAMPLE_PACKAGE_NAME, 'stub_distribution = "idk-something-random"'
    )
    actual_result = get_stub_distribution_name(
        EXAMPLE_PACKAGE_NAME, typeshed_dir=maybe_stringize_path(typeshed)
    )
    assert actual_result == "idk-something-random"


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


@pytest.fixture
def typeshed_with_eightline_multifile_package(
    typeshed: Path, EXAMPLE_PACKAGE_NAME: str
) -> Path:
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
    return typeshed


def test_get_package_size_multiple_files(
    EXAMPLE_PACKAGE_NAME: str,
    typeshed_with_eightline_multifile_package: Path,
    maybe_stringize_path: Callable[[Path], Path | str],
) -> None:
    typeshed_dir_to_pass = maybe_stringize_path(
        typeshed_with_eightline_multifile_package
    )
    result = get_package_size(EXAMPLE_PACKAGE_NAME, typeshed_dir=typeshed_dir_to_pass)
    assert result == 8


# ================================
# Tests for get_pyright_setting_for_package
# ================================


@dataclass
class PyrightTestCase:
    package_to_test: str
    expected_result: str
    entirely_excluded_path: str = ""
    path_excluded_from_strict: str = ""
    pyrightconfig_basic: str = field(init=False, repr=False)
    pyrightconfig_strict: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        default_path = "foo.pyi"
        self.entirely_excluded_path = self.entirely_excluded_path or default_path
        self.pyrightconfig_basic = PYRIGHTCONFIG_TEMPLATE.format(
            f'"{self.entirely_excluded_path}"'
        )
        self.excluded_from_strict = self.path_excluded_from_strict or default_path
        self.pyrightconfig_strict = PYRIGHTCONFIG_TEMPLATE.format(
            f'"{self.excluded_from_strict}"'
        )


PYRIGHT_TEST_CASES: Final = (
    # Some files are entirely excluded, none are excluded from strict settings
    PyrightTestCase(
        entirely_excluded_path="stdlib",
        package_to_test="stdlib",
        expected_result="ENTIRELY_EXCLUDED",
    ),
    PyrightTestCase(
        entirely_excluded_path="stdlib/**/*.pyi",
        package_to_test="stdlib",
        expected_result="ENTIRELY_EXCLUDED",
    ),
    PyrightTestCase(
        entirely_excluded_path="stdlib/tkinter",
        package_to_test="stdlib",
        expected_result="SOME_FILES_EXCLUDED",
    ),
    PyrightTestCase(
        entirely_excluded_path="stdlib/lib2to3/fixes/*.pyi",
        package_to_test="stdlib",
        expected_result="SOME_FILES_EXCLUDED",
    ),
    PyrightTestCase(
        entirely_excluded_path="stdlib",
        package_to_test="boto",
        expected_result="STRICT",
    ),
    PyrightTestCase(
        entirely_excluded_path="stubs",
        package_to_test="aiofiles",
        expected_result="ENTIRELY_EXCLUDED",
    ),
    PyrightTestCase(
        entirely_excluded_path="stubs/aiofiles",
        package_to_test="aiofiles",
        expected_result="ENTIRELY_EXCLUDED",
    ),
    PyrightTestCase(
        entirely_excluded_path="stubs/aiofiles/**/*.pyi",
        package_to_test="aiofiles",
        expected_result="ENTIRELY_EXCLUDED",
    ),
    PyrightTestCase(
        entirely_excluded_path="stubs/aiofiles",
        package_to_test="boto",
        expected_result="STRICT",
    ),
    # No files are entirely excluded, some are excluded from strict settings
    PyrightTestCase(
        path_excluded_from_strict="stdlib",
        package_to_test="stdlib",
        expected_result="NOT_STRICT",
    ),
    PyrightTestCase(
        path_excluded_from_strict="stdlib/**/*.pyi",
        package_to_test="stdlib",
        expected_result="NOT_STRICT",
    ),
    PyrightTestCase(
        path_excluded_from_strict="stdlib/tkinter",
        package_to_test="stdlib",
        expected_result="STRICT_ON_SOME_FILES",
    ),
    PyrightTestCase(
        path_excluded_from_strict="stdlib/tkinter/*.pyi",
        package_to_test="stdlib",
        expected_result="STRICT_ON_SOME_FILES",
    ),
    PyrightTestCase(
        path_excluded_from_strict="stubs",
        package_to_test="stdlib",
        expected_result="STRICT",
    ),
    PyrightTestCase(
        path_excluded_from_strict="stubs/aiofiles",
        package_to_test="stdlib",
        expected_result="STRICT",
    ),
    PyrightTestCase(
        path_excluded_from_strict="stubs/aiofiles/*.pyi",
        package_to_test="stdlib",
        expected_result="STRICT",
    ),
    PyrightTestCase(
        path_excluded_from_strict="stubs",
        package_to_test="appdirs",
        expected_result="NOT_STRICT",
    ),
    PyrightTestCase(
        path_excluded_from_strict="stubs/boto/auth.pyi",
        package_to_test="boto",
        expected_result="STRICT_ON_SOME_FILES",
    ),
    # Some files are entirely excluded, some are excluded from strict settings
    PyrightTestCase(
        entirely_excluded_path="stdlib",
        path_excluded_from_strict="stdlib/tkinter",
        package_to_test="stdlib",
        expected_result="ENTIRELY_EXCLUDED",
    ),
    PyrightTestCase(
        entirely_excluded_path="stdlib/tkinter",
        path_excluded_from_strict="stdlib/asyncio",
        package_to_test="stdlib",
        expected_result="SOME_FILES_EXCLUDED",
    ),
    PyrightTestCase(
        entirely_excluded_path="stdlib/tkinter/*.pyi",
        path_excluded_from_strict="stdlib/asyncio/*.pyi",
        package_to_test="stdlib",
        expected_result="SOME_FILES_EXCLUDED",
    ),
    PyrightTestCase(
        entirely_excluded_path="stubs",
        path_excluded_from_strict="stdlib/tkinter",
        package_to_test="stdlib",
        expected_result="STRICT_ON_SOME_FILES",
    ),
    PyrightTestCase(
        entirely_excluded_path="stdlib",
        path_excluded_from_strict="stubs/boto/auth.pyi",
        package_to_test="boto",
        expected_result="STRICT_ON_SOME_FILES",
    ),
    PyrightTestCase(
        entirely_excluded_path="stdlib/*.pyi",
        path_excluded_from_strict="stubs/boto/auth.pyi",
        package_to_test="boto",
        expected_result="STRICT_ON_SOME_FILES",
    ),
    PyrightTestCase(
        entirely_excluded_path="stubs/boto/auth.pyi",
        path_excluded_from_strict="stubs/boto/foo.pyi",
        package_to_test="boto",
        expected_result="SOME_FILES_EXCLUDED",
    ),
)


@pytest.mark.parametrize(
    "test_case",
    [pytest.param(case, id=f"case{i}") for i, case in enumerate(PYRIGHT_TEST_CASES)],
)
def test_get_pyright_setting_for_package(
    typeshed: Path,
    test_case: PyrightTestCase,
    maybe_stringize_path: Callable[[Path], Path | str],
) -> None:
    config_filenames_to_configs = {
        "pyrightconfig.json": test_case.pyrightconfig_basic,
        "pyrightconfig.stricter.json": test_case.pyrightconfig_strict,
    }

    if test_case.package_to_test == "stdlib":
        (typeshed / "stdlib" / "functools.pyi").write_text("")
    else:
        package_dir = typeshed / "stubs" / test_case.package_to_test
        package_dir.mkdir()
        (package_dir / "foo.pyi").write_text("")

    for config_filename, config in config_filenames_to_configs.items():
        with pytest.raises(json.JSONDecodeError):
            json.loads(config)

        (typeshed / config_filename).write_text(config, encoding="utf-8")

    pyright_setting = get_pyright_setting_for_package(
        package_name=test_case.package_to_test,
        typeshed_dir=maybe_stringize_path(typeshed),
    )
    expected_result = PyrightSetting[test_case.expected_result]
    assert pyright_setting is expected_result


# =========================
# Tests for tmpdir_typeshed
# =========================


@pytest.mark.requires_network
def test_tmpdir_typeshed() -> None:
    with tmpdir_typeshed() as typeshed:
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
# Tests for gather_stats_on_file
# ======================


# Tests for bad arguments passed into typeshed_dir
def test_gather_stats_on_file_bad_typeshed_dir_type() -> None:
    with pytest.raises(TypeError, match="Expected str or Path argument"):
        gather_stats_on_file("stdlib/functools.pyi", typeshed_dir=5)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]  # ty: ignore[invalid-argument-type]


def test_gather_stats_on_file_nonexistent_typeshed_dir() -> None:
    with pytest.raises(ValueError, match="does not exist"):
        gather_stats_on_file("stdlib/functools.pyi", typeshed_dir="foo/bar")


def test_gather_stats_on_file_typeshed_dir_points_to_file(tmp_path: Path) -> None:
    file = tmp_path / "foo.pyi"
    file.write_text("\n", encoding="utf-8")
    with pytest.raises(ValueError, match="is not a directory"):
        gather_stats_on_file("stdlib/functools.pyi", typeshed_dir=file)


# Tests for bad arguments passed into file_path
def test_gather_stats_on_file_bad_file_path_type() -> None:
    with pytest.raises(TypeError, match="Expected str or Path argument"):
        gather_stats_on_file(5, typeshed_dir=".")  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]  # ty: ignore[invalid-argument-type]


def test_gather_stats_on_file_nonexistent_file() -> None:
    with pytest.raises(ValueError, match="does not exist"):
        gather_stats_on_file("foo/bar.pyi", typeshed_dir=".")


def test_gather_stats_on_file_directory_passed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="does not point to a file"):
        gather_stats_on_file(tmp_path, typeshed_dir=".")


def test_gather_stats_on_file_non_pyi_file_passed(tmp_path: Path) -> None:
    file = tmp_path / "foo.py"
    file.write_text("\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"Expected a path pointing to a \.pyi file"):
        gather_stats_on_file(file, typeshed_dir=".")


# Tests for good arguments
def test_gather_stats_on_file_no_network_access(
    complete_typeshed: Path,
    real_typeshed_package_names: frozenset[str],
    maybe_stringize_path: Callable[[Path], Path | str],
) -> None:
    pyi_files = chain.from_iterable(  # pragma: no branch
        (complete_typeshed / "stubs" / package_name).rglob("*.pyi")
        for package_name in real_typeshed_package_names
    )
    typeshed_dir_to_pass = maybe_stringize_path(complete_typeshed)
    # Absolute Path passed
    gather_stats_on_file(next(pyi_files), typeshed_dir=typeshed_dir_to_pass)
    # Absolute str passed
    gather_stats_on_file(str(next(pyi_files)), typeshed_dir=typeshed_dir_to_pass)
    # Relative Path passed
    gather_stats_on_file(
        next(pyi_files).relative_to(complete_typeshed),
        typeshed_dir=typeshed_dir_to_pass,
    )
    # Relative str passed
    gather_stats_on_file(
        str(next(pyi_files).relative_to(complete_typeshed)),
        typeshed_dir=typeshed_dir_to_pass,
    )


def test_gather_stats_on_file_stdlib_file_passed(
    complete_typeshed: Path, maybe_stringize_path: Callable[[Path], Path | str]
) -> None:
    typeshed_dir_to_pass = maybe_stringize_path(complete_typeshed)
    info_on_functools = gather_stats_on_file(
        complete_typeshed / "stdlib" / "functools.pyi",
        typeshed_dir=typeshed_dir_to_pass,
    )
    assert info_on_functools.parent_package == "stdlib"
    assert info_on_functools.file_path.as_posix() == "stdlib/functools.pyi"
    assert (complete_typeshed / info_on_functools.file_path).exists()


def test_gather_stats_on_file_non_stdlib_file_passed(
    complete_typeshed: Path, maybe_stringize_path: Callable[[Path], Path | str]
) -> None:
    typeshed_dir_to_pass = maybe_stringize_path(complete_typeshed)
    info_on_appdirs = gather_stats_on_file(
        complete_typeshed / "stubs" / "appdirs" / "appdirs" / "foo.pyi",
        typeshed_dir=typeshed_dir_to_pass,
    )
    assert info_on_appdirs.parent_package == "appdirs"
    assert info_on_appdirs.file_path.as_posix() == "stubs/appdirs/appdirs/foo.pyi"
    assert (complete_typeshed / info_on_appdirs.file_path).exists()


# ======================
# Tests for gather_stats_on_multiple_packages
# ======================


@pytest.fixture
def mocked_get_package_status(mocker: MockerFixture) -> None:
    mocker.patch.object(
        typeshed_stats.gather,
        "get_package_status",
        autospec=True,
        return_value=PackageStatus.UP_TO_DATE,
    )


@pytest.mark.usefixtures("mocked_get_package_status")
@pytest.mark.parametrize(
    "pass_none",
    [pytest.param(True, id="pass_none"), pytest.param(False, id="pass_packages")],
)
def test_gather_stats__on_packages_no_network_access(
    complete_typeshed: Path,
    maybe_stringize_path: Callable[[Path], Path | str],
    pass_none: bool,
    real_typeshed_package_names: frozenset[str],
) -> None:
    typeshed_dir_to_pass = maybe_stringize_path(complete_typeshed)

    if pass_none:
        packages_to_pass: set[str] | None = None
    else:
        packages_to_pass = {"stdlib", *os.listdir(complete_typeshed / "stubs")}

    results = gather_stats_on_multiple_packages(
        packages_to_pass, typeshed_dir=typeshed_dir_to_pass
    )
    package_names_in_results = [item.package_name for item in results]
    assert package_names_in_results == sorted(package_names_in_results)
    expected_package_names = real_typeshed_package_names | {"stdlib"}
    assert set(package_names_in_results) == expected_package_names


def test_tmpdir_typeshed_with_mocked_git_clone() -> None:
    import subprocess

    with mock.patch.object(subprocess, "run", autospec=True) as run:
        assert sys.modules["subprocess"].run is run
        with tmpdir_typeshed() as typeshed:
            assert isinstance(typeshed, Path)


@pytest.mark.requires_network
@pytest.mark.dependency(name="integration_basic")
def test_gather_stats__on_packages_integrates_with_tmpdir_typeshed() -> None:
    num_packages = random.randint(3, 10)
    print(f"Testing {num_packages}")
    with tmpdir_typeshed() as typeshed:
        print(f"Typeshed dir is {typeshed!r}")
        available_stubs = os.listdir(typeshed / "stubs")
        package_names = {random.choice(available_stubs) for _ in range(num_packages)}
        print(f"Testing with {package_names}")
        results = gather_stats_on_multiple_packages(
            package_names, typeshed_dir=typeshed
        )

    package_names_in_results = [item.package_name for item in results]
    assert package_names_in_results == sorted(package_names_in_results)
    assert set(package_names_in_results) == package_names


KNOWN_FULLY_ANNOTATED_FILES_WITH_LAX_PYRIGHT_SETTINGS = frozenset({
    Path("stdlib/lib2to3/fixes/fix_imports2.pyi"),
    Path("stdlib/lib2to3/fixes/__init__.pyi"),
    Path("stdlib/xml/sax/__init__.pyi"),
})


@pytest.mark.dependency(depends=["integration_basic"])
def test_basic_sanity_checks(subtests: SubTests) -> None:
    with tmpdir_typeshed() as typeshed:
        stats_on_packages = gather_stats_on_multiple_packages(typeshed_dir=typeshed)
        stats_on_stdlib_files = [
            gather_stats_on_file(path, typeshed_dir=typeshed)
            for path in (typeshed / "stdlib").rglob("*.pyi")
        ]

    at_least_one_incomplete_package = any(  # pragma: no branch
        s.completeness_level is CompletenessLevel.PARTIAL for s in stats_on_packages
    )
    no_partial_packages_msg = "Likely bug detected: no packages are marked as partial?!"
    assert at_least_one_incomplete_package, no_partial_packages_msg

    at_least_one_complete_package = any(  # pragma: no branch
        s.completeness_level is CompletenessLevel.COMPLETE for s in stats_on_packages
    )
    no_complete_packages_msg = (
        "Likely bug detected: no packages are marked as complete?!"
    )
    assert at_least_one_complete_package, no_complete_packages_msg

    at_least_one_upstream_url = any(  # pragma: no branch
        isinstance(s.upstream_url, str) for s in stats_on_packages
    )
    no_upstream_urls_msg = "Likely bug detected: no packages list an upstream URL?!"
    assert at_least_one_upstream_url, no_upstream_urls_msg

    for s in stats_on_packages:
        with subtests.test(package_name=s.package_name):
            annot_stats = s.annotation_stats
            is_only_partially_annotated = bool(
                annot_stats.unannotated_parameters or annot_stats.unannotated_returns
            )
            is_fully_annotated = not is_only_partially_annotated
            if s.pyright_setting is PyrightSetting.STRICT:
                assert is_fully_annotated, (
                    "Likely bug detected: "
                    f"{s.package_name!r} has unannotated parameters and/or returns, "
                    "but has the strictest pyright settings in CI"
                )
            else:
                assert is_only_partially_annotated, (
                    "Likely bug detected: "
                    f"{s.package_name!r} is fully annotated, "
                    "but does not have the strictest pyright settings in CI"
                )
            upstream_url = s.upstream_url
            assert isinstance(upstream_url, str | types.NoneType)
            if upstream_url is not None:
                assert upstream_url.startswith("https://")
    for f in stats_on_stdlib_files:
        if Path("stdlib/distutils/command") in f.file_path.parents:
            continue
        with subtests.test(path=f.file_path):
            annot_stats = f.annotation_stats
            is_only_partially_annotated = bool(
                annot_stats.unannotated_parameters or annot_stats.unannotated_returns
            )
            is_fully_annotated = not is_only_partially_annotated
            if f.pyright_setting is PyrightSetting.STRICT:
                assert is_fully_annotated, (
                    "Likely bug detected: "
                    f"{f.file_path!r} has unannotated parameters and/or returns, "
                    "but has the strictest pyright settings in CI"
                )
            elif (
                f.file_path not in KNOWN_FULLY_ANNOTATED_FILES_WITH_LAX_PYRIGHT_SETTINGS
            ):
                assert is_only_partially_annotated, (
                    "Likely bug detected: "
                    f"{f.file_path!r} is fully annotated, "
                    "but does not have the strictest pyright settings in CI"
                )


def test_exceptions_bubble_up(typeshed: Path) -> None:
    with (
        pytest.raises(ExceptionGroup) as exc_info,
        mock.patch.object(
            typeshed_stats.gather,
            "gather_stats_on_package",
            autospec=True,
            side_effect=KeyError,
        ),
    ):
        gather_stats_on_multiple_packages(typeshed_dir=typeshed)
    assert isinstance(exc_info.value, ExceptionGroup)
    assert any(isinstance(exc, KeyError) for exc in exc_info.value.exceptions)


def test_stub_version_repr() -> None:
    version = StubVersion("==1.2.*")
    assert repr(version) == "StubVersion('==1.2.*')"
    assert SpecifierSet.__repr__(version) == "<SpecifierSet('==1.2.*')>"
