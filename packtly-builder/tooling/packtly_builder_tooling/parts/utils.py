from pathlib import Path
from typing import Literal, Optional
import logging
import os
import signal
import subprocess

logger = logging.getLogger(__name__)

Mode = Literal["stream", "capture", "silent"]


def run_subprocess(
    cmd: list[str],
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
        start_new_session=True,
    ) as proc:

        output: list[str] = []

        try:
            if stdin_data is not None and proc.stdin:
                try:
                    proc.stdin.write(stdin_data)
                except BrokenPipeError:
                    # Child exited before consuming stdin; continue collecting output.
                    pass
                finally:
                    proc.stdin.close()

            assert proc.stdout is not None

            for line in proc.stdout:
                output.append(line)

                if mode == "stream":
                    logger.info(line.rstrip())
                elif mode == "capture":
                    logger.debug(line.rstrip())
            returncode = proc.wait()

        except KeyboardInterrupt:
            _terminate(proc)
            raise

    stdout = "".join(output)

    if check and returncode != 0:
        raise subprocess.CalledProcessError(
            returncode,
            cmd,
            output=stdout,
        )

    return subprocess.CompletedProcess(
        cmd,
        returncode,
        stdout,
    )


def _terminate(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGINT)
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
