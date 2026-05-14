import os
from pathlib import Path

from conftest import ExtraArgs


def test_arg(testargs: ExtraArgs) -> None:
    testdeb = Path(os.path.join(os.getcwd(), testargs.dpkgbuild))
    assert os.path.exists(testdeb)
