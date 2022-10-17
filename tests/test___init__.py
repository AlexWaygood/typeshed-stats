import sys
from unittest import mock

import pytest


@mock.patch.object(sys, "version_info", new=(3, 9, 8, "final", 0))
def test_import_fails_on_less_than_3_point_10() -> None:
    sys.modules.pop("typeshed_stats")
    with pytest.raises(ImportError):
        import typeshed_stats  # noqa: F401
