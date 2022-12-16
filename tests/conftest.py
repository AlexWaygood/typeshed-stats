import random
import string
import sys
import textwrap
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path

# Make sure not to import rich or markdown here, since they're optional dependencies
# Some tests assert behaviour that's predicated on these modules not yet being imported
import pytest

from typeshed_stats.gather import (
    AnnotationStats,
    FileInfo,
    PackageInfo,
    PackageStatus,
    PyrightSetting,
    StubtestSetting,
    UploadStatus,
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
        import builtins
        import email
        import typing
        import typing_extensions
        from _typeshed import Incomplete
        from collections.abc import Iterable
        from types import GenericAlias
        from typing import Any, TypeAlias

        a: int
        b: str = ...
        c: Any | None
        d: Any
        d: Incomplete
        e: Iterable[typing.Any]
        f: _typeshed.Incomplete
        g: _typeshed.StrPath
        h: email.message.Message

        # TypeAliases should not count towards the number of "annotated variables"
        i: TypeAlias = int
        j: typing.TypeAlias = str
        k: typing_extensions.TypeAlias = bytes

        class Spam:
            a: tuple[typing.Any, ...] | None
            b = ...
            c: int = ...
            d: typing.Sized
            def __init__(__self) -> None: ...
            def __class_getitem__(cls, item: Any) -> GenericAlias: ...

            # This shouldn't count as an unannotated parameter --
            # it's just "self" with a weird name
            def weird_named_first_param(x): ...

        def func1(arg): ...
        def func2(arg: int): ...
        def func3(arg: Incomplete | None = ...): ...
        def func4(arg: Any) -> Any: ...
        def func5(*args: int, **kwargs: str) -> bool: ...
        def func6(*args, **kwargs): ...
        def func7(*, arg): ...
        def func8(*, arg1: int, arg2: str): ...

        class Eggs:
            def __new__(cls) -> Eggs: ...
            def __init__(self) -> None: ...
            def __init_subclass__(cls) -> None: ...
            async def func5(self, arg): ...
            @staticmethod
            async def func6(arg: str) -> list[bytes]: ...
            @builtins.staticmethod
            def func6_pt_5(arg: str) -> None: ...
            def func7(self, arg: Any) -> _typeshed.Incomplete: ...
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
        annotated_parameters=12,
        unannotated_parameters=5,
        annotated_returns=12,
        unannotated_returns=9,
        explicit_Incomplete_parameters=2,
        explicit_Incomplete_returns=1,
        explicit_Any_parameters=3,
        explicit_Any_returns=2,
        annotated_variables=12,
        explicit_Any_variables=4,
        explicit_Incomplete_variables=2,
    )


PYRIGHTCONFIG_TEMPLATE = """\
{{
    "typeshedPath": ".",
    // A comment to make this invalid JSON
    "exclude": [
        {}
    ],
}}
"""


@pytest.fixture
def complete_typeshed(
    tmp_path: Path,
    example_stub_source: str,
    real_typeshed_package_names: frozenset[str],
) -> Path:
    typeshed = tmp_path
    for directory in "stdlib", "stubs":
        (typeshed / directory).mkdir()

    (typeshed / "pyrightconfig.json").write_text("{}", encoding="utf-8")
    pyrightconfig_path = typeshed / "pyrightconfig.stricter.json"
    pyrightconfig_path.write_text(PYRIGHTCONFIG_TEMPLATE.format(""), encoding="utf-8")

    for package_name in real_typeshed_package_names:
        package_dir = typeshed / "stubs" / package_name
        package_dir.mkdir()
        write_metadata_text(typeshed, package_name, "version = 0.1")
        source_dir = package_dir / package_name
        source_dir.mkdir()
        for filename in "foo", "bar", "spam", "spammy_spam", "ham", "eggs", "bacon":
            path = source_dir / f"{filename}.pyi"
            path.write_text(example_stub_source, encoding="utf-8")

    functools_path = typeshed / "stdlib" / "functools.pyi"
    functools_path.write_text(example_stub_source, encoding="utf-8")
    return typeshed


@pytest.fixture(scope="session")
def AnnotationStats_fieldnames() -> tuple[str, ...]:
    return tuple(AnnotationStats.__annotations__)


def random_identifier() -> str:
    return "".join(
        random.choice(string.ascii_letters) for _ in range(random.randint(1, 10))
    )


def random_AnnotationStats() -> AnnotationStats:
    return AnnotationStats(
        *[random.randint(0, 1000) for _ in AnnotationStats.__annotations__]
    )


def random_PackageInfo() -> PackageInfo:
    stubtest_setting = random.choice(list(StubtestSetting))
    if stubtest_setting is StubtestSetting.SKIPPED:
        stubtest_platforms = []
    else:
        stubtest_platforms = [random.choice(["win32", "darwin", "linux"])]
    return PackageInfo(
        package_name=random_identifier(),
        extra_description=None,
        number_of_lines=random.randint(10, 500),
        package_status=random.choice(list(PackageStatus)),
        stubtest_setting=stubtest_setting,
        stubtest_platforms=stubtest_platforms,
        upload_status=random.choice(list(UploadStatus)),
        pyright_setting=random.choice(list(PyrightSetting)),
        annotation_stats=random_AnnotationStats(),
    )


def random_FileInfo() -> FileInfo:
    package_name = random_identifier()
    return FileInfo(
        file_path=Path(
            "stubs", package_name, package_name, f"{random_identifier()}.pyi"
        ),
        parent_package=package_name,
        number_of_lines=random.randint(10, 500),
        pyright_setting=random.choice(list(PyrightSetting)),
        annotation_stats=random_AnnotationStats(),
    )


@pytest.fixture
def random_PackageInfo_sequence() -> Sequence[PackageInfo]:
    return [random_PackageInfo() for _ in range(random.randint(3, 10))]


@pytest.fixture
def random_FileInfo_sequence() -> Sequence[FileInfo]:
    return [random_FileInfo() for _ in range(random.randint(3, 10))]


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
