import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "args", [[sys.executable, "-m", "typeshed_stats"], ["typeshed-stats"]]
)
def test_running_from_command_line(complete_typeshed: Path, args: list[str]) -> None:
    result = subprocess.run([*args, "--typeshed-dir", str(complete_typeshed)])
    code = result.returncode
    assert code == 0
