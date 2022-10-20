import argparse
import logging
import random
import string
from pathlib import Path

import pytest

from typeshed_stats._cli import _get_argument_parser


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
