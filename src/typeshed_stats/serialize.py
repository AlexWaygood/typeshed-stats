"""Tools for serializing and deserializing [`PackageInfo`][typeshed_stats.gather.PackageInfo] and [`FileInfo`][typeshed_stats.gather.FileInfo] objects."""

from collections.abc import Sequence
from operator import attrgetter
from pathlib import Path
from typing import overload

import attrs
import cattrs

from typeshed_stats.gather import (
    AnnotationStats,
    FileInfo,
    PackageInfo,
    StubtestSettings,
    StubtestStrictness,
    _NiceReprEnum,
)

__all__ = [
    "file_stats_from_csv",
    "file_stats_from_json",
    "package_stats_from_csv",
    "package_stats_from_json",
    "stats_to_csv",
    "stats_to_json",
    "stats_to_markdown",
]

_CATTRS_CONVERTER = cattrs.Converter()
_unstructure = _CATTRS_CONVERTER.unstructure
_structure = _CATTRS_CONVERTER.structure

_CATTRS_CONVERTER.register_unstructure_hook(_NiceReprEnum, attrgetter("name"))
_CATTRS_CONVERTER.register_unstructure_hook(Path, Path.as_posix)
_CATTRS_CONVERTER.register_structure_hook(_NiceReprEnum, lambda d, t: t[d])  # type: ignore[index,no-any-return]
_CATTRS_CONVERTER.register_structure_hook(
    Path, lambda d, t: Path(d)
)  # pragma: no branch


def stats_to_json(stats: Sequence[PackageInfo | FileInfo]) -> str:
    """Convert stats on multiple stubs packages to JSON format.

    Args:
        stats: The statistics to convert.

    Returns:
        The statistics serialized as JSON.
    """
    import json

    return json.dumps(_unstructure(stats), indent=2) + "\n"


def package_stats_from_json(data: str) -> list[PackageInfo]:
    """Load [`PackageInfo`][typeshed_stats.gather.PackageInfo] objects from JSON format.

    Args:
        data: A JSON string.

    Returns:
        The statistics deserialized into
            [`PackageInfo`][typeshed_stats.gather.PackageInfo] objects.
    """
    import json

    return _structure(json.loads(data), list[PackageInfo])


def file_stats_from_json(data: str) -> list[FileInfo]:
    """Load [`FileInfo`][typeshed_stats.gather.FileInfo] objects from JSON format.

    Args:
        data: A JSON string.

    Returns:
        The statistics deserialized into
            [`FileInfo`][typeshed_stats.gather.FileInfo] objects.
    """
    import json

    return _structure(json.loads(data), list[FileInfo])


def stats_to_csv(stats: Sequence[PackageInfo | FileInfo]) -> str:
    """Convert stats on multiple stubs packages to csv format.

    Args:
        stats: The statistics to convert.

    Returns:
        The statistics serialized as a CSV string.
    """
    import csv
    import io

    converted_stats = _unstructure(stats)
    for info in converted_stats:
        info |= info["annotation_stats"]
        del info["annotation_stats"]

        # This section is specific to PackageInfo objects
        if "stubtest_settings" in info:
            info |= {
                f"stubtest_{key}": val for key, val in info["stubtest_settings"].items()
            }
            del info["stubtest_settings"]
            stubtest_platforms = info["stubtest_platforms"]
            if not stubtest_platforms:
                info["stubtest_platforms"] = "None"
            else:
                info["stubtest_platforms"] = ";".join(stubtest_platforms)
            if info["extra_description"] is None:
                info["extra_description"] = "-"

    fieldnames = converted_stats[0].keys()
    csvfile = io.StringIO(newline="")
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()
    for info in converted_stats:
        writer.writerow(info)
    return csvfile.getvalue()


@overload
def _stats_from_csv(data: str, cls: type[PackageInfo]) -> list[PackageInfo]:
    ...


@overload
def _stats_from_csv(data: str, cls: type[FileInfo]) -> list[FileInfo]:
    ...


def _stats_from_csv(
    data: str, cls: type[PackageInfo | FileInfo]
) -> list[PackageInfo] | list[FileInfo]:
    import csv
    import io

    csvfile = io.StringIO(data, newline="")
    stats = list(csv.DictReader(csvfile))
    converted_stats = []
    for stat in stats:
        converted_stat, annotation_stats, stubtest_settings = {}, {}, {}
        for key, val in stat.items():
            if key in AnnotationStats.__annotations__:
                annotation_stats[key] = val
            elif key.removeprefix("stubtest_") in StubtestSettings.__annotations__:
                stubtest_settings[key.removeprefix("stubtest_")] = val
            else:
                converted_stat[key] = val
        converted_stat["annotation_stats"] = annotation_stats
        converted_stat["stubtest_settings"] = stubtest_settings
        if cls is PackageInfo:
            stubtest_platforms = stubtest_settings["platforms"]
            if stubtest_platforms == "None":
                stubtest_settings["platforms"] = []
            else:
                stubtest_settings["platforms"] = stubtest_platforms.split(";")
            if converted_stat["extra_description"] == "-":
                converted_stat["extra_description"] = None
        converted_stats.append(converted_stat)
    return _structure(converted_stats, list[cls])  # type: ignore[valid-type]


def package_stats_from_csv(data: str) -> list[PackageInfo]:
    """Load [`PackageInfo`][typeshed_stats.gather.PackageInfo] objects from csv format.

    Args:
        data: A CSV string.

    Returns:
        The statistics deserialized into
            [`PackageInfo`][typeshed_stats.gather.PackageInfo] objects.
    """
    return _stats_from_csv(data, cls=PackageInfo)


def file_stats_from_csv(data: str) -> list[FileInfo]:
    """Load [`FileInfo`][typeshed_stats.gather.FileInfo] objects from csv format.

    Args:
        data: A CSV string.

    Returns:
        The statistics deserialized into
            [`FileInfo`][typeshed_stats.gather.FileInfo] objects.
    """
    return _stats_from_csv(data, cls=FileInfo)


def stats_to_markdown(stats: Sequence[PackageInfo]) -> str:
    """Generate MarkDown describing statistics on multiple stubs packages.

    Args:
        stats: The statistics to convert.

    Returns:
        A markdown page describing the statistics.
    """
    import textwrap

    template = textwrap.dedent(
        """
        ## Info on typeshed's stubs for {package_name}
        {extra_description_section}{stub_distribution_name_section}
        ### Number of lines

        {number_of_lines:,} (excluding blank lines)

        ### Package status: *{package_status.formatted_name}*

        {package_status.value}

        ### Upload status: *{upload_status.formatted_name}*

        {upload_status.value}

        ### Stubtest settings in CI: *{stubtest_strictness.formatted_name}*

        {stubtest_strictness.value}{stubtest_platforms_section}

        {stubtest_allowlist_section}

        ### Pyright settings in CI: *{pyright_setting.formatted_name}*

        {pyright_setting.value}

        ### Statistics on the annotations in typeshed's stubs for {package_name}

        - Parameters (excluding `self`, `cls`, `metacls` and `mcls`):
            - Annotated parameters: {annotated_parameters:,}
            - Unannotated parameters: {unannotated_parameters:,}
            - Explicit `Any` parameters: {explicit_Any_parameters:,}
            - Explicitly `Incomplete` (or partially `Incomplete`) parameters: {explicit_Incomplete_parameters:,}
        - Returns:
            - Annotated returns: {annotated_returns:,}
            - Unannotated returns: {unannotated_returns:,}
            - Explicit `Any` returns: {explicit_Any_returns:,}
            - Explicitly `Incomplete` (or partially `Incomplete`) returns: {explicit_Incomplete_returns:,}
        - Variables:
            - Annotated variables: {annotated_variables:,}
            - Explicit `Any` variables: {explicit_Any_variables:,}
            - Explicitly `Incomplete` (or partially `Incomplete`) variables: {explicit_Incomplete_variables:,}
        """
    )

    def format_package(package_stats: PackageInfo) -> str:
        kwargs = attrs.asdict(package_stats)
        kwargs |= kwargs["annotation_stats"]
        kwargs |= {
            f"stubtest_{key}": val for key, val in kwargs["stubtest_settings"].items()
        }
        del kwargs["annotation_stats"]
        del kwargs["stubtest_settings"]

        if package_stats.package_name == "stdlib":
            kwargs["package_name"] = "the stdlib"
        else:
            kwargs["package_name"] = f"`{package_stats.package_name}`"

        if package_stats.stub_distribution_name == "-":
            kwargs["stub_distribution_name_section"] = ""
        else:
            kwargs["stub_distribution_name_section"] = textwrap.dedent(
                f"""
                ### Stub distribution name

                `{package_stats.stub_distribution_name}`
                """
            )
        del kwargs["stub_distribution_name"]

        if package_stats.extra_description:
            kwargs["extra_description_section"] = textwrap.dedent(
                f"""
                ### Extra description

                {package_stats.extra_description}
                """
            )
        else:
            kwargs["extra_description_section"] = ""
        del kwargs["extra_description"]

        stubtest_settings = package_stats.stubtest_settings
        if stubtest_settings.strictness is not StubtestStrictness.SKIPPED:
            platforms = stubtest_settings.platforms
            num_platforms = len(platforms)
            if num_platforms == 1:
                desc = f"In CI, stubtest is run on `{platforms[0]}` only."
            elif num_platforms == 2:
                desc = (
                    f"In CI, stubtest is run on `{platforms[0]}` and `{platforms[1]}`."
                )
            else:
                assert num_platforms == 3
                desc = (
                    "In CI, stubtest is run on "
                    f"`{platforms[0]}`, `{platforms[1]}` and `{platforms[2]}`."
                )
            kwargs["stubtest_platforms_section"] = f"\n\n{desc}"
        else:
            kwargs["stubtest_platforms_section"] = ""
        del kwargs["stubtest_platforms"]

        allowlist_length = kwargs["stubtest_allowlist_length"]
        kwargs["stubtest_allowlist_section"] = (
            f"Typeshed currently has {allowlist_length} allowlist "
            f"{'entry' if allowlist_length == 1 else 'entries'} "
            f"for {kwargs['package_name']} when running stubtest in CI."
        )
        del kwargs["stubtest_allowlist_length"]

        return template.format(**kwargs)

    return "\n<hr>\n".join(format_package(info) for info in stats).strip() + "\n"
