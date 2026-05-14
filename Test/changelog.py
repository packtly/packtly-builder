import re
from pathlib import Path
from typing import Optional


def _get_pyproject_path(start: Optional[Path] = None) -> Optional[Path]:
    start = Path(start or Path.cwd())
    print(f"Searching in: {start}")  # ← Debug print

    for path in start.rglob("pyproject.toml"):
        print(f"Found: {path}")      # ← Debug print
        return path

    return None


def _get_version_from_file() -> Optional[str]:
    # CHANGELOG path relative to pyproject.toml
    source = "../../CHANGELOG.md"
    pattern = r"^## \[(\d+\.\d+\.\d+)\]"  # Matches: ## [1.2.3]

    pyproject_path = _get_pyproject_path(
        Path(__file__).parent.parent / "packtly-builder")
    if pyproject_path is None:
        raise RuntimeError("Unable to find pyproject.toml")

    changelog_path = pyproject_path.parent / source
    content = changelog_path.read_text(encoding="utf-8").strip()

    result = re.search(pattern, content, re.MULTILINE)
    if result is None:
        raise ValueError(
            f"No version match in '{source}' for pattern '{pattern}'")

    return result.group(1)


def main() -> None:
    version = _get_version_from_file()
    print(f"Version is {version}")


if __name__ == "__main__":
    main()
