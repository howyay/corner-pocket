#!/usr/bin/env python3
"""Move every line citation that a commit range moved.

A citation is the text ``path:N`` or ``path:N-M`` in a document, a test or a page.
A citation is payable when its cited line moved and its text stands at the new
number:

* the cited line moved at all (``map[N] != N``);
* the text at ``map[N]`` in the working tree equals the text at ``N`` in the
  old tree, so the same line stands at the new number;
* both ends of a range move on their own, so a range keeps its form.

The sweep is a one-shot pass per base commit.  It records the base it swept in
``.git/citation-sweep.json`` and refuses a second run for that base, because the
working tree then states the post-round numbers already and a second pass would
shift them again.

Rules for a round:

* Hold every file that a writer of the round touched (``--hold``).  Such a file
  states the post-round numbers already, so the sweep must not shift it.
* Read the report before a write run.  Every row must name a line whose text
  moved in this range.
* The ``.pm`` tree stays out of the walk: it is an untracked pack with no commit
  to read a baseline from.

Three citation forms are invisible to this walk, so a write run must also run the
guard ``tests/test_citation_lines.py`` and the modules that read a moved file:

* a bare ``:NNN`` continuation after a ``path:NNN`` in the same sentence;
* a number the text builds, as ``'{0}:375'.format(OWNER)``;
* a line pinned as a bare integer in a list or a dict key.

Usage:
    python3 tools/citation_sweep.py --base <commit> [--hold <path>] [--write]
"""

from __future__ import annotations

import argparse
import datetime
import difflib
import json
import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAMP = os.path.join(ROOT, ".git", "citation-sweep.json")
SKIP_DIRS = {".git", ".venv", "node_modules", "out", "dist", "__pycache__", ".pytest_cache", ".pm"}
SUFFIX = ("py", "js", "md", "sql", "sh", "css", "html", "json")
PATTERN = re.compile(r"([A-Za-z0-9_./\-]+\.(?:" + "|".join(SUFFIX) + r")):(\d+)(?:-(\d+))?")


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout


def split_lines(text: str) -> list[str]:
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def read(relative: str) -> list[str]:
    with open(os.path.join(ROOT, relative), encoding="utf-8", errors="replace") as handle:
        return split_lines(handle.read())


def line_map(old: list[str], new: list[str]) -> dict[int, int]:
    """Map every old line number to its new number where the text still aligns."""
    mapping: dict[int, int] = {}
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if tag == "equal" or (tag == "replace" and (i2 - i1) == (j2 - j1)):
            for step in range(i2 - i1):
                mapping[i1 + step + 1] = j1 + step + 1
    return mapping


def scan_files():
    for base, dirs, names in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in names:
            if name.rsplit(".", 1)[-1] in SUFFIX:
                path = os.path.join(base, name)
                yield os.path.relpath(path, ROOT).replace(os.sep, "/"), path


def collect(base_commit: str, hold: set[str]) -> list[tuple[str, int, str, str]]:
    changed = [l for l in git("diff", "--name-only", base_commit).splitlines() if l.strip()]
    maps: dict[str, dict[int, int]] = {}
    texts: dict[str, tuple[list[str], list[str]]] = {}
    for relative in changed:
        old, new = split_lines(git("show", f"{base_commit}:{relative}")), read(relative)
        maps[relative] = line_map(old, new)
        texts[relative] = (old, new)
    by_name = {os.path.basename(rel): rel for rel in maps}

    def resolve(cited: str) -> str | None:
        if cited in maps:
            return cited
        candidate = by_name.get(os.path.basename(cited))
        if candidate and len(os.path.basename(cited)) == len(os.path.basename(candidate)):
            return candidate
        return None

    def moved_to(target: str, number: int) -> int | None:
        mapping = maps[target]
        new_number = mapping.get(number)
        if new_number is None or new_number == number:
            return None
        old, new = texts[target]
        if number > len(old) or new_number > len(new):
            return None
        if new[new_number - 1].strip() != old[number - 1].strip():
            return None
        return new_number

    def rebuild(token: str, cited: str) -> str | None:
        target = resolve(cited)
        match = PATTERN.fullmatch(token)
        if target is None or match is None:
            return None
        start, end = int(match.group(2)), match.group(3)
        new_start = moved_to(target, start) or start
        if end is None:
            return None if new_start == start else f"{cited}:{new_start}"
        new_end = moved_to(target, int(end)) or int(end)
        return None if (new_start == start and new_end == int(end)) else f"{cited}:{new_start}-{new_end}"

    rows = []
    for relative, path in scan_files():
        if relative in hold:
            continue
        with open(path, encoding="utf-8", errors="replace") as handle:
            for number, line in enumerate(handle, 1):
                for match in PATTERN.finditer(line):
                    rebuilt = rebuild(match.group(0), match.group(1))
                    if rebuilt:
                        rows.append((relative, number, match.group(0), rebuilt))
    return rows


def swept_base() -> str | None:
    try:
        with open(STAMP, encoding="utf-8") as handle:
            return json.load(handle).get("base")
    except (OSError, ValueError):
        return None


def stamp(base: str, files: int, citations: int) -> None:
    payload = {
        "base": base,
        "at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "files": files,
        "citations": citations,
    }
    with open(STAMP, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="commit at the start of the round")
    parser.add_argument("--hold", action="append", default=[], help="file the sweep must not touch")
    parser.add_argument("--write", action="store_true", help="rewrite the citations")
    parser.add_argument("--force", action="store_true", help="sweep a base that a run already swept")
    options = parser.parse_args()

    done = swept_base()
    if done == options.base and not options.force:
        print(f"base {options.base} was already swept (see {STAMP}); nothing to do")
        if not options.write:
            print("a further pass would shift the post-round numbers again")
        return 0

    rows = collect(options.base, set(options.hold))
    print(f"=== payable citations: {len(rows)} ===")
    for relative, number, token, rebuilt in rows:
        print(f"{relative}:{number}  {token} -> {rebuilt}")
    if not options.write:
        return 0

    per_file: dict[str, list[tuple[int, str, str]]] = {}
    for relative, number, token, rebuilt in rows:
        per_file.setdefault(relative, []).append((number, token, rebuilt))
    written = 0
    for relative, items in per_file.items():
        path = os.path.join(ROOT, relative)
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().split("\n")
        for number, token, rebuilt in items:
            before = lines[number - 1]
            lines[number - 1] = before.replace(token, rebuilt)
            if lines[number - 1] != before:
                written += 1
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines))
    stamp(options.base, len(per_file), written)
    print(f"=== citations replaced: {written} in {len(per_file)} files (stamp written) ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
