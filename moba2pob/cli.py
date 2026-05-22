"""Command-line interface for moba2pob."""
import os
import sys
import json
import argparse

from . import __version__
from .scrape import load_build, build_variants, slug_from_url, ScrapeError
from .convert import convert, convert_merged
from .pobdata import find_install, PoBData
from .analyze import summarize, analyze, AnalysisError


def _build_parser():
    p = argparse.ArgumentParser(
        prog='moba2pob',
        description='Convert a Mobalytics PoE2 build guide into a '
                    'Path of Building import code.')
    p.add_argument('source',
                   help='Mobalytics build URL, or a local .html/.json file')
    p.add_argument('--variant', default='0',
                   help="variant index to convert, or 'all' (default: 0)")
    p.add_argument('--merge', action='store_true',
                   help='merge all variants into one build with switchable '
                        'Tree specs, Item Sets, and Skill Sets')
    p.add_argument('-o', '--out',
                   help='output file (single variant) or directory (all)')
    p.add_argument('--xml', action='store_true',
                   help='also write the raw build XML')
    p.add_argument('--json', action='store_true',
                   help='dump the scraped build data as JSON and exit')
    p.add_argument('--class', dest='cls', metavar='NAME',
                   help='override the detected class')
    p.add_argument('--ascendancy', metavar='NAME',
                   help='override the detected ascendancy')
    p.add_argument('--level', type=int, default=90,
                   help='character level to record (default: 90)')
    p.add_argument('--pob-path', metavar='DIR',
                   help='Path of Building (PoE2) install directory')
    p.add_argument('--no-pob', action='store_true',
                   help='ignore any Path of Building install')
    p.add_argument('--analyze', action='store_true',
                   help='run an LLM analysis of the build')
    p.add_argument('--provider', default='anthropic',
                   choices=['anthropic', 'ollama', 'none'],
                   help='LLM provider for --analyze (default: anthropic)')
    p.add_argument('--model', help='LLM model name')
    p.add_argument('--api-key', help='API key (else uses ANTHROPIC_API_KEY)')
    p.add_argument('--ollama-url', help='Ollama base URL')
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


def _convert_one(variant, idx, args, pob):
    meta = convert(variant, pob=pob, class_override=args.cls,
                   ascendancy_override=args.ascendancy, level=args.level)
    detected = ' (detected)' if meta['detected_ascendancy'] else ''
    print(f"# variant {idx}: {meta['class']} / {meta['ascendancy']}{detected}  "
          f"- {meta['node_count']} nodes, {meta['skill_count']} skill groups, "
          f"tree {meta['tree_version']}", file=sys.stderr)
    return meta


def main(argv=None):
    args = _build_parser().parse_args(argv)

    try:
        doc = load_build(args.source)
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
    print(f'build: {name}  ({len(variants)} variant'
          f'{"s" if len(variants) != 1 else ""})', file=sys.stderr)

    pob = _load_pob(args)
    slug = slug_from_url(args.source) or 'build'

    if args.merge:
        return _run_merge(variants, slug, args, pob)

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
        try:
            meta = _convert_one(variants[idx], idx, args, pob)
        except ValueError as e:
            print(f'error: variant {idx}: {e}', file=sys.stderr)
            rc = 1
            continue

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
        else:
            print(meta['code'])

        if args.analyze:
            _run_analysis(variants[idx], meta, pob, args)

    return rc


def _run_merge(variants, slug, args, pob):
    titles = [f'Variant {i} ({len(v.get("passiveTree", {}).get("mainTree", {}).get("selectedSlugs", []))}n)'
              for i, v in enumerate(variants)]
    try:
        meta = convert_merged(variants, pob=pob, class_override=args.cls,
                              ascendancy_override=args.ascendancy,
                              level=args.level, titles=titles)
    except ValueError as e:
        print(f'error: {e}', file=sys.stderr)
        return 1
    print(f"# merged: {meta['class']} / {meta['ascendancy']}  "
          f"- {meta['variant_count']} variants, tree {meta['tree_version']}",
          file=sys.stderr)

    if args.out:
        _write(args.out, meta['code'])
        if args.xml:
            _write(os.path.splitext(args.out)[0] + '.xml', meta['xml'])
        print(f'wrote {args.out}', file=sys.stderr)
    else:
        print(meta['code'])
    return 0


def _run_analysis(variant, meta, pob, args):
    summary = summarize(variant, meta, pob)
    try:
        result = analyze(summary, provider=args.provider, model=args.model,
                         api_key=args.api_key, base_url=args.ollama_url)
    except AnalysisError as e:
        print(f'analysis skipped: {e}', file=sys.stderr)
        return
    if result:
        print('\n--- build analysis ---', file=sys.stderr)
        print(result, file=sys.stderr)


def _write(path, text):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


if __name__ == '__main__':
    sys.exit(main())
