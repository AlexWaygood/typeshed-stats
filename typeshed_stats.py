from __future__ import annotations

import ast
import asyncio
import os
import sys
import urllib.parse
from collections.abc import Mapping
from dataclasses import dataclass, fields
from enum import Enum, auto
from functools import cache, cached_property
from pathlib import Path
from typing import Any, NamedTuple, TypeVar
from typing_extensions import Annotated, TypeAlias

import aiohttp
import tomli
from packaging.specifiers import SpecifierSet
from packaging.version import Version

ExitCode: TypeAlias = int
PackageName: TypeAlias = str
PackageCompleteness: TypeAlias = Annotated[
    bool, "Whether or not a package uses stubtest's --ignore-missing-stub option in CI"
]


def is_Any(annotation: ast.expr) -> bool:
    match annotation:
        case ast.Name("Any"):
            return True
        case ast.Attribute(value=ast.Name("typing"), attr="Any"):
            return True
        case _:
            return False


def is_Incomplete(annotation: ast.expr) -> bool:
    match annotation:
        case ast.Name("Incomplete"):
            return True
        case ast.Attribute(value=ast.Name("_typeshed"), attr="Incomplete"):
            return True
        case _:
            return False


AnnotationStatsSelf = TypeVar("AnnotationStatsSelf", bound="PackageAnnotationStats")


@dataclass
class PackageAnnotationStats(ast.NodeVisitor):
    """Statistics on the annotations for a source file or a directory of source files"""

    annotated_parameters: int = 0
    unannotated_parameters: int = 0
    annotated_returns: int = 0
    unannotated_returns: int = 0
    explicit_Incomplete_parameters: int = 0
    explicit_Incomplete_returns: int = 0
    explicit_Any_parameters: int = 0
    explicit_Any_returns: int = 0

    def visit_arg(self, node: ast.arg) -> None:
        annotation = node.annotation
        if annotation is None:
            self.unannotated_parameters += 1
        else:
            self.annotated_parameters += 1
            if is_Any(annotation):
                self.explicit_Any_parameters += 1
            elif is_Incomplete(annotation):
                self.explicit_Incomplete_parameters += 1
        self.generic_visit(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        returns = node.returns
        if returns is None:
            self.unannotated_returns += 1
        else:
            self.annotated_returns += 1
            if is_Any(returns):
                self.explicit_Any_returns += 1
            elif is_Incomplete(returns):
                self.explicit_Incomplete_returns += 1

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)
        self.generic_visit(node)

    def gather_stats_on_file(
        self: AnnotationStatsSelf, source: str
    ) -> AnnotationStatsSelf:
        self.visit(ast.parse(source))
        return self

    @property
    def field_names(self) -> tuple[str, ...]:
        return tuple(field.name for field in fields(type(self)))

    def __add__(self, other: PackageAnnotationStats) -> PackageAnnotationStats:
        if not isinstance(other, PackageAnnotationStats):
            return NotImplemented  # type: ignore[unreachable]
        result = PackageAnnotationStats()
        for field in self.field_names:
            setattr(result, field, getattr(self, field) + getattr(other, field))
        return result

    __radd__ = __add__


def gather_annotation_stats_on_package(
    package_directory: Path,
) -> PackageAnnotationStats:
    return sum(
        [
            PackageAnnotationStats().gather_stats_on_file(path.read_text())
            for path in package_directory.rglob("*.pyi")
        ],
        start=PackageAnnotationStats(),
    )


@cache
def get_package_metadata(package_directory: Path) -> Mapping[str, Any]:
    with open(package_directory / "METADATA.toml", "rb") as f:
        return tomli.load(f)


def get_package_completeness(
    package_name: str, package_directory: Path
) -> PackageCompleteness:
    if package_name == "stdlib":
        return True
    metadata = get_package_metadata(package_directory)
    ignore_missing_stub_used = (
        metadata.get("tool", {}).get("stubtest", {}).get("ignore_missing_stub", True)
    )
    return not ignore_missing_stub_used


class PackageStatus(Enum):
    STDLIB = auto()
    OBSOLETE = auto()
    NO_LONGER_UPDATED = auto()
    OUT_OF_DATE = auto()
    UP_TO_DATE = auto()

    def __repr__(self) -> str:
        return f"PackageStatus.{self.name}"


async def get_package_status(
    package_name: str, package_directory: Path, *, session: aiohttp.ClientSession
) -> PackageStatus:
    if package_name == "stdlib":
        # This function isn't really relevant for the stdlib stubs
        return PackageStatus.STDLIB

    metadata = get_package_metadata(package_directory)

    if "obsolete_since" in metadata:
        return PackageStatus.OBSOLETE

    if metadata.get("no_longer_updated", False):
        return PackageStatus.NO_LONGER_UPDATED

    typeshed_pinned_version = SpecifierSet(f"=={metadata['version']}")
    pypi_root = f"https://pypi.org/pypi/{urllib.parse.quote(package_name)}"
    async with session.get(f"{pypi_root}/json") as response:
        response.raise_for_status()
        pypi_data = await response.json()
    pypi_version = Version(pypi_data["info"]["version"])
    return PackageStatus[
        "UP_TO_DATE" if pypi_version in typeshed_pinned_version else "OUT_OF_DATE"
    ]


def get_package_line_number(package_directory: Path) -> int:
    return sum(
        len(stub.read_text().splitlines()) for stub in package_directory.rglob("*.pyi")
    )


@dataclass
class PackageStats:
    number_of_lines: int
    package_status: PackageStatus
    package_is_complete: PackageCompleteness
    annotation_stats: PackageAnnotationStats


class PackageData(NamedTuple):
    name: PackageName
    stats: PackageStats


async def gather_stats_for_package(
    package_name: PackageName, *, typeshed_dir: Path, session: aiohttp.ClientSession
) -> PackageData:
    if package_name == "stdlib":
        package_directory = typeshed_dir / "stdlib"
    else:
        package_directory = typeshed_dir / "stubs" / package_name
    stats = PackageStats(
        number_of_lines=get_package_line_number(package_directory),
        package_status=await get_package_status(
            package_name, package_directory, session=session
        ),
        package_is_complete=get_package_completeness(package_name, package_directory),
        annotation_stats=gather_annotation_stats_on_package(package_directory),
    )
    return PackageData(name=package_name, stats=stats)


async def gather_stats(
    packages: list[str], *, typeshed_dir: Path
) -> dict[PackageName, PackageStats]:
    conn = aiohttp.TCPConnector(limit_per_host=10)
    async with aiohttp.ClientSession(connector=conn) as session:
        tasks = (
            gather_stats_for_package(
                package_name, typeshed_dir=typeshed_dir, session=session
            )
            for package_name in packages
        )
        return dict(await asyncio.gather(*tasks))


class Options(NamedTuple):
    packages: list[str]
    typeshed_dir: Path
    print_output: bool


def get_options() -> Options:
    import argparse

    parser = argparse.ArgumentParser(description="Script to gather stats on typeshed")
    parser.add_argument(
        "packages",
        type=str,
        nargs="*",
        action="extend",
        help=(
            "Packages to gather stats on (defaults to all third-party packages, plus"
            " the stdlib)"
        ),
    )
    parser.add_argument(
        "-t",
        "--typeshed-dir",
        type=Path,
        required=True,
        help="Path to the typeshed directory",
    )
    parser.add_argument(
        "--print-output",
        action="store_true",
        help="Pretty-print ouptut straight to the terminal",
    )
    args = parser.parse_args()
    typeshed_dir = args.typeshed_dir
    packages = args.packages or os.listdir(typeshed_dir) + ["stdlib"]
    stdlib = typeshed_dir / "stdlib"
    if not (
        typeshed_dir.exists()
        and typeshed_dir.is_dir()
        and stdlib.exists()
        and stdlib.is_dir()
    ):
        raise TypeError(f'"{typeshed_dir}" is not a valid typeshed directory')
    return Options(packages, typeshed_dir, args.print_output)


async def main() -> None:
    packages, typeshed_dir, print_output = get_options()
    stats = await gather_stats(packages, typeshed_dir=typeshed_dir)
    if print_output:
        from pprint import pprint

        pprint(stats)


if __name__ == "__main__":
    assert sys.version_info >= (3, 10), "Python 3.10+ is required to run this script."
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Interrupted!")
        code = 1
    else:
        code = 0
    raise SystemExit(code)
