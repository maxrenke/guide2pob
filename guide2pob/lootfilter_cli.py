"""CLI: generate a build-customized PoE2 loot filter from a NeverSink base zip."""
import argparse
import sys

from . import __version__
from .lootfilter import ARCHETYPES, STRICTNESS_LABEL, generate


def _build_parser():
    p = argparse.ArgumentParser(
        prog='guide2pob-filter',
        description='Customize a NeverSink/FilterBlade PoE2 loot filter for a '
                    'specific build: install base filters from a zip and inject '
                    'build-specific highlight rules.')
    p.add_argument('--zip', metavar='ZIP',
                   help='NeverSink base-filter zip to install (omit to reuse '
                        'already-installed base filters)')
    p.add_argument('--build', metavar='NAME|PATH',
                   help='PoB2 build XML path, or a name substring to find in the '
                        'Path of Building (PoE2) Builds directory')
    p.add_argument('--name', help='output build name (default: from --build)')
    p.add_argument('--archetype', choices=sorted(ARCHETYPES),
                   help='override the auto-detected archetype')
    p.add_argument('--strictness', type=int, default=3, choices=range(0, 7),
                   metavar='0-6',
                   help='base strictness to customize (default: 3=Strict)')
    p.add_argument('--filter-dir', metavar='DIR',
                   help="PoE2 filter directory (default: auto-detected)")
    p.add_argument('--builds-dir', metavar='DIR',
                   help='Path of Building (PoE2) Builds directory (for --build '
                        'name lookup; default: auto-detected)')
    p.add_argument('--version', action='version', version=f'guide2pob {__version__}')
    return p


def main(argv=None):
    args = _build_parser().parse_args(argv)
    try:
        r = generate(zip_path=args.zip, build=args.build, name=args.name,
                     archetype=args.archetype, strictness=args.strictness,
                     filter_dir=args.filter_dir, builds_dir=args.builds_dir)
    except (FileNotFoundError, ValueError) as e:
        print(f'error: {e}', file=sys.stderr)
        return 1

    if r['build_name']:
        print(f'build:     {r["build_name"]}  '
              f'({r["class"]}/{r["ascendancy"]})', file=sys.stderr)
    print(f'archetype: {r["archetype"]}', file=sys.stderr)
    if r['backed_up']:
        print(f'backed up: {len(r["backed_up"])} old filter(s) -> _old_filters_*/',
              file=sys.stderr)
    if args.zip:
        print(f'installed: {len(r["installed"])} base filter(s)', file=sys.stderr)
    import os
    print(f'base:      {os.path.basename(r["base"])}', file=sys.stderr)
    print(f'output:    {os.path.basename(r["output"])}')
    print('Select it in-game: Options -> UI -> filter dropdown.', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
