import subprocess
import sys
from pathlib import Path

# Make sure not to import rich or markdown here, since they're optional dependencies
# Some tests assert behaviour that's predicated on these modules not yet being imported
import pytest


@pytest.mark.parametrize(
    "args", [[sys.executable, "-m", "typeshed_stats"], ["typeshed-stats"]]
)
def test_running_from_command_line(complete_typeshed: Path, args: list[str]) -> None:
    result = subprocess.run([*args, "--typeshed-dir", str(complete_typeshed)])
    code = result.returncode
    assert code == 0
