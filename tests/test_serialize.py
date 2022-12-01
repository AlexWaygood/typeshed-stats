import csv
import io
import json
from collections.abc import Sequence

import markdown
from bs4 import BeautifulSoup

from typeshed_stats.gather import PackageInfo
from typeshed_stats.serialize import (
    stats_from_csv,
    stats_from_json,
    stats_to_csv,
    stats_to_json,
    stats_to_markdown,
)


def test_conversion_to_and_from_json(
    random_PackageInfo_sequence: Sequence[PackageInfo],
) -> None:
    converted = stats_to_json(random_PackageInfo_sequence)
    assert converted[-1] == "\n"
    assert converted[-2] != "\n"
    assert isinstance(converted, str)
    lst = json.loads(converted)
    assert isinstance(lst, list)
    assert all(isinstance(item, dict) and "package_name" in item for item in lst)
    new_package_stats = stats_from_json(converted)
    assert new_package_stats == random_PackageInfo_sequence


def test_conversion_to_and_from_csv(
    random_PackageInfo_sequence: Sequence[PackageInfo],
) -> None:
    converted = stats_to_csv(random_PackageInfo_sequence)
    assert isinstance(converted, str)
    with io.StringIO(converted, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        first_row = next(iter(reader))
    assert isinstance(first_row, dict)
    assert "package_name" in first_row
    first_PackageInfo_item = random_PackageInfo_sequence[0]
    assert first_row["package_name"] == first_PackageInfo_item.package_name
    assert "annotated_parameters" in first_row
    assert (
        int(first_row["annotated_parameters"])
        == first_PackageInfo_item.annotation_stats.annotated_parameters
    )
    new_list_of_info = stats_from_csv(converted)
    assert new_list_of_info == random_PackageInfo_sequence


def test_markdown_and_htmlconversion(
    random_PackageInfo_sequence: Sequence[PackageInfo],
) -> None:
    converted_to_markdown = stats_to_markdown(random_PackageInfo_sequence)
    assert converted_to_markdown[-1] == "\n"
    assert converted_to_markdown[-2] != "\n"
    html1 = markdown.markdown(converted_to_markdown)
    soup = BeautifulSoup(html1, "html.parser")
    assert bool(soup.find()), "Invalid HTML produced!"
