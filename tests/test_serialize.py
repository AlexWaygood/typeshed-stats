import copy
import csv
import io
import json
from collections.abc import Sequence

import markdown
import pytest
from bs4 import BeautifulSoup

from typeshed_stats.gather import (
    AnnotationStats,
    CompletenessLevel,
    FileInfo,
    PackageInfo,
    PackageStatus,
    PyrightSetting,
    StubtestSettings,
    StubtestStrictness,
    UploadStatus,
)
from typeshed_stats.serialize import (
    file_stats_from_csv,
    file_stats_from_json,
    package_stats_from_csv,
    package_stats_from_json,
    stats_to_csv,
    stats_to_json,
    stats_to_markdown,
)


def test_PackageInfo_conversion_to_and_from_json(
    random_PackageInfo_sequence: Sequence[PackageInfo],
) -> None:
    converted = stats_to_json(random_PackageInfo_sequence)
    assert converted[-1] == "\n"
    assert converted[-2] != "\n"
    assert isinstance(converted, str)
    lst = json.loads(converted)
    assert isinstance(lst, list)
    assert all(isinstance(item, dict) and "package_name" in item for item in lst)
    new_package_stats = package_stats_from_json(converted)
    assert new_package_stats == random_PackageInfo_sequence


def test_FileInfo_conversion_to_and_from_json(
    random_FileInfo_sequence: Sequence[FileInfo],
) -> None:
    converted = stats_to_json(random_FileInfo_sequence)
    assert converted[-1] == "\n"
    assert converted[-2] != "\n"
    assert isinstance(converted, str)
    lst = json.loads(converted)
    assert isinstance(lst, list)
    assert all(isinstance(item, dict) and "parent_package" in item for item in lst)
    new_package_stats = file_stats_from_json(converted)
    assert new_package_stats == random_FileInfo_sequence


@pytest.fixture
def unusual_packages() -> list[PackageInfo]:
    pkg1 = PackageInfo(
        "foo",
        stub_distribution_name="types-foo-ts",
        extra_description="a very fooey package",
        completeness_level=CompletenessLevel.PARTIAL,
        number_of_lines=100_000_000_000,
        package_status=PackageStatus.UP_TO_DATE,
        upload_status=UploadStatus.NOT_CURRENTLY_UPLOADED,
        stubtest_settings=StubtestSettings(
            strictness=StubtestStrictness.SKIPPED, platforms=[], allowlist_length=0
        ),
        pyright_setting=PyrightSetting.STRICT,
        annotation_stats=AnnotationStats(),
    )
    pkg2 = copy.deepcopy(pkg1)
    pkg2.package_name = "stdlib"
    pkg2.stubtest_settings.strictness = StubtestStrictness.ERROR_ON_MISSING_STUB
    pkg2.stubtest_settings.platforms = ["win32", "darwin"]
    pkg2.stub_distribution_name = "-"
    pkg3 = copy.deepcopy(pkg2)
    pkg3.stubtest_settings.platforms = ["win32", "darwin", "linux"]
    return [pkg1, pkg2, pkg3]


def test_PackageInfo_conversion_to_and_from_csv(
    random_PackageInfo_sequence: Sequence[PackageInfo],
    unusual_packages: list[PackageInfo],
) -> None:
    list_of_info = list(random_PackageInfo_sequence) + unusual_packages
    converted = stats_to_csv(list_of_info)
    assert isinstance(converted, str)
    with io.StringIO(converted, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        first_row = next(iter(reader))
    assert isinstance(first_row, dict)
    assert "package_name" in first_row
    first_PackageInfo_item = list_of_info[0]
    assert first_row["package_name"] == first_PackageInfo_item.package_name
    assert "annotated_parameters" in first_row
    assert (
        int(first_row["annotated_parameters"])
        == first_PackageInfo_item.annotation_stats.annotated_parameters
    )
    new_list_of_info = package_stats_from_csv(converted)
    assert new_list_of_info == list_of_info


def test_FileInfo_conversion_to_and_from_csv(
    random_FileInfo_sequence: Sequence[FileInfo],
) -> None:
    converted = stats_to_csv(random_FileInfo_sequence)
    assert isinstance(converted, str)
    with io.StringIO(converted, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        first_row = next(iter(reader))
    assert isinstance(first_row, dict)
    assert "parent_package" in first_row
    first_FileInfo_item = random_FileInfo_sequence[0]
    assert first_row["parent_package"] == first_FileInfo_item.parent_package
    assert "annotated_parameters" in first_row
    assert (
        int(first_row["annotated_parameters"])
        == first_FileInfo_item.annotation_stats.annotated_parameters
    )
    new_list_of_info = file_stats_from_csv(converted)
    assert new_list_of_info == random_FileInfo_sequence


def test_markdown_and_htmlconversion(
    random_PackageInfo_sequence: Sequence[PackageInfo],
    unusual_packages: list[PackageInfo],
) -> None:
    list_of_info = list(random_PackageInfo_sequence) + unusual_packages
    converted_to_markdown = stats_to_markdown(list_of_info)
    assert converted_to_markdown[-1] == "\n"
    assert converted_to_markdown[-2] != "\n"
    assert "`stdlib`" not in converted_to_markdown
    assert "`the stdlib`" not in converted_to_markdown
    assert "``" not in converted_to_markdown
    html1 = markdown.markdown(converted_to_markdown)
    soup = BeautifulSoup(html1, "html.parser")
    assert bool(soup.find()), "Invalid HTML produced!"
