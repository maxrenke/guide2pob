"""CLI: walk a PoB2 Builds folder and emit .build files into PoE2's
BuildPlanner directory so they show up in-game.
"""
import os
import sys
import argparse

from . import __version__
from .buildfile import (
    parse_pob_xml, parse_pob_progression, build_dotbuild, load_tree_export,
    build_node_id_map, find_buildplanner_dir, write_buildfile, safe_filename)
from .pobdata import find_install, find_builds_dir, PoBData


def _extract_source_url(notes):
    if not notes:
        return None
    for line in notes.splitlines():
        s = line.strip()
        if s.startswith('http://') or s.startswith('https://'):
            return s
    return None


def _build_parser():
    p = argparse.ArgumentParser(
        prog='guide2pob-buildfile',
        description='Generate PoE2 in-game .build files from Path of Building 2 '
                    'build XMLs and drop them in the BuildPlanner directory.')
    p.add_argument('builds_dir', nargs='?',
                   help='Path of Building (PoE2) Builds directory '
                        '(default: auto-detected)')
    p.add_argument('-o', '--out', metavar='DIR',
                   help='destination directory (default: '
                        '~/Documents/My Games/Path of Exile 2/Preferences/BuildPlanner)')
    p.add_argument('--prefer', choices=['largest', 'active'], default='largest',
                   help='which variant to export when a build has several '
                        "(default: 'largest' = the spec with the most passives)")
    p.add_argument('--pob-path', help='Path of Building (PoE2) install dir '
                                       '(for gem id resolution)')
    p.add_argument('--refresh-tree', action='store_true',
                   help='re-download the GGG passive-tree export')
    p.add_argument('--dry-run', action='store_true',
                   help='report what would be written without touching disk')
    p.add_argument('-v', '--verbose', action='store_true')
    p.add_argument('--version', action='version',
                   version=f'guide2pob {__version__}')
    return p


def _process_one(xml_path, *, node_id_map, pob, out_dir, prefer, dry_run,
                  verbose):
    try:
        xml = open(xml_path, encoding='utf-8').read()
    except OSError as e:
        print(f'skip {xml_path}: {e}', file=sys.stderr)
        return None

    try:
        # 'largest' (default) also derives per-gem/-item level intervals from
        # the build's act-staged variants; 'active' is a single-variant snapshot.
        parsed = (parse_pob_progression(xml) if prefer == 'largest'
                  else parse_pob_xml(xml, prefer=prefer))
    except Exception as e:  # noqa: BLE001
        print(f'skip {xml_path}: parse failed: {e}', file=sys.stderr)
        return None

    if not parsed['node_ids'] and not parsed['skill_groups']:
        if verbose:
            print(f'skip {xml_path}: no nodes or skills', file=sys.stderr)
        return None

    base = os.path.splitext(os.path.basename(xml_path))[0]
    src = _extract_source_url(parsed.get('notes'))
    doc = build_dotbuild(parsed, pob=pob, node_id_map=node_id_map,
                         name=base, source_url=src)

    matched = sum(1 for nid in parsed['node_ids']
                  if nid in node_id_map)
    total_nodes = len(parsed['node_ids'])
    n_skills = len(doc.get('skills') or [])
    n_inv = len(doc.get('inventory_slots') or [])

    filename = safe_filename(base) + '.build'
    out_path = os.path.join(out_dir, filename)
    if dry_run:
        print(f'  would write {filename}  '
              f'({matched}/{total_nodes} nodes, {n_skills} skills, {n_inv} slots)')
        return out_path

    write_buildfile(doc, out_dir, filename)
    print(f'  {filename}  '
          f'({matched}/{total_nodes} nodes, {n_skills} skills, {n_inv} slots)')
    return out_path


def main(argv=None):
    args = _build_parser().parse_args(argv)

    builds_dir = args.builds_dir or find_builds_dir()
    if not builds_dir or not os.path.isdir(builds_dir):
        print('error: could not locate Path of Building Builds directory; '
              'pass it explicitly', file=sys.stderr)
        return 2

    out_dir = args.out or find_buildplanner_dir()
    print(f'reading builds from: {builds_dir}', file=sys.stderr)
    print(f'writing .build files to: {out_dir}', file=sys.stderr)

    install = find_install(args.pob_path)
    pob = PoBData(install) if install else None
    if not pob:
        print('warning: no Path of Building install found - gem IDs will be '
              'omitted (skills section will be empty)', file=sys.stderr)

    print('loading passive-tree export...', file=sys.stderr)
    try:
        tree = load_tree_export(refresh=args.refresh_tree)
    except Exception as e:  # noqa: BLE001
        print(f'error: failed to load skill-tree export: {e}', file=sys.stderr)
        return 2
    node_id_map = build_node_id_map(tree)
    if args.verbose:
        print(f'  mapped {len(node_id_map)} passive nodes', file=sys.stderr)

    # Walk recursively so class subfolders are included; skip backup/dupe dirs.
    paths = []
    for root, dirs, files in os.walk(builds_dir):
        dirs[:] = [d for d in dirs
                   if not d.startswith('_backup') and d != '_duplicates']
        for f in files:
            if f.lower().endswith('.xml'):
                paths.append(os.path.join(root, f))
    paths.sort()
    if not paths:
        print('no .xml builds found', file=sys.stderr)
        return 1

    print(f'processing {len(paths)} build(s)...', file=sys.stderr)
    written = 0
    seen = {}
    for path in paths:
        base = os.path.splitext(os.path.basename(path))[0]
        if base in seen:
            print(f'skip {os.path.relpath(path, builds_dir)}: duplicate name of '
                  f'{os.path.relpath(seen[base], builds_dir)}', file=sys.stderr)
            continue
        seen[base] = path
        result = _process_one(
            path, node_id_map=node_id_map, pob=pob, out_dir=out_dir,
            prefer=args.prefer, dry_run=args.dry_run, verbose=args.verbose)
        if result:
            written += 1

    verb = 'would write' if args.dry_run else 'wrote'
    print(f'{verb} {written}/{len(paths)} .build file(s)', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
