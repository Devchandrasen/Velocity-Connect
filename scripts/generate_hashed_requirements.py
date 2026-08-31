#!/usr/bin/env python3
"""Generate a Windows CPython 3.12 wheel-hash lock from a frozen version list."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re

from packaging.utils import canonicalize_name, parse_wheel_filename


PIN = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s;]+)$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--versions", required=True, type=Path)
    parser.add_argument("--wheelhouse", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--pip-version", default="26.2")
    args = parser.parse_args()

    pins: list[tuple[str, str]] = [("pip", args.pip_version)]
    for raw in args.versions.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = PIN.fullmatch(line)
        if match is None:
            raise ValueError(f"unsupported requirement line: {raw!r}")
        pins.append((match.group(1), match.group(2)))

    wheels: dict[tuple[str, str], list[Path]] = {}
    for wheel in sorted(args.wheelhouse.glob("*.whl")):
        name, version, _, _ = parse_wheel_filename(wheel.name)
        wheels.setdefault(
            (canonicalize_name(name), str(version)),
            [],
        ).append(wheel)

    output = [
        "# Hash-locked Windows x86-64 CPython 3.12 analysis environment.",
        "# Generated from environment/requirements-lock.txt and downloaded wheels.",
        "# Regenerate with scripts/generate_hashed_requirements.py.",
    ]
    for name, version in pins:
        key = (canonicalize_name(name), version)
        matches = wheels.get(key, [])
        if len(matches) != 1:
            raise ValueError(
                f"{name}=={version}: expected one compatible wheel, "
                f"found {[path.name for path in matches]}"
            )
        output.append(f"{name}=={version} --hash=sha256:{sha256(matches[0])}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(output) + "\n", encoding="utf-8")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
