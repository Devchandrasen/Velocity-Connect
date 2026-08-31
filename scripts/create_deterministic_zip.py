#!/usr/bin/env python3
"""Create a sorted, metadata-normalized ZIP from an explicit file map."""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import shutil
import time
import zipfile

WINDOWS_INVALID = frozenset('<>:"\\|?*')


def validate_entry(name: str) -> None:
    if not name or "\\" in name or ":" in name:
        raise ValueError(f"unsafe archive entry: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ValueError(f"unsafe archive entry: {name!r}")
    for part in path.parts:
        if not part or part.rstrip(" .") != part:
            raise ValueError(f"unsafe archive entry component: {name!r}")
        if any(
            character in WINDOWS_INVALID or ord(character) < 32
            for character in part
        ):
            raise ValueError(f"Windows-invalid archive entry: {name!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file-map", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-date-epoch", type=int, default=1767225600)
    args = parser.parse_args()

    records = json.loads(args.file_map.read_text(encoding="utf-8-sig"))
    if not isinstance(records, list) or not records:
        raise ValueError("file map must be a nonempty list")
    mapped: dict[str, Path] = {}
    collision_keys: set[str] = set()
    for record in records:
        name = str(record["entry"]).replace("\\", "/")
        validate_entry(name)
        collision = name.casefold()
        if collision in collision_keys:
            raise ValueError(f"duplicate/case-colliding entry: {name}")
        collision_keys.add(collision)
        source = Path(record["source"]).resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        mapped[name] = source

    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.gmtime(args.source_date_epoch)[:6]
    if stamp[0] < 1980:
        raise ValueError("ZIP timestamps must be 1980 or later")

    with zipfile.ZipFile(
        output,
        mode="x",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        allowZip64=True,
    ) as archive:
        for name in sorted(mapped):
            info = zipfile.ZipInfo(filename=name, date_time=stamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.flag_bits |= 0x800
            with mapped[name].open("rb") as source, archive.open(
                info, mode="w", force_zip64=True
            ) as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
