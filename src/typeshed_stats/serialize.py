"""Tools for serializing and deserializing [`PackageInfo`][typeshed_stats.gather.PackageInfo] objects."""

from collections.abc import Sequence
from functools import cache
from operator import attrgetter

import attrs
import cattrs

from typeshed_stats.gather import (
    AnnotationStats,
    PackageInfo,
    StubtestSetting,
    _NiceReprEnum,
)

__all__ = [
    "stats_from_csv",
    "stats_from_json",
    "stats_to_csv",
    "stats_to_json",
    "stats_to_markdown",
]

_CATTRS_CONVERTER = cattrs.Converter()
_unstructure = _CATTRS_CONVERTER.unstructure
_structure = _CATTRS_CONVERTER.structure

_CATTRS_CONVERTER.register_unstructure_hook(_NiceReprEnum, attrgetter("name"))
_CATTRS_CONVERTER.register_structure_hook(_NiceReprEnum, lambda d, t: t[d])  # type: ignore[index,no-any-return]


def stats_to_json(stats: Sequence[PackageInfo]) -> str:
    """Convert stats on multiple stubs packages to JSON format.

    Args:
        stats: The statistics to convert.

    Returns:
        The statistics serialized as JSON.
    """
    import json

    return json.dumps(_unstructure(stats), indent=2) + "\n"


def stats_from_json(data: str) -> list[PackageInfo]:
    """Load `PackageInfo` objects from JSON format.

    Args:
        data: A JSON string.

    Returns:
        The statistics deserialized into
            [`PackageInfo`][typeshed_stats.gather.PackageInfo] objects.
    """
    import json

    return _structure(json.loads(data), list[PackageInfo])


def stats_to_csv(stats: Sequence[PackageInfo]) -> str:
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


@cache
def _annotation_stats_fields() -> tuple[str, ...]:
    return tuple(f.name for f in attrs.fields(AnnotationStats))


def stats_from_csv(data: str) -> list[PackageInfo]:
    """Load `PackageInfo` objects from csv format.

    Args:
        data: A CSV string.

    Returns:
        The statistics deserialized into
            [`PackageInfo`][typeshed_stats.gather.PackageInfo] objects.
    """
    import csv
    import io

    csvfile = io.StringIO(data, newline="")
    stats = list(csv.DictReader(csvfile))
    annotation_stats_fields = _annotation_stats_fields()
    converted_stats = []
    for stat in stats:
        converted_stat, annotation_stats = {}, {}
        for key, val in stat.items():
            if key in annotation_stats_fields:
                annotation_stats[key] = val
            else:
                converted_stat[key] = val
        converted_stat["annotation_stats"] = annotation_stats
        stubtest_platforms = converted_stat["stubtest_platforms"]
        if stubtest_platforms == "None":
            converted_stat["stubtest_platforms"] = []
        else:
            converted_stat["stubtest_platforms"] = stubtest_platforms.split(";")
        if converted_stat["extra_description"] == "-":
            converted_stat["extra_description"] = None
        converted_stats.append(converted_stat)
    return _structure(converted_stats, list[PackageInfo])


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
        ## Info on typeshed's stubs for `{package_name}`
        {extra_description_section}
        ### Number of lines

        {number_of_lines:,} (excluding blank lines)

        ### Package status: *{package_status.formatted_name}*

        {package_status.value}

        ### Upload status: *{upload_status.formatted_name}*

        {upload_status.value}

        ### Stubtest settings in CI: *{stubtest_setting.formatted_name}*

        {stubtest_setting.value}
        {stubtest_platforms_section}
        ### Pyright settings in CI: *{pyright_setting.formatted_name}*

        {pyright_setting.value}

        ### Statistics on the annotations in typeshed's stubs for `{package_name}`

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
        package_as_dict = attrs.asdict(package_stats)
        kwargs = package_as_dict | package_as_dict["annotation_stats"]
        del kwargs["annotation_stats"]

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

        if package_stats.stubtest_setting is not StubtestSetting.SKIPPED:
            platforms = package_stats.stubtest_platforms
            num_platforms = len(platforms)
            if num_platforms == 1:
                desc = f"In CI, stubtest is run on {platforms[0]} only."
            elif num_platforms == 2:
                desc = f"In CI, stubtest is run on {platforms[0]} and {platforms[1]}."
            else:
                assert num_platforms == 3
                desc = (
                    "In CI, stubtest is run on "
                    f"{platforms[0]}, {platforms[1]} and {platforms[2]}."
                )
            kwargs["stubtest_platforms_section"] = textwrap.dedent(
                f"""
                ### Stubtest platforms in CI

                {desc}
                """
            )
        else:
            kwargs["stubtest_platforms_section"] = ""
        del kwargs["stubtest_platforms"]

        return template.format(**kwargs)

    return "\n<hr>\n".join(format_package(info) for info in stats).strip() + "\n"
