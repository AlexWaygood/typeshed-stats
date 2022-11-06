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


def random_package_name() -> str:
    def random_string() -> str:
        return "".join(
            random.choice(string.ascii_letters) for _ in range(random.randint(1, 10))
        )

    while (result := random_string()) in {"stdlib", "gdb"}:
        continue  # pragma: no cover
    return result


@pytest.fixture(scope="session")
def EXAMPLE_PACKAGE_NAME() -> str:
    return random_package_name()


@pytest.fixture
def typeshed(EXAMPLE_PACKAGE_NAME: str, tmp_path: Path) -> Path:
    typeshed = tmp_path
    (typeshed / "stdlib").mkdir()
    stubs_dir = typeshed / "stubs"
    stubs_dir.mkdir()
    (stubs_dir / EXAMPLE_PACKAGE_NAME).mkdir()
    return typeshed


@pytest.fixture(scope="session")
def AnnotationStats_fieldnames() -> tuple[str, ...]:
    return tuple(field.name for field in attrs.fields(AnnotationStats))


@pytest.fixture
def make_random_PackageStats(
    AnnotationStats_fieldnames: tuple[str, ...]
) -> Callable[[], PackageStats]:
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
                *[random.randint(0, 1000) for _ in AnnotationStats_fieldnames]
            ),
        )

    return random_PackageStats


@pytest.fixture
def random_PackageStats_sequence(
    make_random_PackageStats: Callable[[], PackageStats]
) -> Sequence[PackageStats]:
    return [make_random_PackageStats() for _ in range(random.randint(3, 10))]


@pytest.fixture(params=[True, False], ids=["use_string_path", "use_pathlib_path"])
def maybe_stringize_path(
    request: pytest.FixtureRequest,
) -> Callable[[Path], Path | str]:
    def inner(path: Path) -> Path | str:
        if request.param:
            return str(path)
        return path

    inner.__name__ = "maybe_stringize_path"
    return inner


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
