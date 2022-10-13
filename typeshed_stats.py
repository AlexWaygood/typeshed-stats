from __future__ import annotations

import ast
import asyncio
import dataclasses
import json
import os
import re
import sys
import urllib.parse
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from functools import cache
from pathlib import Path
from typing import Any, NamedTuple, get_type_hints
from typing_extensions import Literal, TypeAlias

import aiohttp
import tomli
from packaging.specifiers import SpecifierSet
from packaging.version import Version

assert sys.version_info >= (3, 10), "Python 3.10+ is required."


__all__ = ["main", "gather_stats", "format_stats", "OutputOption"]


ExitCode: TypeAlias = int
PackageName: TypeAlias = str


class NiceReprEnum(Enum):
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}.{self.name}"

    @property
    def __doc__(self) -> str:  # type: ignore[override]
        return self.value  # type: ignore[no-any-return]

    @property
    def formatted_name(self) -> str:
        return " ".join(self.name.split("_")).lower()


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


@dataclass
class AnnotationStats(ast.NodeVisitor):
    """Statistics on the annotations for a source file or a directory of source files"""

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

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.annotated_variables += 1
        if is_Any(node.annotation):
            self.explicit_Any_variables += 1
        elif is_Incomplete(node.annotation):
            self.explicit_Incomplete_variables += 1
        self.generic_visit(node)

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

    @staticmethod
    def gather_stats_on_file(path: Path) -> AnnotationStats:
        visitor = AnnotationStats()
        visitor.visit(ast.parse(path.read_text(encoding="utf-8")))
        return visitor


def gather_annotation_stats_on_package(package_directory: Path) -> AnnotationStats:
    file_results = [
        AnnotationStats.gather_stats_on_file(path)
        for path in package_directory.rglob("*.pyi")
    ]
    # Sum all the statistics together, to get the statistics for the package as a whole
    package_stats: Counter[str] = sum(
        [Counter(dataclasses.asdict(result)) for result in file_results],
        start=Counter(),
    )
    return AnnotationStats(**package_stats)


@cache
def get_package_metadata(package_directory: Path) -> Mapping[str, Any]:
    with open(package_directory / "METADATA.toml", "rb") as f:
        return tomli.load(f)


class StubtestSetting(NiceReprEnum):
    SKIPPED = "Stubtest is skipped in CI for this package."
    MISSING_STUBS_IGNORED = (
        "The `--ignore-missing-stub` stubtest setting is used in CI."
    )
    ERROR_ON_MISSING_STUB = (
        "Objects missing from the stub cause stubtest to emit an error in CI."
    )


def get_stubtest_setting(package_name: str, package_directory: Path) -> StubtestSetting:
    if package_name == "stdlib":
        return StubtestSetting.ERROR_ON_MISSING_STUB
    metadata = get_package_metadata(package_directory)
    stubtest_settings = metadata.get("tool", {}).get("stubtest", {})
    if stubtest_settings.get("skip", False):
        return StubtestSetting.SKIPPED
    ignore_missing_stub_used = stubtest_settings.get("ignore_missing_stub", True)
    return StubtestSetting[
        "MISSING_STUBS_IGNORED" if ignore_missing_stub_used else "ERROR_ON_MISSING_STUB"
    ]


class PackageStatus(NiceReprEnum):
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


async def get_package_status(
    package_name: str, package_directory: Path, *, session: aiohttp.ClientSession
) -> PackageStatus:
    if package_name == "stdlib":
        # This function isn't really relevant for the stdlib stubs
        return PackageStatus.STDLIB

    if package_name == "gdb":
        return PackageStatus.NOT_ON_PYPI

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
        len(stub.read_text(encoding="utf-8").splitlines())
        for stub in package_directory.rglob("*.pyi")
    )


@cache
def get_pyright_strict_excludelist(typeshed_dir: Path) -> frozenset[Path]:
    # Read pyrightconfig.stricter.json;
    # do some pre-processing so that it can be passed to json.loads()
    with open(typeshed_dir / "pyrightconfig.stricter.json", encoding="utf-8") as file:
        # strip comments from the file
        lines = [line for line in file if not line.strip().startswith("//")]
    # strip trailing commas from the file
    valid_json = re.sub(r",(\s*?[\}\]])", r"\1", "\n".join(lines))
    pyright_config = json.loads(valid_json)
    assert isinstance(pyright_config, dict)
    excludelist = pyright_config.get("exclude", [])
    return frozenset(typeshed_dir / item for item in excludelist)


class PyrightSetting(NiceReprEnum):
    STRICT = "All files are tested with the stricter pyright settings in CI."
    NOT_STRICT = "All files are excluded from the stricter pyright settings in CI."
    STRICT_ON_SOME_FILES = (
        "Some files are tested with the stricter pyright settings in CI;"
        " some are excluded."
    )


def get_pyright_strictness(
    package_directory: Path, *, typeshed_dir: Path
) -> PyrightSetting:
    excluded_paths = get_pyright_strict_excludelist(typeshed_dir)
    if package_directory in excluded_paths:
        return PyrightSetting.NOT_STRICT
    if any(
        package_directory in excluded_path.parents for excluded_path in excluded_paths
    ):
        return PyrightSetting.STRICT_ON_SOME_FILES
    return PyrightSetting.STRICT


@dataclass
class PackageStats:
    package_name: PackageName
    number_of_lines: int
    package_status: PackageStatus
    stubtest_setting: StubtestSetting
    pyright_setting: PyrightSetting
    annotation_stats: AnnotationStats


async def gather_stats_for_package(
    package_name: PackageName, *, typeshed_dir: Path, session: aiohttp.ClientSession
) -> PackageStats:
    if package_name == "stdlib":
        package_directory = typeshed_dir / "stdlib"
    else:
        package_directory = typeshed_dir / "stubs" / package_name
    return PackageStats(
        package_name=package_name,
        number_of_lines=get_package_line_number(package_directory),
        package_status=await get_package_status(
            package_name, package_directory, session=session
        ),
        stubtest_setting=get_stubtest_setting(package_name, package_directory),
        pyright_setting=get_pyright_strictness(
            package_directory, typeshed_dir=typeshed_dir
        ),
        annotation_stats=gather_annotation_stats_on_package(package_directory),
    )


async def _gather_stats(
    packages: list[str], *, typeshed_dir: Path
) -> Sequence[PackageStats]:
    conn = aiohttp.TCPConnector(limit_per_host=10)
    async with aiohttp.ClientSession(connector=conn) as session:
        tasks = (
            gather_stats_for_package(
                package_name, typeshed_dir=typeshed_dir, session=session
            )
            for package_name in packages
        )
        return await asyncio.gather(*tasks)


def gather_stats(packages: list[str], *, typeshed_dir: Path) -> Sequence[PackageStats]:
    return asyncio.run(_gather_stats(packages, typeshed_dir=typeshed_dir))


class Options(NamedTuple):
    packages: list[str]
    typeshed_dir: Path
    output_option: OutputOption
    writefile: Path | None


def get_options() -> Options:
    import argparse

    parser = argparse.ArgumentParser(description="Script to gather stats on typeshed")
    parser.add_argument(
        "packages",
        type=str,
        nargs="*",
        action="extend",
        help=(
            "Packages to gather stats on"
            " (defaults to all third-party packages, plus the stdlib)"
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
        "-o",
        "--overwrite",
        action="store_true",
        help=(
            "Overwrite the path passed to `--file` if it already exists"
            " (defaults to False)"
        ),
    )

    output_options = parser.add_mutually_exclusive_group()
    output_options.add_argument(
        "--pprint",
        action="store_true",
        help="Pretty-print Python representations of the data (default output)",
    )
    output_options.add_argument(
        "--to-json", action="store_true", help="Print output as JSON"
    )
    output_options.add_argument(
        "--to-csv", action="store_true", help="Print output in csv format"
    )
    output_options.add_argument(
        "--to-markdown", action="store_true", help="Print output as formatted MarkDown"
    )
    output_options.add_argument(
        "-f",
        "--to-file",
        type=Path,
        help=(
            f"File to write output to. Extension must be one of {SUPPORTED_EXTENSIONS}"
        ),
    )

    args = parser.parse_args()
    writefile: Path | None = args.to_file

    if writefile:
        suffix = writefile.suffix
        try:
            output_option = next(
                option
                for option in OutputOption
                if option.required_file_extension == suffix
            )
        except StopIteration:
            raise TypeError(
                f"Unrecognised file extension {suffix!r} passed to --file"
                f" (choose from {SUPPORTED_EXTENSIONS})"
            ) from None
        if writefile.exists() and not args.overwrite:
            raise TypeError(f'"{writefile}" already exists!')
    elif args.to_json:
        output_option = OutputOption.JSON
    elif args.to_csv:
        output_option = OutputOption.CSV
    elif args.to_markdown:
        output_option = OutputOption.MARKDOWN
    else:
        # --pprint is the default if no option in this group was specified
        output_option = OutputOption.PPRINT

    typeshed_dir = args.typeshed_dir
    stubs_dir = typeshed_dir / "stubs"
    for folder in typeshed_dir, (typeshed_dir / "stdlib"), stubs_dir:
        if not folder.exists() and folder.is_dir():
            raise TypeError(f'"{typeshed_dir}" is not a valid typeshed directory')

    packages = args.packages or os.listdir(stubs_dir) + ["stdlib"]

    return Options(packages, typeshed_dir, output_option, writefile)


def jsonify_stats(stats: Sequence[PackageStats]) -> str:
    class EnumAwareEncoder(json.JSONEncoder):
        def default(self, obj: object) -> Any:
            return obj.name if isinstance(obj, NiceReprEnum) else super().default(obj)

    dictified_stats = {info.package_name: dataclasses.asdict(info) for info in stats}
    return json.dumps(dictified_stats, indent=2, cls=EnumAwareEncoder)


def csvify_stats(stats: Sequence[PackageStats]) -> str:
    import csv
    import io

    # First, dictify
    converted_stats = [dataclasses.asdict(info) for info in stats]

    # Then, flatten the data, and stringify the enums
    enum_fields = [
        key
        for key, val in get_type_hints(PackageStats).items()
        if issubclass(val, Enum)
    ]
    for info in converted_stats:
        info |= info["annotation_stats"]
        del info["annotation_stats"]
        for field in enum_fields:
            info[field] = info[field].name

    # Now, write to csv
    fieldnames = converted_stats[0].keys()
    csvfile = io.StringIO(newline="")
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()
    for info in converted_stats:
        writer.writerow(info)
    return csvfile.getvalue()


def markdownify_stats(stats: Sequence[PackageStats]) -> str:
    import textwrap

    def format_enum_member(enum_member: Enum) -> str:
        return " ".join(enum_member.name.split("_")).lower()

    template = textwrap.dedent(
        """
        ## Stats on typeshed's stubs for {package_name}

        ### Number of lines
        {number_of_lines}

        ### Package status: {package_status.formatted_name}
        {package_status.value}

        ### Stubtest settings in CI: {stubtest_setting.formatted_name}
        {stubtest_setting.value}

        ### Pyright settings in CI: {pyright_setting.formatted_name}
        {pyright_setting.value}

        ### Statistics on the annotations in typeshed's stubs for {package_name}
        {annotation_stats}
        """
    )

    def format_annotation_stats(annotation_stats: dict[str, int]) -> str:
        def format_key(key: str) -> str:
            return " ".join(key.split("_")).capitalize()

        return "- " + "\n- ".join(
            f"{format_key(key)}: {val}" for key, val in annotation_stats.items()
        )

    def format_package(package_stats: PackageStats) -> str:
        package_as_dict = dataclasses.asdict(package_stats)
        package_as_dict["annotation_stats"] = format_annotation_stats(
            package_as_dict["annotation_stats"]
        )
        return template.format(**package_as_dict)

    markdown_page = "# Stats on typeshed's stubs for various packages\n<br>\n"
    markdown_page += "\n<br>\n".join(format_package(info) for info in stats)
    return markdown_page


def format_stats_for_pprinting(stats: Sequence[PackageStats]) -> str:
    return str({info_bundle.package_name: info_bundle for info_bundle in stats})


class OutputOption(Enum):
    PPRINT = ".txt", format_stats_for_pprinting
    JSON = ".json", jsonify_stats
    CSV = ".csv", csvify_stats
    MARKDOWN = ".md", markdownify_stats

    @property
    def required_file_extension(self) -> str:
        return self.value[0]

    def convert(self, stats: Sequence[PackageStats]) -> str:
        converter_function = self.value[1]
        return converter_function(stats)


SUPPORTED_EXTENSIONS = [option.required_file_extension for option in OutputOption]


def format_stats(
    stats: Sequence[PackageStats],
    output_option: OutputOption | Literal["PPRINT", "JSON", "CSV", "MARKDOWN"],
) -> str:
    if not isinstance(output_option, OutputOption):
        output_option = OutputOption[output_option]
    return output_option.convert(stats)


def write_stats(formatted_stats: str, writefile: Path | None) -> None:
    if writefile is None:
        try:
            import rich

            pprint = rich.print
        except ImportError:
            from pprint import pprint  # type: ignore[no-redef]

        pprint(formatted_stats)
    else:
        newline = "" if writefile.suffix == ".csv" else "\n"
        with writefile.open("w", newline=newline) as f:
            f.write(formatted_stats)
        print(f'Output successfully written to "{writefile}"!')


def main() -> None:
    packages, typeshed_dir, output_option, writefile = get_options()
    print("Gathering stats...")
    stats = gather_stats(packages, typeshed_dir=typeshed_dir)
    print("Formatting stats...")
    formatted_stats = format_stats(stats, output_option)
    write_stats(formatted_stats, writefile)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted!")
        code = 1
    else:
        code = 0
    raise SystemExit(code)
