import pytest
import subprocess
from unittest.mock import MagicMock, patch
from pathlib import Path
from packtly_builder_tooling.parts.utils import (
    run_subprocess,
)


def test_run_subprocess_success() -> None:
    proc = MagicMock()
    proc.stdout = iter(["line1\n", "line2\n"])
    proc.wait.return_value = 0

    proc.__enter__.return_value = proc
    proc.__exit__.return_value = None

    with patch("subprocess.Popen", return_value=proc):
        run_subprocess(cmd=["echo", "test"], cwd=Path("/tmp"))


def test_run_subprocess_failure() -> None:
    proc = MagicMock()
    proc.stdout = iter(["error\n"])
    proc.wait.return_value = 1

    proc.__enter__.return_value = proc
    proc.__exit__.return_value = None

    with patch("subprocess.Popen", return_value=proc):
        with pytest.raises(subprocess.CalledProcessError):
            run_subprocess(cmd=["false"], cwd=Path("/tmp"))


def test_run_streamed_logs_output() -> None:
    proc = MagicMock()
    proc.stdout = iter(["foo\n", "bar\n"])
    proc.wait.return_value = 0

    proc.__enter__.return_value = proc
    proc.__exit__.return_value = None

    with (
        patch("subprocess.Popen", return_value=proc),
        patch("packtly_builder_tooling.parts.utils.logger.info") as mock_logger,
    ):
        run_subprocess(["echo"], Path("/tmp"))

    print(mock_logger.call_args_list)

    mock_logger.assert_any_call("foo")
    mock_logger.assert_any_call("bar")


def test_run_subprocess_writes_stdin() -> None:
    proc = MagicMock()
    proc.stdout = iter([])
    proc.stdin = MagicMock()
    proc.wait.return_value = 0

    proc.__enter__.return_value = proc
    proc.__exit__.return_value = None

    with patch("subprocess.Popen", return_value=proc):
        run_subprocess(
            ["cmd"],
            Path("/tmp"),
            stdin_data="y\n",
        )

    proc.stdin.write.assert_called_once_with("y\n")
    proc.stdin.close.assert_called_once()


def test_run_subprocess_stream() -> None:
    cmd = ["echo", "hello"]
    with patch("packtly_builder_tooling.parts.utils.logger.info") as mock_logger:
        run_subprocess(cmd, Path("/tmp"), mode="stream")

    mock_logger.assert_any_call("hello")


def test_run_subprocess_capture() -> None:
    cmd = ["echo", "hello"]
    with patch("packtly_builder_tooling.parts.utils.logger.debug") as mock_logger:
        result = run_subprocess(cmd, Path("/tmp"), mode="capture")

    assert result.stdout == "hello\n"
    mock_logger.assert_any_call("hello")


def test_run_subprocess_silent() -> None:
    cmd = ["echo", "hello"]
    with (
        patch("packtly_builder_tooling.parts.utils.logger.info") as mock_info,
        patch("packtly_builder_tooling.parts.utils.logger.debug") as mock_debug,
    ):
        result = run_subprocess(cmd, Path("/tmp"), mode="silent")

    assert result.stdout == "hello\n"
    mock_info.assert_not_called()
    mock_debug.assert_not_called()


def test_run_subprocess_stdin() -> None:
    with patch("packtly_builder_tooling.parts.utils.logger.info") as mock_logger:
        run_subprocess(
            ["cat"],
            Path("/tmp"),
            stdin_data="hello\n",
        )

    mock_logger.assert_any_call("hello")


def test_run_subprocess_empty_stdin_still_opens_pipe() -> None:
    proc = MagicMock()
    proc.stdout = iter([])
    proc.stdin = MagicMock()
    proc.wait.return_value = 0

    proc.__enter__.return_value = proc
    proc.__exit__.return_value = None

    with patch("subprocess.Popen", return_value=proc) as mock_popen:
        run_subprocess(["cat"], Path("/tmp"), stdin_data="")

    assert mock_popen.call_args.kwargs["stdin"] == subprocess.PIPE
    proc.stdin.write.assert_called_once_with("")
    proc.stdin.close.assert_called_once()


def test_run_subprocess_handles_broken_pipe_and_raises_calledprocesserror() -> None:
    proc = MagicMock()
    proc.stdout = iter(["child exited early\n"])
    proc.stdin = MagicMock()
    proc.stdin.write.side_effect = BrokenPipeError
    proc.wait.return_value = 1

    proc.__enter__.return_value = proc
    proc.__exit__.return_value = None

    with patch("subprocess.Popen", return_value=proc):
        with pytest.raises(subprocess.CalledProcessError) as exc_info:
            run_subprocess(["cmd"], Path("/tmp"), stdin_data="data")

    assert exc_info.value.returncode == 1
    assert "child exited early" in str(exc_info.value.output)
    proc.stdin.close.assert_called_once()
