#!/usr/bin/env python3
"""Verify that a ScaffoldGuard wheel contains required runtime package data."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from zipfile import BadZipFile, ZipFile

PACKAGE_ROOT = "scaffold_guard"
TEMPLATE_ROOT = f"{PACKAGE_ROOT}/templates"
REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_SOURCE_ROOT = REPO_ROOT / "src" / "scaffold_guard" / "templates"
LIFECYCLE_RUNTIME_MEMBERS = (
    f"{PACKAGE_ROOT}/legacy.py",
    f"{PACKAGE_ROOT}/manifest.py",
    f"{PACKAGE_ROOT}/migrations.py",
    f"{PACKAGE_ROOT}/upgrade.py",
    f"{PACKAGE_ROOT}/versions.py",
    f"{PACKAGE_ROOT}/py.typed",
)


def parse_args() -> argparse.Namespace:
    """Parse the wheel path to inspect."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path, help="path to one built wheel")
    return parser.parse_args()


def wheel_members(wheel: Path) -> frozenset[str]:
    """Return non-directory archive member names from a wheel."""
    with ZipFile(wheel) as archive:
        return frozenset(info.filename for info in archive.infolist() if not info.is_dir())


def template_members(source_root: Path = TEMPLATE_SOURCE_ROOT) -> frozenset[str]:
    """Return wheel member names for every template tracked in the source tree."""
    if not source_root.is_dir():
        raise FileNotFoundError(f"Template source root does not exist: {source_root}")

    return frozenset(
        f"{TEMPLATE_ROOT}/{path.relative_to(source_root).as_posix()}"
        for path in source_root.rglob("*")
        if path.is_file()
    )


def required_members(source_root: Path = TEMPLATE_SOURCE_ROOT) -> frozenset[str]:
    """Return all wheel members required for upgrade lifecycle behavior."""
    return frozenset(LIFECYCLE_RUNTIME_MEMBERS).union(template_members(source_root))


def main() -> int:
    """Inspect the requested wheel and report any missing required members."""
    wheel = parse_args().wheel
    if not wheel.is_file():
        print(f"Wheel does not exist: {wheel}", file=sys.stderr)
        return 2

    try:
        members = wheel_members(wheel)
        required = required_members()
    except (BadZipFile, FileNotFoundError, OSError) as error:
        print(f"Unable to inspect wheel {wheel}: {error}", file=sys.stderr)
        return 2

    missing = sorted(required.difference(members))
    if missing:
        print(f"Wheel is missing {len(missing)} required member(s): {wheel}", file=sys.stderr)
        for member in missing:
            print(f"  {member}", file=sys.stderr)
        return 1

    print(f"Wheel inspection passed: {wheel} ({len(members)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
