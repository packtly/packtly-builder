import pytest
import signal
import subprocess
from unittest.mock import MagicMock, patch
from pathlib import Path
from packtly_builder_tooling.parts.utils import (
    run_subprocess,
)


def test_run_subprocess_success(tmp_path: Path) -> None:
    proc = MagicMock()
    proc.stdout = iter(["line1\n", "line2\n"])
    proc.wait.return_value = 0

    proc.__enter__.return_value = proc
    proc.__exit__.return_value = None

    with patch("subprocess.Popen", return_value=proc):
        run_subprocess(cmd=["echo", "test"], cwd=tmp_path)


def test_run_subprocess_failure(tmp_path: Path) -> None:
    proc = MagicMock()
    proc.stdout = iter(["error\n"])
    proc.wait.return_value = 1

    proc.__enter__.return_value = proc
    proc.__exit__.return_value = None

    with patch("subprocess.Popen", return_value=proc):
        with pytest.raises(subprocess.CalledProcessError):
            run_subprocess(cmd=["false"], cwd=tmp_path)


def test_run_streamed_logs_output(tmp_path: Path) -> None:
    proc = MagicMock()
    proc.stdout = iter(["foo\n", "bar\n"])
    proc.wait.return_value = 0

    proc.__enter__.return_value = proc
    proc.__exit__.return_value = None

    with (
        patch("subprocess.Popen", return_value=proc),
        patch("packtly_builder_tooling.parts.utils.logger.info") as mock_logger,
    ):
        run_subprocess(["echo"], tmp_path)

    print(mock_logger.call_args_list)

    mock_logger.assert_any_call("foo")
    mock_logger.assert_any_call("bar")


def test_run_subprocess_writes_stdin(tmp_path: Path) -> None:
    proc = MagicMock()
    proc.stdout = iter([])
    proc.stdin = MagicMock()
    proc.wait.return_value = 0

    proc.__enter__.return_value = proc
    proc.__exit__.return_value = None

    with patch("subprocess.Popen", return_value=proc):
        run_subprocess(
            ["cmd"],
            tmp_path,
            stdin_data="y\n",
        )

    proc.stdin.write.assert_called_once_with("y\n")
    proc.stdin.close.assert_called_once()


def test_run_subprocess_stream(tmp_path: Path) -> None:
    cmd = ["echo", "hello"]
    with patch("packtly_builder_tooling.parts.utils.logger.info") as mock_logger:
        run_subprocess(cmd, tmp_path, mode="stream")

    mock_logger.assert_any_call("hello")


def test_run_subprocess_capture(tmp_path: Path) -> None:
    cmd = ["echo", "hello"]
    with patch("packtly_builder_tooling.parts.utils.logger.debug") as mock_logger:
        result = run_subprocess(cmd, tmp_path, mode="capture")

    assert result.stdout == "hello\n"
    mock_logger.assert_any_call("hello")


def test_run_subprocess_silent(tmp_path: Path) -> None:
    cmd = ["echo", "hello"]
    with (
        patch("packtly_builder_tooling.parts.utils.logger.info") as mock_info,
        patch("packtly_builder_tooling.parts.utils.logger.debug") as mock_debug,
    ):
        result = run_subprocess(cmd, tmp_path, mode="silent")

    assert result.stdout == "hello\n"
    mock_info.assert_not_called()
    mock_debug.assert_not_called()


def test_run_subprocess_stdin(tmp_path: Path) -> None:
    with patch("packtly_builder_tooling.parts.utils.logger.info") as mock_logger:
        run_subprocess(
            ["cat"],
            tmp_path,
            stdin_data="hello\n",
        )

    mock_logger.assert_any_call("hello")


def test_run_subprocess_empty_stdin_still_opens_pipe(tmp_path: Path) -> None:
    proc = MagicMock()
    proc.stdout = iter([])
    proc.stdin = MagicMock()
    proc.wait.return_value = 0

    proc.__enter__.return_value = proc
    proc.__exit__.return_value = None

    with patch("subprocess.Popen", return_value=proc) as mock_popen:
        run_subprocess(["cat"], tmp_path, stdin_data="")

    assert mock_popen.call_args.kwargs["stdin"] == subprocess.PIPE
    proc.stdin.write.assert_called_once_with("")
    proc.stdin.close.assert_called_once()


def test_run_subprocess_handles_broken_pipe_and_raises_calledprocesserror(
    tmp_path: Path,
) -> None:
    proc = MagicMock()
    proc.stdout = iter(["child exited early\n"])
    proc.stdin = MagicMock()
    proc.stdin.write.side_effect = BrokenPipeError
    proc.wait.return_value = 1

    proc.__enter__.return_value = proc
    proc.__exit__.return_value = None

    with patch("subprocess.Popen", return_value=proc):
        with pytest.raises(subprocess.CalledProcessError) as exc_info:
            run_subprocess(["cmd"], tmp_path, stdin_data="data")

    assert exc_info.value.returncode == 1
    assert "child exited early" in str(exc_info.value.output)
    proc.stdin.close.assert_called_once()


def test_run_subprocess_forwards_sigint_on_keyboardinterrupt(tmp_path: Path) -> None:
    proc = MagicMock()
    proc.pid = 4242
    proc.stdin = None
    proc.poll.return_value = None
    proc.wait.return_value = 0

    proc.stdout = MagicMock()
    proc.stdout.__iter__.side_effect = KeyboardInterrupt
    proc.__enter__.return_value = proc
    proc.__exit__.return_value = None

    with (
        patch("subprocess.Popen", return_value=proc),
        patch("packtly_builder_tooling.parts.utils.os.killpg") as mock_killpg,
    ):
        with pytest.raises(KeyboardInterrupt):
            run_subprocess(["cmd"], tmp_path)

    mock_killpg.assert_called_with(4242, signal.SIGINT)
