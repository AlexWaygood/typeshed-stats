import random
import string
import sys
import textwrap
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path

# Make sure not to import rich or markdown here, since they're optional dependencies
# Some tests assert behaviour that's predicated on these modules not yet being imported
import attrs
import pytest

from typeshed_stats.gather import (
    AnnotationStats,
    PackageStats,
    PackageStatus,
    PyrightSetting,
    StubtestSetting,
)


@pytest.fixture(autouse=True)
def ensure_optional_dependencies_not_imported() -> Iterator[None]:
    previously_imported_modules = set(sys.modules)
    yield
    newly_imported_thirdparty_modules = {
        module_name
        for module_name in sys.modules
        if (
            module_name not in previously_imported_modules
            and module_name not in sys.stdlib_module_names
        )
    }
    for module_name in newly_imported_thirdparty_modules:
        del sys.modules[module_name]


def random_package_name() -> str:
    def random_string() -> str:
        return "".join(
            random.choice(string.ascii_letters) for _ in range(random.randint(1, 10))
        )

    while (result := random_string()) in {"stdlib", "gdb"}:
        continue  # pragma: no cover
    return result


def write_metadata_text(typeshed: Path, package_name: str, data: str) -> None:
    metadata = typeshed / "stubs" / package_name / "METADATA.toml"
    metadata.write_text(data, encoding="utf-8")


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
def real_typeshed_package_names() -> frozenset[str]:
    return frozenset({"emoji", "protobuf", "appdirs"})


@pytest.fixture(scope="session")
def example_stub_source() -> str:
    return textwrap.dedent(
        """
        import _typeshed
        import typing
        from _typeshed import Incomplete
        from collections.abc import Iterable
        from typing import Any

        a: int
        b: str = ...
        c: Any | None
        d: Any
        d: Incomplete
        e: Iterable[typing.Any]
        f: _typeshed.Incomplete
        g: _typeshed.StrPath

        class Spam:
            a: tuple[typing.Any, ...] | None
            b = ...
            c: int = ...
            d: typing.Sized

        def func1(arg): ...
        def func2(arg: int): ...
        def func3(arg: Incomplete | None = ...): ...
        def func4(arg: Any) -> Any: ...

        class Eggs:
            async def func5(self, arg): ...
            @staticmethod
            async def func6(arg: str) -> list[bytes]: ...
            def func7(arg: Any) -> _typeshed.Incomplete: ...
            @classmethod
            def class_method(cls, eggs: Incomplete): ...

        class Meta(type):
            @classmethod
            def metaclass_classmethod(metacls) -> str: ...
            @classmethod
            async def metaclass_classmethod2(mcls) -> typing.Any: ...
        """
    )


@pytest.fixture(scope="session")
def expected_stats_on_example_stub_file() -> AnnotationStats:
    return AnnotationStats(
        annotated_parameters=6,
        unannotated_parameters=2,
        annotated_returns=5,
        unannotated_returns=5,
        explicit_Incomplete_parameters=2,
        explicit_Incomplete_returns=1,
        explicit_Any_parameters=2,
        explicit_Any_returns=2,
        annotated_variables=11,
        explicit_Any_variables=4,
        explicit_Incomplete_variables=2,
    )


@pytest.fixture(scope="session")
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


@pytest.fixture
def complete_typeshed(
    tmp_path: Path,
    example_stub_source: str,
    pyrightconfig_template: str,
    real_typeshed_package_names: frozenset[str],
) -> Path:
    typeshed = tmp_path
    for directory in "stdlib", "stubs":
        (typeshed / directory).mkdir()

    pyrightconfig_path = typeshed / "pyrightconfig.stricter.json"
    pyrightconfig_path.write_text(pyrightconfig_template.format(""), encoding="utf-8")

    for package_name in real_typeshed_package_names:
        package_dir = typeshed / "stubs" / package_name
        package_dir.mkdir()
        write_metadata_text(typeshed, package_name, "version = 0.1")
        source_dir = package_dir / package_name
        source_dir.mkdir()
        (source_dir / "foo.pyi").write_text(example_stub_source, encoding="utf-8")

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
