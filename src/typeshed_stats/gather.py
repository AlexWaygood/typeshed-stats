"""Tools for gathering stats about typeshed packages."""

import ast
import asyncio
import json
import os
import re
import sys
import urllib.parse
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import AsyncExitStack, contextmanager
from enum import Enum
from functools import cache
from pathlib import Path
from typing import Any, Protocol, TypeAlias, TypeVar, final

import aiohttp
import attrs
from packaging.specifiers import SpecifierSet
from packaging.version import Version

if sys.version_info < (3, 10):
    raise ImportError("Python 3.10+ is required!")

if sys.version_info >= (3, 11):
    import tomllib  # pragma: no cover
else:
    import tomli as tomllib  # pragma: no cover


__all__ = [
    "AnnotationStats",
    "PackageName",
    "PackageStats",
    "PackageStatus",
    "PyrightSetting",
    "StubtestSetting",
    "gather_annotation_stats_on_file",
    "gather_annotation_stats_on_package",
    "gather_stats",
    "gather_stats_on_package",
    "get_package_size",
    "get_package_status",
    "get_pyright_strictness",
    "get_stubtest_setting",
]

PackageName: TypeAlias = str
_NiceReprEnumSelf = TypeVar("_NiceReprEnumSelf", bound="_NiceReprEnum")


class _NiceReprEnum(Enum):
    """Base class for several public-API enums in this package."""

    def __new__(cls: type[_NiceReprEnumSelf], doc: str) -> _NiceReprEnumSelf:
        assert isinstance(doc, str)
        member = object.__new__(cls)
        member._value_ = member.__doc__ = doc
        return member

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}.{self.name}"

    @property
    def formatted_name(self) -> str:
        return " ".join(self.name.split("_")).lower()


@attrs.define
class _SingleAnnotationAnalyzer(ast.NodeVisitor):
    Any_in_annotation: bool = False
    Incomplete_in_annotation: bool = False

    def visit_Name(self, node: ast.Name) -> None:
        match node.id:
            case "Any":
                self.Any_in_annotation = True
            case "Incomplete":
                self.Incomplete_in_annotation = True
            case _:
                pass

    def visit_Attribute(self, node: ast.Attribute) -> None:
        match node.value, node.attr:
            case [ast.Name("typing"), "Any"]:
                self.Any_in_annotation = True
            case [ast.Name("_typeshed"), "Incomplete"]:
                self.Incomplete_in_annotation = True
            case _:
                pass
        self.generic_visit(node)


class _SingleAnnotationAnalysis(Protocol):
    Any_in_annotation: bool
    Incomplete_in_annotation: bool


def _analyse_annotation(annotation: ast.AST) -> _SingleAnnotationAnalysis:
    analyser = _SingleAnnotationAnalyzer()
    analyser.visit(annotation)
    return analyser


@final
@attrs.define
class AnnotationStats:
    """Stats on the annotations for a source file or a directory of source files."""

    annotated_parameters: int = 0
    unannotated_parameters: int = 0
    annotated_returns: int = 0
    unannotated_returns: int = 0
    explicit_Incomplete_parameters: int = 0
    explicit_Incomplete_returns: int = 0
    explicit_Any_parameters: int = 0
    explicit_Any_returns: int = 0
    annotated_variables: int = 0
    explicit_Any_variables: int = 0
    explicit_Incomplete_variables: int = 0


class _AnnotationStatsCollector(ast.NodeVisitor):
    """AST Visitor for collecting stats on a single stub file."""

    def __init__(self) -> None:
        self.stats = AnnotationStats()
        self._class_nesting = 0
        self._function_decorators: frozenset[str] = frozenset()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(stats={self.stats})"

    @property
    def in_class(self) -> bool:
        """Return `True` if we're currently visiting a class definition."""
        return bool(self._class_nesting)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._class_nesting += 1
        self.generic_visit(node)
        self._class_nesting -= 1

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.stats.annotated_variables += 1
        analysis = _analyse_annotation(node.annotation)
        if analysis.Any_in_annotation:
            self.stats.explicit_Any_variables += 1
        if analysis.Incomplete_in_annotation:
            self.stats.explicit_Incomplete_variables += 1
        self.generic_visit(node)

    def visit_arg(self, node: ast.arg) -> None:
        self.generic_visit(node)

        # We don't want self/cls/metacls/mcls arguments to count towards the statistics
        if self.in_class and "staticmethod" not in self._function_decorators:
            if "classmethod" in self._function_decorators:
                if node.arg in {"cls", "metacls", "mcls"}:
                    return
            elif node.arg == "self":
                return

        annotation = node.annotation
        if annotation is None:
            self.stats.unannotated_parameters += 1
        else:
            self.stats.annotated_parameters += 1
            analysis = _analyse_annotation(annotation)
            if analysis.Any_in_annotation:
                self.stats.explicit_Any_parameters += 1
            if analysis.Incomplete_in_annotation:
                self.stats.explicit_Incomplete_parameters += 1

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        returns = node.returns
        if returns is None:
            self.stats.unannotated_returns += 1
        else:
            self.stats.annotated_returns += 1
            analysis = _analyse_annotation(returns)
            if analysis.Any_in_annotation:
                self.stats.explicit_Any_returns += 1
            if analysis.Incomplete_in_annotation:
                self.stats.explicit_Incomplete_returns += 1

        old_function_decorators = self._function_decorators
        self._function_decorators = frozenset(
            decorator.id
            for decorator in node.decorator_list
            if isinstance(decorator, ast.Name)
        )
        self.generic_visit(node)
        self._function_decorators = old_function_decorators

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)


def gather_annotation_stats_on_file(path: Path | str) -> AnnotationStats:
    """Gather annotation stats on a single typeshed stub file.

    Args:
        path: The location of the file to be analysed.

    Returns:
        An `AnnotationStats` object containing data
        about the annotations in the file.
    """
    visitor = _AnnotationStatsCollector()
    with open(path, encoding="utf-8") as file:
        visitor.visit(ast.parse(file.read()))
    return visitor.stats


@cache
def _get_package_directory(package_name: PackageName, typeshed_dir: Path | str) -> Path:
    if package_name == "stdlib":
        return Path(typeshed_dir, "stdlib")
    return Path(typeshed_dir, "stubs", package_name)


def gather_annotation_stats_on_package(
    package_name: PackageName, *, typeshed_dir: Path | str
) -> AnnotationStats:
    """Aggregate annotation stats on a typeshed stubs package.

    Args:
        package_name: The name of the stubs package to analyze.
        typeshed_dir: A path pointing to the location of a typeshed directory
          in which to find the stubs package source.

    Returns:
        An `AnnotationStats` object containing data
        about the annotations in the package.
    """
    package_directory = _get_package_directory(package_name, typeshed_dir)
    file_results = [
        gather_annotation_stats_on_file(path)
        for path in package_directory.rglob("*.pyi")
    ]
    # Sum all the statistics together, to get the statistics for the package as a whole
    #
    # TODO: we're throwing away information here.
    # It might be nice to have a way to get per-file stats, especially for the stdlib.
    package_stats: Counter[str] = sum(
        [Counter(attrs.asdict(result)) for result in file_results], start=Counter()
    )
    return AnnotationStats(**package_stats)


@cache
def _get_package_metadata(
    package_name: PackageName, typeshed_dir: Path | str
) -> Mapping[str, Any]:
    package_directory = _get_package_directory(package_name, typeshed_dir)
    with open(package_directory / "METADATA.toml", "rb") as f:
        return tomllib.load(f)


class StubtestSetting(_NiceReprEnum):
    """Enumeration of the various possible settings typeshed uses for stubtest in CI."""

    SKIPPED = "Stubtest is skipped in CI for this package."
    MISSING_STUBS_IGNORED = (
        "The `--ignore-missing-stub` stubtest setting is used in CI."
    )
    ERROR_ON_MISSING_STUB = (
        "Objects missing from the stub cause stubtest to emit an error in CI."
    )


def get_stubtest_setting(
    package_name: str, *, typeshed_dir: Path | str
) -> StubtestSetting:
    """Get the setting typeshed uses in CI when stubtest is run on a certain package.

    Args:
        package_name: The name of the package to find the stubtest setting for.
        typeshed_dir: A path pointing to a typeshed directory,
          from which to retrieve the stubtest setting.

    Returns:
        A member of the `StubtestSetting` enumeration
        (see the docs on `StubtestSetting` for details).
    """
    if package_name == "stdlib":
        return StubtestSetting.ERROR_ON_MISSING_STUB
    metadata = _get_package_metadata(package_name, typeshed_dir)
    stubtest_settings = metadata.get("tool", {}).get("stubtest", {})
    if stubtest_settings.get("skip", False):
        return StubtestSetting.SKIPPED
    ignore_missing_stub_used = stubtest_settings.get("ignore_missing_stub", True)
    return StubtestSetting[
        "MISSING_STUBS_IGNORED" if ignore_missing_stub_used else "ERROR_ON_MISSING_STUB"
    ]


class PackageStatus(_NiceReprEnum):
    """The various states of freshness/staleness a stubs package can be in."""

    STDLIB = (
        "These are the stdlib stubs. Typeshed's stdlib stubs are generally fairly"
        " up to date, and tested against all currently supported Python versions"
        " in CI."
    )
    NOT_ON_PYPI = (
        "The upstream for this package doesn't exist on PyPI,"
        " so whether or not these stubs are up to date or not is unknown."
    )
    OBSOLETE = "Upstream has added type hints; these typeshed stubs are now obsolete."
    NO_LONGER_UPDATED = (
        "Upstream has not added type hints,"
        " but these stubs are no longer updated for some other reason."
    )
    OUT_OF_DATE = (
        "These stubs are out of date. In CI, stubtest tests these stubs against an"
        " older version of this package than the latest that's available."
    )
    UP_TO_DATE = (
        "These stubs should be fairly up to date. In CI, stubtest tests these stubs"
        " against the latest version of the package that's available."
    )


async def _get_pypi_data(
    package_name: str, session: aiohttp.ClientSession | None
) -> dict[str, Any]:
    pypi_data_url = f"https://pypi.org/pypi/{urllib.parse.quote(package_name)}/json"
    async with AsyncExitStack() as stack:
        if session is None:
            # see https://github.com/python/mypy/issues/13936
            # for why we need the tmp_var to keep mypy happy
            tmp_var = await stack.enter_async_context(aiohttp.ClientSession())
            session = tmp_var
        async with session.get(pypi_data_url) as response:
            response.raise_for_status()
            response_json = await response.json()
    assert isinstance(response_json, dict)
    return response_json


async def get_package_status(
    package_name: str,
    *,
    typeshed_dir: Path | str,
    session: aiohttp.ClientSession | None = None,
) -> PackageStatus:
    """Retrieve information on how up to date a stubs package is.

    If stubtest tests these stubs against the latest version of the runtime
    in typeshed's CI, it's a fair bet that the stubs are relatively up to date.
    If stubtest tests these stubs against an older version, however,
    the stubs may be out of date.

    This function makes network requests to PyPI in order to determine what the
    latest version of the runtime is, and then compares this against
    the metadata of the stubs package.

    Args:
        package_name: The name of the stubs package to analyze.
        typeshed_dir: A path pointing to a typeshed directory
          in which to find the stubs package.
        session (optional): An `aiohttp.ClientSession` instance, to be used
          for making a network requests, or `None`. If `None` is provided
          for this argument, a new `aiohttp.ClientSession` instance will be
          created to make the network request.

    Returns:
        A member of the `PackageStatus` enumeration
        (see the docs on `PackageStatus` for details).
    """
    if package_name == "stdlib":
        # This function isn't really relevant for the stdlib stubs
        return PackageStatus.STDLIB

    if package_name == "gdb":
        return PackageStatus.NOT_ON_PYPI

    metadata = _get_package_metadata(package_name, typeshed_dir)

    if "obsolete_since" in metadata:
        return PackageStatus.OBSOLETE

    if metadata.get("no_longer_updated", False):
        return PackageStatus.NO_LONGER_UPDATED

    typeshed_pinned_version = SpecifierSet(f"=={metadata['version']}")
    pypi_data = await _get_pypi_data(package_name, session)
    pypi_version = Version(pypi_data["info"]["version"])
    status = "UP_TO_DATE" if pypi_version in typeshed_pinned_version else "OUT_OF_DATE"
    return PackageStatus[status]


def get_package_size(package_name: str, *, typeshed_dir: Path | str) -> int:
    """Get the total number of lines of code for a stubs package in typeshed.

    Args:
        package_name: The name of the stubs package to find the line number for.
        typeshed_dir: A path pointing to a typeshed directory
          in which to find the stubs package.

    Returns:
        The number of lines of code the stubs package contains.
    """
    return sum(
        len(stub.read_text(encoding="utf-8").splitlines())
        for stub in _get_package_directory(package_name, typeshed_dir).rglob("*.pyi")
    )


@cache
def _get_pyright_strict_excludelist(typeshed_dir: Path | str) -> frozenset[Path]:
    # Read pyrightconfig.stricter.json;
    # do some pre-processing so that it can be passed to json.loads()
    config_path = Path(typeshed_dir, "pyrightconfig.stricter.json")
    with config_path.open(encoding="utf-8") as file:
        # strip comments from the file
        lines = [line for line in file if not line.strip().startswith("//")]
    # strip trailing commas from the file
    valid_json = re.sub(r",(\s*?[\}\]])", r"\1", "\n".join(lines))
    pyright_config = json.loads(valid_json)
    assert isinstance(pyright_config, dict)
    excludelist = pyright_config.get("exclude", [])
    return frozenset(Path(typeshed_dir, item) for item in excludelist)


class PyrightSetting(_NiceReprEnum):
    """The various possible pyright settings typeshed uses in CI."""

    STRICT = "All files are tested with the stricter pyright settings in CI."
    NOT_STRICT = "All files are excluded from the stricter pyright settings in CI."
    STRICT_ON_SOME_FILES = (
        "Some files are tested with the stricter pyright settings in CI;"
        " some are excluded."
    )


def get_pyright_strictness(
    package_name: PackageName, *, typeshed_dir: Path | str
) -> PyrightSetting:
    """Get the setting typeshed uses in CI when pyright is run on a certain package.

    Args:
        package_name: The name of the package to find the stubtest setting for.
        typeshed_dir: A path pointing to a typeshed directory,
          from which to retrieve the stubtest setting.

    Returns:
        A member of the `PyrightSetting` enumeration
        (see the docs on `PyrightSetting` for details).
    """
    package_directory = _get_package_directory(package_name, typeshed_dir)
    excluded_paths = _get_pyright_strict_excludelist(typeshed_dir)
    if package_directory in excluded_paths:
        return PyrightSetting.NOT_STRICT
    if any(
        excluded_path in package_directory.parents for excluded_path in excluded_paths
    ):
        return PyrightSetting.NOT_STRICT
    if any(
        package_directory in excluded_path.parents for excluded_path in excluded_paths
    ):
        return PyrightSetting.STRICT_ON_SOME_FILES
    return PyrightSetting.STRICT


@final
@attrs.define
class PackageStats:
    """Statistics about a single stubs package in typeshed."""

    package_name: PackageName
    number_of_lines: int
    package_status: PackageStatus
    stubtest_setting: StubtestSetting
    pyright_setting: PyrightSetting
    annotation_stats: AnnotationStats


async def gather_stats_on_package(
    package_name: PackageName,
    *,
    typeshed_dir: Path | str,
    session: aiohttp.ClientSession | None = None,
) -> PackageStats:
    """Gather miscellaneous statistics about a single stubs package in typeshed.

    This function calls `get_package_status()`,
    which makes network requests to PyPI.
    See the docs on `get_package_status()` for details.

    Args:
        package_name: The name of the package to gather statistics on.
        typeshed_dir: A path pointing to a typeshed directory,
          in which the source code for the stubs package can be found.
        session (optional): An `aiohttp.ClientSession` instance, to be used
          for making a network requests, or `None`. If `None` is provided
          for this argument, a new `aiohttp.ClientSession` instance will be
          created to make the network request.

    Returns:
        An instance of the `PackageStats` class.
    """
    return PackageStats(
        package_name=package_name,
        number_of_lines=get_package_size(package_name, typeshed_dir=typeshed_dir),
        package_status=await get_package_status(
            package_name, typeshed_dir=typeshed_dir, session=session
        ),
        stubtest_setting=get_stubtest_setting(package_name, typeshed_dir=typeshed_dir),
        pyright_setting=get_pyright_strictness(package_name, typeshed_dir=typeshed_dir),
        annotation_stats=gather_annotation_stats_on_package(
            package_name, typeshed_dir=typeshed_dir
        ),
    )


async def _gather_stats(
    packages: Iterable[str], *, typeshed_dir: Path | str
) -> Sequence[PackageStats]:
    conn = aiohttp.TCPConnector(limit_per_host=10)
    async with aiohttp.ClientSession(connector=conn) as session:
        tasks = (
            gather_stats_on_package(
                package_name, typeshed_dir=typeshed_dir, session=session
            )
            for package_name in packages
        )
        return await asyncio.gather(*tasks, return_exceptions=True)


def gather_stats(
    packages: Iterable[str] | None = None, *, typeshed_dir: Path | str
) -> Sequence[PackageStats]:
    """Concurrently gather statistics on multiple packages.

    Note: this function calls `asyncio.run()` to start an asyncio event loop.
    It is therefore not suitable to be called from inside functions
    that are themselves called as part of an asyncio event loop.

    Args:
        packages: An iterable of package names to be analysed, or None.
          If `None`, defaults to all third-party stubs, plus the stubs for the stdlib.
        typeshed_dir: The path to a local clone of typeshed.

    Returns:
        A sequence of `PackageStats` objects. Each `PackageStats` object
        contains information representing an analysis of a certain stubs package
        in typeshed.
    """
    if packages is None:
        packages = os.listdir(Path(typeshed_dir, "stubs")) + ["stdlib"]
    results = asyncio.run(_gather_stats(packages, typeshed_dir=typeshed_dir))
    for result in results:
        if isinstance(result, BaseException):
            raise result
    return results


@contextmanager
def tmpdir_typeshed() -> Iterator[Path]:
    """Context manager to clone typeshed into a tempdir, and then yield the tempdir."""
    import subprocess
    from tempfile import TemporaryDirectory

    args = [
        "git",
        "clone",
        "https://github.com/python/typeshed",
        "--depth",
        "1",
        "--quiet",
    ]

    with TemporaryDirectory() as td:
        args.append(td)
        subprocess.run(args, check=True)
        yield Path(td)
