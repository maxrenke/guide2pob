"""Command-line interface for moba2pob."""
import os
import sys
import re
import json
import zlib
import base64
import argparse
import subprocess
import urllib.request

from . import __version__
from .scrape import (
    load_build, build_variants, variant_labels, slug_from_url, ScrapeError,
    build_description, guide_text)
from .convert import convert, convert_merged
from .convert_poe1 import (
    convert as convert_poe1,
    convert_merged as convert_merged_poe1,
)
from .pobdata import find_install, find_builds_dir, find_exe, PoBData
from .upload import upload_pobbin, UploadError


def _class_from_pobcode(doc):
    """Try to extract the ascendancy name from a doc-level pobCode.

    Returns the ascendancy string (e.g. 'Amazon') or None on failure.
    The pobCode may be a raw base64+zlib blob or a pobb.in URL.
    """
    code = (doc or {}).get('pobCode') or ''
    if not code:
        return None
    try:
        # If it's a pobb.in URL, fetch the actual code first.
        if code.startswith('http'):
            m = re.search(r'pobb\.in/([A-Za-z0-9_-]+)$', code.strip())
            if not m:
                return None
            req = urllib.request.Request(
                f'https://pobb.in/pob/{m.group(1)}',
                headers={'User-Agent': 'moba2pob'})
            code = urllib.request.urlopen(req, timeout=10).read().decode().strip()
        std = code.replace('-', '+').replace('_', '/')
        xml = zlib.decompress(base64.b64decode(std + '==')).decode()
        m = re.search(r'ascendClassName="([^"]+)"', xml)
        return m.group(1) if m and m.group(1) not in ('None', '') else None
    except Exception:  # noqa: BLE001
        return None


def _detect_game(source):
    """Return 'poe1' or 'poe2' based on the URL path."""
    if '/poe-2/' in source or '/poe2/' in source:
        return 'poe2'
    if '/poe/' in source and '/poe2' not in source and '/poe-2' not in source:
        return 'poe1'
    return 'poe2'  # default for local files and unknown URLs


def _build_parser():
    p = argparse.ArgumentParser(
        prog='moba2pob',
        description='Convert a Mobalytics PoE build guide into a '
                    'Path of Building import code.')
    p.add_argument('source', nargs='+',
                   help='one or more Mobalytics build URLs or local .html/.json files')
    p.add_argument('--game', choices=['poe1', 'poe2'],
                   help='game version (default: auto-detected from URL)')
    p.add_argument('--variant', default='all',
                   help="variant index to convert, or 'all' (default: all); "
                        "for PoE1 pass a specific index to skip the embedded pobCode")
    p.add_argument('--merge', action='store_true', default=True,
                   help='merge all variants into one build with switchable '
                        'Tree specs, Item Sets, and Skill Sets (default: on)')
    p.add_argument('--no-merge', dest='merge', action='store_false',
                   help='disable merge; convert each variant separately')
    p.add_argument('--no-reorder', action='store_true',
                   help='keep Mobalytics variant order instead of sorting '
                        'by progression (leveling -> endgame)')
    _downloads = os.path.join(os.path.expanduser('~'), 'Downloads')
    p.add_argument('-o', '--out', default=_downloads,
                   help='output file (single variant) or directory (all) '
                        '(default: ~/Downloads)')
    p.add_argument('--xml', action='store_true',
                   help='also write the raw build XML')
    p.add_argument('--save-pob', action='store_true', default=True,
                   help='save build XML to Path of Building builds directory (default: on)')
    p.add_argument('--no-save-pob', dest='save_pob', action='store_false',
                   help='skip saving to Path of Building builds directory')
    p.add_argument('--upload', action='store_true',
                   help='upload to pobb.in and print a shareable link')
    p.add_argument('-p', '--print-code', action='store_true',
                   help='print the import code to stdout even when -o is set')
    p.add_argument('--open', action='store_true', default=True,
                   help='upload to pobb.in and open the build in Path of Building '
                        '(default: on)')
    p.add_argument('--no-open', dest='open', action='store_false',
                   help='disable auto-open in Path of Building')
    p.add_argument('--json', action='store_true',
                   help='dump the scraped build data as JSON and exit')
    p.add_argument('--class', dest='cls', metavar='NAME',
                   help='override the detected class')
    p.add_argument('--ascendancy', metavar='NAME',
                   help='override the detected ascendancy')
    p.add_argument('--level', type=int, default=90,
                   help='character level to record (default: 90)')
    p.add_argument('--pob-path', metavar='DIR',
                   help='Path of Building install directory')
    p.add_argument('--no-pob', action='store_true',
                   help='ignore any Path of Building install')
    p.add_argument('--version', action='version',
                   version=f'moba2pob {__version__}')
    return p


def _load_pob(args):
    if args.no_pob:
        return None
    install = find_install(args.pob_path)
    if not install:
        print('note: no Path of Building (PoE2) install found - gem names '
              'will be approximate and class detection needs --ascendancy',
              file=sys.stderr)
        return None
    print(f'using Path of Building data: {install}', file=sys.stderr)
    if args.save_pob:
        builds_dir = find_builds_dir()
        if builds_dir:
            args._pob_builds_dir = builds_dir
    exe = find_exe(install)
    if exe:
        args._pob_exe = exe
    return PoBData(install)


def _make_notes(name, source, labels, description=None, html=None):
    """Build the base Notes string: URL, description, guide text, variant list."""
    parts = []

    # Header: build name + source URL
    header = [name, source]
    parts.append('\n'.join(header))

    # Short description from og:description (skip if it just restates the name)
    if description and description.lower() != name.lower():
        parts.append(description)

    # Full guide text extracted from Lexical rich-text blocks in the page HTML
    gt = guide_text(html) if html else ''
    if gt:
        parts.append(gt)

    # Variant index -> label map
    if any(labels):
        lines = ['Variants:']
        for i, lbl in enumerate(labels):
            lines.append(f'  {i}: {lbl or "Variant " + str(i)}')
        parts.append('\n'.join(lines))

    return '\n\n'.join(parts)


# -- PoE2 helpers -----------------------------------------------------------

def _convert_one_poe2(variant, idx, args, pob, labels, notes=None):
    title = labels[idx] if idx < len(labels) else None
    meta = convert(variant, pob=pob, class_override=args.cls,
                   ascendancy_override=args.ascendancy, level=args.level,
                   title=title, notes=notes)
    detected = ' (detected)' if meta['detected_ascendancy'] else ''
    label = f' "{title}"' if title else ''
    print(f"# variant {idx}{label}: {meta['class']} / {meta['ascendancy']}{detected}  "
          f"- {meta['node_count']} nodes, {meta['skill_count']} skill groups, "
          f"tree {meta['tree_version']}", file=sys.stderr)
    return meta


def _run_poe2(doc, html, args, slug):
    variants = build_variants(doc)
    labels = variant_labels(html, variants)
    name = doc.get('name', 'build')
    notes = _make_notes(name, args.source, labels,
                        description=build_description(html), html=html)
    pob = _load_pob(args)

    if args.merge:
        return _run_merge_poe2(variants, slug, args, pob, labels, notes, doc=doc)

    variant_arg = args.variant if args.variant is not None else '0'
    if variant_arg == 'all':
        indices = list(range(len(variants)))
    else:
        try:
            indices = [int(variant_arg)]
        except ValueError:
            print(f'error: bad --variant {variant_arg!r}', file=sys.stderr)
            return 2
        if not 0 <= indices[0] < len(variants):
            print(f'error: variant {indices[0]} out of range '
                  f'(0..{len(variants) - 1})', file=sys.stderr)
            return 2

    out_dir = args.out if (args.out and len(indices) > 1) else None
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    rc = 0
    for idx in indices:
        try:
            meta = _convert_one_poe2(variants[idx], idx, args, pob, labels,
                                     notes=notes)
        except ValueError as e:
            print(f'error: variant {idx}: {e}', file=sys.stderr)
            rc = 1
            continue

        _output(meta, slug, idx, args, out_dir, game='poe2')

    return rc


def _run_merge_poe2(variants, slug, args, pob, labels, notes=None, doc=None):
    titles = [labels[i] or f'Variant {i}' for i in range(len(variants))]
    asc_override = args.ascendancy
    cls_override = args.cls
    # If class can't be detected from any variant's tree, fall back to the
    # doc-level pobCode (some builds have null ascendancy trees).
    if not asc_override and not cls_override:
        asc_override = _class_from_pobcode(doc) if doc else None
        if asc_override:
            print(f'note: class detected from pobCode: {asc_override}',
                  file=sys.stderr)
    try:
        meta = convert_merged(variants, pob=pob, class_override=cls_override,
                              ascendancy_override=asc_override,
                              level=args.level, titles=titles,
                              notes=notes,
                              progression_order=not args.no_reorder)
    except ValueError as e:
        print(f'error: {e}', file=sys.stderr)
        return 1
    print(f"# merged: {meta['class']} / {meta['ascendancy']}  "
          f"- {meta['variant_count']} variants, tree {meta['tree_version']}",
          file=sys.stderr)
    _output(meta, slug, None, args, None, game='poe2')
    return 0


# -- PoE1 helpers -----------------------------------------------------------

def _run_poe1(doc, html, args, slug):
    variants = build_variants(doc)
    labels = variant_labels(html, variants)
    name = doc.get('name', 'build')
    notes = _make_notes(name, args.source, labels,
                        description=build_description(html), html=html)

    if args.merge:
        return _run_merge_poe1(doc, slug, args, labels, notes)

    # For PoE1, omitting --variant uses the embedded pobCode (best quality).
    if args.variant is None:
        try:
            meta = convert_poe1(doc, variant_idx=None, notes=notes,
                                 level=args.level,
                                 class_override=args.cls,
                                 ascendancy_override=args.ascendancy)
        except Exception as e:
            print(f'error: {e}', file=sys.stderr)
            return 1
        print(f"# pobCode: {meta['class']} / {meta['ascendancy']}",
              file=sys.stderr)
        _output(meta, slug, None, args, None, game='poe1')
        return 0

    if args.variant == 'all':
        indices = list(range(len(variants)))
    else:
        try:
            indices = [int(args.variant)]
        except ValueError:
            print(f'error: bad --variant {args.variant!r}', file=sys.stderr)
            return 2
        if not 0 <= indices[0] < len(variants):
            print(f'error: variant {indices[0]} out of range '
                  f'(0..{len(variants) - 1})', file=sys.stderr)
            return 2

    out_dir = args.out if (args.out and len(indices) > 1) else None
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    rc = 0
    for idx in indices:
        label = labels[idx] if idx < len(labels) else None
        try:
            meta = convert_poe1(doc, variant_idx=idx, notes=notes,
                                 level=args.level,
                                 class_override=args.cls,
                                 ascendancy_override=args.ascendancy)
        except ValueError as e:
            print(f'error: variant {idx}: {e}', file=sys.stderr)
            rc = 1
            continue
        label_str = f' "{label}"' if label else ''
        print(f"# variant {idx}{label_str}: {meta['class']} / {meta['ascendancy']}  "
              f"- {meta.get('node_count', '?')} nodes",
              file=sys.stderr)
        _output(meta, slug, idx, args, out_dir, game='poe1')

    return rc


def _run_merge_poe1(doc, slug, args, labels, notes=None):
    variants = build_variants(doc)
    titles = [labels[i] or f'Variant {i}' for i in range(len(variants))]
    try:
        meta = convert_merged_poe1(doc, notes=notes, level=args.level,
                                   class_override=args.cls,
                                   ascendancy_override=args.ascendancy,
                                   titles=titles,
                                   progression_order=not args.no_reorder)
    except ValueError as e:
        print(f'error: {e}', file=sys.stderr)
        return 1
    print(f"# merged: {meta['class']} / {meta['ascendancy']}  "
          f"- {meta['variant_count']} variants",
          file=sys.stderr)
    _output(meta, slug, None, args, None, game='poe1')
    return 0


# -- shared output ----------------------------------------------------------

def _output(meta, slug, idx, args, out_dir, game='poe2'):
    # Treat -o <dir> the same as out_dir when the path is/looks like a directory.
    effective_dir = out_dir
    effective_file = args.out if args.out else None
    if effective_file and not effective_dir:
        if os.path.isdir(effective_file) or effective_file.endswith(('/', '\\')):
            effective_dir = effective_file
            effective_file = None

    if effective_dir:
        os.makedirs(effective_dir, exist_ok=True)
        suffix = f'-v{idx}' if idx is not None else ''
        base = os.path.join(effective_dir, f'{slug}{suffix}')
        _write(base + '.txt', meta['code'])
        if args.xml:
            _write(base + '.xml', meta['xml'])
        print(f'wrote {base}.txt', file=sys.stderr)
    elif effective_file:
        _write(effective_file, meta['code'])
        if args.xml:
            _write(os.path.splitext(effective_file)[0] + '.xml', meta['xml'])
        print(f'wrote {effective_file}', file=sys.stderr)
    if args.print_code or (not effective_file and not effective_dir):
        print(meta['code'])
    saved_path = None
    if getattr(args, '_pob_builds_dir', None) and args.save_pob:
        suffix = f'-v{idx}' if idx is not None else ''
        saved_path = os.path.join(args._pob_builds_dir, f'{slug}{suffix}.xml')
        _write(saved_path, meta['xml'])
        print(f'saved  {saved_path}', file=sys.stderr)
    if args.upload or args.open:
        if args.open and saved_path and getattr(args, '_pob_exe', None):
            # Signal main() to launch PoB2 once after all sources are done.
            args._should_open_pob2 = True
        else:
            _print_pobbin(meta['code'], open_in_pob=args.open, game=game)


def _print_pobbin(code, open_in_pob=False, game='poe2'):
    try:
        info = upload_pobbin(code)
    except UploadError as e:
        print(f'pobb.in upload failed: {e}', file=sys.stderr)
        return
    print(f"pobb.in:  {info['url']}")
    proto_url = info.get('pob2_url', '')
    if game == 'poe1':
        # PoE1 uses pob:// (not pob2://)
        proto_url = f"pob://pobbin/{info['id']}"
    print(f"open PoB: {proto_url}")
    if open_in_pob:
        _open_url(proto_url)


def _open_pob2(exe_path):
    """Launch the PoB2 executable (build appears in the saved list)."""
    try:
        if sys.platform == 'win32':
            os.startfile(exe_path)  # noqa: S606
        elif sys.platform == 'darwin':
            subprocess.run(['open', exe_path], check=False)
        else:
            subprocess.Popen([exe_path])
    except OSError as e:
        print(f'could not launch {exe_path}: {e}', file=sys.stderr)


def _open_url(url):
    """Open a URL via the OS handler."""
    try:
        if sys.platform == 'win32':
            os.startfile(url)  # noqa: S606
        elif sys.platform == 'darwin':
            subprocess.run(['open', url], check=False)
        else:
            subprocess.run(['xdg-open', url], check=False)
    except OSError as e:
        print(f'could not open {url}: {e}', file=sys.stderr)


def _write(path, text):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def _process_one(source, args):
    """Process a single source URL/file. Returns an exit code (0=ok, 1=err, 2=fatal)."""
    args.source = source  # make source available to helpers that read args.source
    try:
        doc, html = load_build(source)
    except ScrapeError as e:
        print(f'error: {e}', file=sys.stderr)
        return 2

    variants = build_variants(doc)
    if not variants:
        print('error: build has no variants', file=sys.stderr)
        return 2

    if args.json:
        json.dump(doc, sys.stdout, indent=1)
        return 0

    name = doc.get('name', 'build')
    n = len(variants)
    print(f'build: {name}  ({n} variant{"s" if n != 1 else ""})',
          file=sys.stderr)

    game = args.game or _detect_game(source)
    print(f'game:  PoE{"1" if game == "poe1" else "2"}', file=sys.stderr)

    slug = slug_from_url(source) or 'build'

    if game == 'poe1':
        return _run_poe1(doc, html, args, slug)
    return _run_poe2(doc, html, args, slug)


def main(argv=None):
    args = _build_parser().parse_args(argv)

    rc = 0
    for source in args.source:
        if len(args.source) > 1:
            print(f'\n--- {source} ---', file=sys.stderr)
        result = _process_one(source, args)
        if result and result > rc:
            rc = result
    if getattr(args, '_should_open_pob2', False):
        print('opening Path of Building...', file=sys.stderr)
        _open_pob2(args._pob_exe)
    return rc


if __name__ == '__main__':
    sys.exit(main())
