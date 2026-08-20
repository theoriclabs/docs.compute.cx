#!/usr/bin/env python3
"""Fail if showcased file.py::function entrypoints lack source, or if the Agent Skill URL is down."""

from __future__ import annotations

import argparse
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_SKILL = "https://compute.cx/SKILL.md"
ENTRYPOINT_RE = re.compile(r"\b([A-Za-z0-9_./-]+\.py)::([A-Za-z_][A-Za-z0-9_]*)\b")
PLACEHOLDER_FILES = {"file.py"}
DEF_RE = re.compile(r"^def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", re.MULTILINE)
MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
HREF_RE = re.compile(r'\bhref="([^"]+)"')
FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---", re.DOTALL)

DOC_GLOBS = ("*.mdx", "*.md")
SOURCE_GLOBS = ("*.py",)


def iter_text_files() -> list[Path]:
    files: list[Path] = []
    for pattern in DOC_GLOBS + SOURCE_GLOBS:
        files.extend(p for p in ROOT.rglob(pattern) if _include(p))
    return sorted(set(files))


def _include(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if any(part in {".git", ".mintlify", "node_modules"} for part in rel.parts):
        return False
    if rel.parts[0] == "scripts":
        return False
    return True


def extract_links(text: str) -> list[str]:
    found = [m.group(1).strip() for m in MD_LINK_RE.finditer(text)]
    found.extend(m.group(1).strip() for m in HREF_RE.finditer(text))
    return found


def resolve_local(href: str) -> Path | None:
    raw = href.split("#", 1)[0].strip()
    if not raw:
        return None
    for prefix in ("https://docs.compute.cx", "http://docs.compute.cx"):
        if raw.startswith(prefix):
            raw = raw[len(prefix) :]
            break
    if raw.startswith("https://") or raw.startswith("http://"):
        return None
    if not raw.startswith("/"):
        return None
    rel = raw.lstrip("/")
    if not rel:
        candidates = [ROOT / "index.mdx", ROOT / "index.md"]
    else:
        candidates = [
            ROOT / rel,
            ROOT / f"{rel}.mdx",
            ROOT / f"{rel}.md",
            ROOT / rel / "index.mdx",
            ROOT / rel / "index.md",
        ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def provides(path: Path, text: str) -> set[tuple[str, str]]:
    funcs = set(DEF_RE.findall(text))
    names = {path.name} if path.suffix == ".py" else set()
    names.update(m.group(1).rsplit("/", 1)[-1] for m in ENTRYPOINT_RE.finditer(text))
    if path.suffix != ".py":
        names.update(re.findall(r"\b([A-Za-z0-9_-]+\.py)\b", text))
    return {(name, func) for name in names for func in funcs}


def check_entrypoints() -> list[str]:
    files = {path: path.read_text(encoding="utf-8") for path in iter_text_files()}
    offered: dict[Path, set[tuple[str, str]]] = {
        path: provides(path, text) for path, text in files.items()
    }
    errors: list[str] = []

    for path, text in files.items():
        if path.suffix not in {".md", ".mdx"} or path.name == "README.md":
            continue
        linked_sources: set[tuple[str, str]] = set(offered[path])
        for href in extract_links(text):
            target = resolve_local(href)
            if target is not None and target in offered:
                linked_sources.update(offered[target])
            elif target is not None and target.suffix == ".py":
                linked_sources.update(provides(target, files.get(target, target.read_text(encoding="utf-8"))))
        rel = path.relative_to(ROOT)
        for match in ENTRYPOINT_RE.finditer(text):
            filename = match.group(1).rsplit("/", 1)[-1]
            if filename in PLACEHOLDER_FILES:
                continue
            pair = (filename, match.group(2))
            if pair not in linked_sources:
                errors.append(
                    f"{rel}: {match.group(1)}::{match.group(2)} has no source on this page "
                    "and no explicit link to a page or file that defines it"
                )
    return errors


def check_skill_file() -> list[str]:
    skill = ROOT / "SKILL.md"
    if not skill.is_file():
        return ["SKILL.md is missing from the docs repository"]
    text = skill.read_text(encoding="utf-8")
    fm = FRONTMATTER_RE.match(text)
    if fm is None:
        return ["SKILL.md must start with YAML frontmatter"]
    body = fm.group(1)
    errors: list[str] = []
    if not re.search(r"^name:\s*\S", body, re.MULTILINE):
        errors.append("SKILL.md frontmatter is missing name")
    if not re.search(r"^description:\s*\S", body, re.MULTILINE):
        errors.append("SKILL.md frontmatter is missing description")
    page = ROOT / "get-started" / "agent-skill.mdx"
    if page.is_file() and CANONICAL_SKILL not in page.read_text(encoding="utf-8"):
        errors.append("get-started/agent-skill.mdx must link to https://compute.cx/SKILL.md")
    home = ROOT / "index.mdx"
    if home.is_file() and "/get-started/agent-skill" not in home.read_text(encoding="utf-8"):
        errors.append("index.mdx must link to /get-started/agent-skill")
    return errors


def check_canonical_skill(*, strict: bool) -> list[str]:
    request = urllib.request.Request(
        CANONICAL_SKILL,
        method="GET",
        headers={"User-Agent": "docs.compute.cx-check"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status = response.status
            content_type = response.headers.get("Content-Type", "")
            body = response.read(2048)
    except urllib.error.HTTPError as exc:
        status = exc.code
        content_type = ""
        body = b""
    except urllib.error.URLError as exc:
        msg = f"{CANONICAL_SKILL} is unreachable ({exc.reason})"
        return [msg] if strict else []

    if status != 200:
        msg = (
            f"{CANONICAL_SKILL} returned HTTP {status}; "
            "do not ship the Agent Skill page until the canonical endpoint returns 200"
        )
        if strict:
            return [msg]
        print(f"warning: {msg}", file=sys.stderr)
        return []

    if b"name:" not in body and b"Compute" not in body:
        msg = f"{CANONICAL_SKILL} did not look like a SKILL.md document"
        return [msg] if strict else []

    if content_type and not any(
        token in content_type.lower() for token in ("text/plain", "text/markdown", "text/x-markdown")
    ):
        print(
            f"warning: {CANONICAL_SKILL} Content-Type is {content_type!r}; prefer text/plain or text/markdown",
            file=sys.stderr,
        )
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if https://compute.cx/SKILL.md is not HTTP 200 (CI default).",
    )
    args = parser.parse_args()
    strict = args.strict or os.environ.get("GITHUB_ACTIONS") == "true"

    errors = check_entrypoints() + check_skill_file() + check_canonical_skill(strict=strict)
    if errors:
        print("docs check failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("docs check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
