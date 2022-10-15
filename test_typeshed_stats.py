"""Test the package."""

import csv
import io
import json

import markdown

from typeshed_stats import (
    AnnotationStats,
    PackageStats,
    PackageStatus,
    PyrightSetting,
    StubtestSetting,
    stats_from_csv,
    stats_from_json,
    stats_to_csv,
    stats_to_html,
    stats_to_json,
    stats_to_markdown,
)

info_on_foo = PackageStats(
    "foo",
    8,
    PackageStatus.UP_TO_DATE,
    StubtestSetting.MISSING_STUBS_IGNORED,
    PyrightSetting.STRICT,
    AnnotationStats(),
)
list_of_info = [info_on_foo, info_on_foo]


def test_conversion_to_and_from_json() -> None:
    """Test conversion to and from JSON."""

    converted = stats_to_json(list_of_info)
    assert isinstance(converted, str)
    lst = json.loads(converted)
    assert isinstance(lst, list)
    assert all(isinstance(item, dict) and "package_name" in item for item in lst)
    new_list_of_info = stats_from_json(converted)
    assert new_list_of_info == list_of_info


def test_conversion_to_and_from_csv() -> None:
    """Test conversion to and from CSV."""

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
    """Test conversion to MarkDown."""

    converted_to_markdown = stats_to_markdown(list_of_info)
    html1 = markdown.markdown(converted_to_markdown)
    html2 = stats_to_html(list_of_info)
    assert html1 == html2
