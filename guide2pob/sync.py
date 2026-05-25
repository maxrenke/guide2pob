"""Sync a directory of PoB XML builds against their source guides.

Each PoB XML produced by guide2pob has the source URL embedded in its
``<Notes>`` block (first or second line). This module scans a builds
directory, re-scrapes every detected guide URL, diffs the result
against the existing XML (ignoring PoB runtime state like
``PlayerStat``/``Buffs``/``TreeView``), and rewrites any that
substantively changed - backing up originals first.

Run via the console entry point:

    guide2pob-sync "C:\\Users\\me\\Documents\\Path of Building (PoE2)\\Builds"

Or as a module:

    python -m guide2pob.sync <dir>
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple


URL_RE = re.compile(
    r'https?://(?:www\.)?(?:mobalytics\.gg/poe-2?/[^\s<>"\']+|'
    r'maxroll\.gg/poe2/[^\s<>"\']+)',
    re.IGNORECASE,
)
NOTES_RE = re.compile(r'<Notes>(.*?)</Notes>', re.DOTALL)
CLASS_RE = re.compile(r'className="([^"]+)"')
ASCEND_RE = re.compile(r'ascendClassName="([^"]+)"')
PATCH_TAG_RE = re.compile(r'(?:\[[^\]]*?|\b)(\d+\.\d+)(?:[^\]]*\]|\b)')

# Lines to ignore when computing whether two XMLs are substantively different.
# These are PoB runtime artifacts that appear after a build is opened in PoB.
NOISE_PATTERNS = [
    re.compile(r'<PlayerStat\b'),
    re.compile(r'<Buffs\b'),
    re.compile(r'<TimelessData\b'),
    re.compile(r'<TreeView\b'),
    re.compile(r'characterLevelAutoMode='),
]


@dataclass
class BuildRecord:
    path: str
    url: Optional[str]
    klass: Optional[str]
    ascend: Optional[str]
    title: Optional[str]
    patch_tag: Optional[str]


@dataclass
class SyncResult:
    record: BuildRecord
    status: str  # "updated", "unchanged", "skipped", "error"
    reason: str = ""
    diff_lines: int = 0
    backup_path: Optional[str] = None


def extract_record(xml_path: str) -> BuildRecord:
    """Pull source URL, class, ascendancy, and patch tag from an XML."""
    text = _read(xml_path)
    notes_match = NOTES_RE.search(text)
    notes = notes_match.group(1) if notes_match else ""
    url_match = URL_RE.search(notes) or URL_RE.search(text)
    url = url_match.group(0) if url_match else None
    # The first non-blank line of the notes is conventionally the title.
    title = None
    for line in notes.splitlines():
        line = line.strip()
        if line and not line.startswith("http"):
            title = line
            break
    patch_tag = None
    # Search title first, then fall back to scanning the notes body for any
    # X.Y patch number reference (Maxroll guides put "Return of the Ancients
    # 0.5.0" or "patch 0.5" in section headers rather than the title).
    for hay in (title, notes):
        if not hay:
            continue
        m = PATCH_TAG_RE.search(hay)
        if m:
            patch_tag = m.group(1)
            break
    klass_match = CLASS_RE.search(text)
    ascend_match = ASCEND_RE.search(text)
    return BuildRecord(
        path=xml_path,
        url=url,
        klass=klass_match.group(1) if klass_match else None,
        ascend=ascend_match.group(1) if ascend_match else None,
        title=title,
        patch_tag=patch_tag,
    )


def normalize(text: str) -> List[str]:
    """Strip PoB runtime noise and blanks for comparison."""
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if any(p.search(s) for p in NOISE_PATTERNS):
            continue
        out.append(s)
    return out


def scrape(url: str, out_path: str, klass: Optional[str],
           ascend: Optional[str], extra_args: Iterable[str] = ()) -> Tuple[bool, str]:
    """Invoke guide2pob to rescrape ``url`` to ``out_path``. Returns (ok, msg)."""
    cmd = [
        sys.executable, "-m", "guide2pob", url,
        "--xml", "-o", out_path,
        "--no-open", "--no-save-pob", "--merge",
    ]
    if klass and klass.lower() not in ("none", ""):
        cmd += ["--class", klass]
    if ascend and ascend.lower() not in ("none", ""):
        cmd += ["--ascendancy", ascend]
    cmd += list(extra_args)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except FileNotFoundError as e:
        return False, f"{e}"
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "").strip().splitlines()
        return False, msg[-1] if msg else f"exit {proc.returncode}"
    return True, ""


def sync_dir(builds_dir: str, *, dry_run: bool = False,
             backup: bool = True, only: Optional[Iterable[str]] = None) -> List[SyncResult]:
    """Re-scrape and update every PoB XML in ``builds_dir``."""
    only_set = {os.path.basename(p) for p in only} if only else None
    xmls = sorted(
        os.path.join(builds_dir, n)
        for n in os.listdir(builds_dir)
        if n.lower().endswith(".xml") and not n.startswith("_")
        and (only_set is None or n in only_set)
    )
    if not xmls:
        return []

    backup_dir = None
    if backup and not dry_run:
        stamp = _dt.date.today().strftime("%Y%m%d")
        backup_dir = os.path.join(builds_dir, f"_backup_{stamp}")
        os.makedirs(backup_dir, exist_ok=True)

    results: List[SyncResult] = []
    with tempfile.TemporaryDirectory(prefix="guide2pob_sync_") as tmp:
        for xml in xmls:
            rec = extract_record(xml)
            if not rec.url:
                results.append(SyncResult(rec, "skipped", "no source URL in notes"))
                continue
            fresh = os.path.join(tmp, os.path.basename(xml))
            ok, msg = scrape(rec.url, fresh, rec.klass, rec.ascend)
            if not ok:
                results.append(SyncResult(rec, "error", msg))
                continue
            cur_lines = normalize(_read(xml))
            new_lines = normalize(_read(fresh))
            diff = _diff_count(cur_lines, new_lines)
            if diff == 0:
                results.append(SyncResult(rec, "unchanged", "", 0))
                continue
            backup_path = None
            if not dry_run:
                if backup_dir:
                    backup_path = os.path.join(backup_dir, os.path.basename(xml))
                    shutil.copy2(xml, backup_path)
                shutil.copy2(fresh, xml)
            results.append(SyncResult(rec, "updated", "", diff, backup_path))
    return results


def _diff_count(a: List[str], b: List[str]) -> int:
    """Count of lines that differ between two normalized line lists."""
    sa = {(i, line) for i, line in enumerate(a)}
    sb = {(i, line) for i, line in enumerate(b)}
    # Order-aware cheap diff: compare line-by-line up to max length.
    n = max(len(a), len(b))
    diff = 0
    for i in range(n):
        la = a[i] if i < len(a) else None
        lb = b[i] if i < len(b) else None
        if la != lb:
            diff += 1
    return diff


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def render_report(results: List[SyncResult], target_patch: str = "0.5") -> str:
    """Human-readable summary including patch audit hints."""
    if not results:
        return "no builds found"
    rows = []
    rows.append(("FILE", "STATUS", "DIFF", "CLASS/ASCEND", "PATCH", "TITLE"))
    for r in results:
        rec = r.record
        rows.append((
            os.path.basename(rec.path),
            r.status + (f" ({r.reason})" if r.reason else ""),
            str(r.diff_lines) if r.status in ("updated", "unchanged") else "",
            f"{rec.klass or '?'}/{rec.ascend or '?'}",
            rec.patch_tag or "?",
            (rec.title or "")[:60],
        ))
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    lines = []
    for row in rows:
        lines.append("  ".join(c.ljust(widths[i]) for i, c in enumerate(row)))
    # Audit section
    target = target_patch
    off_patch = [r for r in results
                 if r.record.patch_tag and r.record.patch_tag != target]
    no_tag = [r for r in results if not r.record.patch_tag]
    lines.append("")
    lines.append(f"audit (target patch {target}):")
    if off_patch:
        for r in off_patch:
            lines.append(f"  off-patch: {os.path.basename(r.record.path)} "
                         f"(tagged {r.record.patch_tag})")
    if no_tag:
        for r in no_tag:
            lines.append(f"  no patch tag: {os.path.basename(r.record.path)}")
    if not off_patch and not no_tag:
        lines.append("  all builds tagged for target patch")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="guide2pob-sync",
        description="Refresh a directory of guide2pob-produced PoB XMLs from "
                    "their source URLs, and audit them against a target patch.",
    )
    p.add_argument("builds_dir", nargs="?",
                   help="Path of Building Builds directory. "
                        "Defaults to the auto-detected PoB2 install.")
    p.add_argument("--dry-run", action="store_true",
                   help="Report changes without writing.")
    p.add_argument("--no-backup", action="store_true",
                   help="Skip copying originals to _backup_YYYYMMDD/.")
    p.add_argument("--only", action="append", default=None,
                   help="Only process the given filename. Repeatable.")
    p.add_argument("--target-patch", default="0.5",
                   help="Patch tag to audit against (default: 0.5).")
    args = p.parse_args(argv)

    builds_dir = args.builds_dir
    if not builds_dir:
        try:
            from .pobdata import find_builds_dir
            builds_dir = find_builds_dir()
        except Exception:
            builds_dir = None
    if not builds_dir or not os.path.isdir(builds_dir):
        p.error("builds_dir not provided and could not be auto-detected")

    results = sync_dir(builds_dir, dry_run=args.dry_run,
                       backup=not args.no_backup, only=args.only)
    print(render_report(results, target_patch=args.target_patch))
    errored = sum(1 for r in results if r.status == "error")
    return 1 if errored else 0


if __name__ == "__main__":
    sys.exit(main())
