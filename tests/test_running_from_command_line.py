import subprocess
from pathlib import Path


def test_running_from_command_line(complete_typeshed: Path) -> None:
    result = subprocess.run(
        ["typeshed-stats", "--typeshed-dir", str(complete_typeshed)]
    )
    code = result.returncode
    assert code == 0
