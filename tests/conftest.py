import random
import string
import textwrap
from collections.abc import Callable, Sequence
from pathlib import Path

import attrs
import pytest

from typeshed_stats.gather import (
    AnnotationStats,
    PackageStats,
    PackageStatus,
    PyrightSetting,
    StubtestSetting,
)


@pytest.fixture(scope="session")
def EXAMPLE_PACKAGE_NAME() -> str:
    def random_string() -> str:
        return "".join(
            random.choice(string.ascii_letters) for _ in range(random.randint(1, 10))
        )

    while (result := random_string()) in {"stdlib", "gdb"}:
        continue  # pragma: no cover

    return result


@pytest.fixture
def typeshed(EXAMPLE_PACKAGE_NAME: str, tmp_path: Path) -> Path:
    typeshed = tmp_path
    (typeshed / "stdlib").mkdir()
    stubs_dir = typeshed / "stubs"
    stubs_dir.mkdir()
    (stubs_dir / EXAMPLE_PACKAGE_NAME).mkdir()
    return typeshed


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


@pytest.fixture(params=[True, False], ids=["use_string_path", "use_Pathlib_path"])
def use_string_path(request: pytest.FixtureRequest) -> bool:
    return request.param  # type: ignore[no-any-return]


@pytest.fixture
def pyrightconfig_template() -> str:
    return textwrap.dedent(
        """
        {{
            "typeshedPath": ".",
            // A comment to make this invalid JSON
            "exclude": [
                {}
            ],
        }}
        """
    )
