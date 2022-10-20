import argparse
import logging
import random
import string
from collections.abc import Callable, Sequence
from pathlib import Path

import attrs
import pytest

from typeshed_stats._cli import _get_argument_parser
from typeshed_stats.api import (
    AnnotationStats,
    PackageStats,
    PackageStatus,
    PyrightSetting,
    StubtestSetting,
)


@pytest.fixture(scope="session")
def EXAMPLE_PACKAGE_NAME() -> str:
    return "".join(
        random.choice(string.ascii_letters) for _ in range(random.randint(1, 10))
    )


@pytest.fixture
def typeshed(EXAMPLE_PACKAGE_NAME: str, tmp_path: Path) -> Path:
    typeshed = tmp_path
    (typeshed / "stdlib").mkdir()
    stubs_dir = typeshed / "stubs"
    stubs_dir.mkdir()
    (stubs_dir / EXAMPLE_PACKAGE_NAME).mkdir()
    return typeshed


@pytest.fixture(scope="session")
def parser() -> argparse.ArgumentParser:
    parser = _get_argument_parser()
    assert isinstance(parser, argparse.ArgumentParser)
    return parser


@pytest.fixture(scope="session")
def LOGGING_LEVELS() -> tuple[int, ...]:
    return (
        logging.CRITICAL,
        logging.ERROR,
        logging.WARNING,
        logging.INFO,
        logging.DEBUG,
        logging.NOTSET,
    )


@pytest.fixture
def make_random_PackageStats() -> Callable[[], PackageStats]:
    def random_PackageStats() -> PackageStats:
        return PackageStats(
            package_name="".join(
                random.choice(string.ascii_letters)
                for _ in range(random.randint(1, 10))
            ),
            number_of_lines=random.randint(10, 500),
            package_status=random.choice(list(PackageStatus)),
            stubtest_setting=random.choice(list(StubtestSetting)),
            pyright_setting=random.choice(list(PyrightSetting)),
            annotation_stats=AnnotationStats(
                *[random.randint(0, 1000) for _ in attrs.fields(AnnotationStats)]
            ),
        )

    return random_PackageStats


@pytest.fixture
def random_PackageStats_sequence(
    make_random_PackageStats: Callable[[], PackageStats]
) -> Sequence[PackageStats]:
    return [make_random_PackageStats() for _ in range(random.randint(3, 10))]
