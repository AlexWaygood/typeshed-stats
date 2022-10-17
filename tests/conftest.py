import random
import string
from pathlib import Path

import pytest


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
