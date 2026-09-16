from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
DOCS = (
    ROOT / "README.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "docs/getting-started.md",
    ROOT / "docs/architecture.md",
    ROOT / "docs/experiment-reference.md",
    ROOT / "docs/how-to-run-a-campaign.md",
    ROOT / "docs/evidence-model.md",
)
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
HTML_SOURCE = re.compile(r"\b(?:src|href)=\"([^\"]+)\"")


def _local_targets(path: Path) -> list[Path]:
    text = path.read_text(encoding="utf-8")
    raw_targets = MARKDOWN_LINK.findall(text) + HTML_SOURCE.findall(text)
    targets = []
    for raw in raw_targets:
        target = raw.strip().split(maxsplit=1)[0].strip("<>")
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or target.startswith(("#", "mailto:")):
            continue
        relative = unquote(parsed.path)
        if relative:
            targets.append((path.parent / relative).resolve())
    return targets


def test_landing_page_links_every_guide() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for guide in DOCS[2:]:
        assert guide.relative_to(ROOT).as_posix() in readme


def test_local_documentation_links_resolve() -> None:
    failures = []
    for document in DOCS:
        assert document.is_file(), document
        for target in _local_targets(document):
            if not target.exists():
                failures.append(f"{document.relative_to(ROOT)} -> {target}")
    assert not failures, "Broken local documentation links:\n" + "\n".join(failures)


def test_banner_is_accessible_and_self_contained() -> None:
    banner = ROOT / "docs/assets/velocity-connect-banner.svg"
    text = banner.read_text(encoding="utf-8")
    assert "<title" in text and "<desc" in text
    assert "<image" not in text
    assert "xlink:href" not in text
