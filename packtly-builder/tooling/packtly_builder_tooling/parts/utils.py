from pathlib import Path
from typing import List, Optional, Literal
import subprocess
import logging

logger = logging.getLogger(__name__)

Mode = Literal["stream", "capture", "silent"]


def run_subprocess(
    cmd: List[str],
    cwd: Path,
    stdin_data: Optional[str] = None,
    mode: Mode = "stream",
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """
    Unified subprocess runner:
    - stream  -> logs output line-by-line
    - capture -> returns stdout
    - silent  -> no logging, but still returns stdout
    """

    with subprocess.Popen(
        cmd,
        cwd=cwd,
        text=True,
        stdin=subprocess.PIPE if stdin_data is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    ) as proc:

        stdout_chunks: list[str] = []

        if proc.stdout is None:
            raise RuntimeError("subprocess stdout pipe was not created")

        # feed stdin if needed
        if stdin_data is not None and proc.stdin:
            try:
                proc.stdin.write(stdin_data)
            except BrokenPipeError:
                # Child exited before consuming stdin. We continue to collect
                # available output and use the same non-zero handling below.
                pass
            finally:
                proc.stdin.close()

        # STREAM MODE
        if mode == "stream":
            for line in proc.stdout:
                logger.info(line.rstrip())
                stdout_chunks.append(line)

        # CAPTURE / SILENT MODE
        else:
            for line in proc.stdout:
                stdout_chunks.append(line)
                if mode == "capture":
                    logger.debug(line.rstrip())

        ret = proc.wait()

    stdout = "".join(stdout_chunks)

    if check and ret != 0:
        raise subprocess.CalledProcessError(ret, cmd, output=stdout)

    return subprocess.CompletedProcess(cmd, ret, stdout)
