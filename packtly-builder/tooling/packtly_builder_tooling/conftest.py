import pytest
from typing import Any, TYPE_CHECKING
from typing import NamedTuple

if TYPE_CHECKING:
    from pytest import Config, FixtureRequest
else:
    Config = Any
    FixtureRequest = Any


class ExtraArgs(NamedTuple):
    dpkgbuild: str


def pytest_addoption(parser: Config) -> None:
    parser.addoption(
        "--dpkgbuild",
        action="store",
        default="nopath",
        help="path to dpkg test build",
    )


@pytest.fixture(autouse=True)
def testargs(request: FixtureRequest) -> ExtraArgs:
    dpkgbuild = request.config.getoption("dpkgbuild")
    print(f"dpkgbuild test package located at {dpkgbuild}")
    return ExtraArgs(dpkgbuild=dpkgbuild)
