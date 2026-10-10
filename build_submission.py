"""Build a reproducible Kaggle submission archive for MicroAgent-Edge."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


PROJECT_ROOT = Path(__file__).resolve().parent
SUBMISSION_PATH = PROJECT_ROOT / "submission.zip"
REQUIRED_FILES = (
    "core",
    "agent",
    "adapters",
    "runner.py",
    "agent.yaml",
    "requirements.txt",
)


def build_submission() -> Path:
    """Package the required source tree and verify the archive layout."""
    missing = [
        item
        for item in REQUIRED_FILES
        if not (PROJECT_ROOT / item).exists()
    ]
    if missing:
        raise FileNotFoundError(
            f"Cannot build submission; required project path(s) missing: {missing}"
        )

    files_to_add: list[tuple[Path, str]] = []
    for item in REQUIRED_FILES:
        source = PROJECT_ROOT / item
        if source.is_dir():
            files_to_add.extend(
                (path, path.relative_to(PROJECT_ROOT).as_posix())
                for path in sorted(source.rglob("*"))
                if path.is_file() and "__pycache__" not in path.parts
            )
        else:
            files_to_add.append((source, item))

    with ZipFile(SUBMISSION_PATH, "w", compression=ZIP_DEFLATED) as archive:
        for source, archive_name in files_to_add:
            archive.write(source, archive_name)

    with ZipFile(SUBMISSION_PATH, "r") as archive:
        names = set(archive.namelist())
        if archive.testzip() is not None:
            raise ValueError(f"Submission archive failed CRC verification: {SUBMISSION_PATH}")
        required_archive_files = {
            "agent.yaml",
            "runner.py",
            "requirements.txt",
        }
        missing_archive_files = sorted(required_archive_files - names)
        if missing_archive_files:
            raise ValueError(
                "Submission archive is missing required root file(s): "
                f"{missing_archive_files}"
            )
        for directory in ("core", "agent", "adapters"):
            if not any(name.startswith(f"{directory}/") for name in names):
                raise ValueError(
                    f"Submission archive does not contain files from {directory}/"
                )

    print(
        f"Created and verified {SUBMISSION_PATH} "
        f"({SUBMISSION_PATH.stat().st_size} bytes; {len(files_to_add)} files)"
    )
    return SUBMISSION_PATH


if __name__ == "__main__":
    build_submission()
