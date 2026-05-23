"""Command-line interface for moba2pob."""
import os
import sys
import json
import argparse
import subprocess

from . import __version__
from .scrape import (
    load_build, build_variants, variant_labels, slug_from_url, ScrapeError)
from .convert import convert, convert_merged
from .convert_poe1 import (
    convert as convert_poe1,
    convert_merged as convert_merged_poe1,
)
from .pobdata import find_install, PoBData
from .upload import upload_pobbin, UploadError


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
    p.add_argument('source',
                   help='Mobalytics build URL, or a local .html/.json file')
    p.add_argument('--game', choices=['poe1', 'poe2'],
                   help='game version (default: auto-detected from URL)')
    p.add_argument('--variant', default=None,
                   help="variant index to convert, or 'all'; "
                        "for PoE1 omit to use the embedded pobCode (best quality)")
    p.add_argument('--merge', action='store_true',
                   help='merge all variants into one build with switchable '
                        'Tree specs, Item Sets, and Skill Sets')
    p.add_argument('--no-reorder', action='store_true',
                   help='keep Mobalytics variant order instead of sorting '
                        'by progression (leveling -> endgame)')
    p.add_argument('-o', '--out',
                   help='output file (single variant) or directory (all)')
    p.add_argument('--xml', action='store_true',
                   help='also write the raw build XML')
    p.add_argument('--upload', action='store_true',
                   help='upload to pobb.in and print a shareable link')
    p.add_argument('-p', '--print-code', action='store_true',
                   help='print the import code to stdout even when -o is set')
    p.add_argument('--open', action='store_true',
                   help='after --upload, launch the pob:// or pob2:// link '
                        'to open the build directly in Path of Building')
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
    return PoBData(install)


def _make_notes(name, source, labels):
    lines = [name, source, '']
    if any(labels):
        lines.append('Variants:')
        for i, lbl in enumerate(labels):
            lines.append(f'  {i}: {lbl or "Variant " + str(i)}')
    return '\n'.join(lines)


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
    notes = _make_notes(name, args.source, labels)
    pob = _load_pob(args)

    if args.merge:
        return _run_merge_poe2(variants, slug, args, pob, labels, notes)

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


def _run_merge_poe2(variants, slug, args, pob, labels, notes=None):
    titles = [labels[i] or f'Variant {i}' for i in range(len(variants))]
    try:
        meta = convert_merged(variants, pob=pob, class_override=args.cls,
                              ascendancy_override=args.ascendancy,
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
    notes = _make_notes(name, args.source, labels)

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
    if out_dir:
        base = os.path.join(out_dir, f'{slug}-v{idx}')
        _write(base + '.txt', meta['code'])
        if args.xml:
            _write(base + '.xml', meta['xml'])
        print(f'wrote {base}.txt', file=sys.stderr)
    elif args.out:
        _write(args.out, meta['code'])
        if args.xml:
            _write(os.path.splitext(args.out)[0] + '.xml', meta['xml'])
        print(f'wrote {args.out}', file=sys.stderr)
    if args.print_code or (not args.out and not out_dir):
        print(meta['code'])
    if args.upload:
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


def main(argv=None):
    args = _build_parser().parse_args(argv)

    try:
        doc, html = load_build(args.source)
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

    game = args.game or _detect_game(args.source)
    print(f'game:  PoE{"1" if game == "poe1" else "2"}', file=sys.stderr)

    slug = slug_from_url(args.source) or 'build'

    if game == 'poe1':
        return _run_poe1(doc, html, args, slug)
    return _run_poe2(doc, html, args, slug)


if __name__ == '__main__':
    sys.exit(main())
