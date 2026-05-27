"""guide2pob-meta: query poe.ninja for PoE2 build popularity data."""
import sys
import argparse

from .scrape_poeninja import (
    get_leagues,
    get_class_popularity,
    get_skill_popularity,
    get_keystone_popularity,
)


def _build_parser():
    p = argparse.ArgumentParser(
        prog='guide2pob-meta',
        description='Query poe.ninja for PoE2 build popularity.')
    p.add_argument('--league', default='vaal', metavar='URL',
                   help='league URL slug (default: vaal); use --leagues to list')
    p.add_argument('--leagues', action='store_true',
                   help='list available leagues and exit')
    p.add_argument('--classes', action='store_true',
                   help='show class popularity')
    p.add_argument('--skills', action='store_true',
                   help='show skill popularity')
    p.add_argument('--keystones', action='store_true',
                   help='show keystone/notable passive popularity')
    p.add_argument('--class', dest='cls', metavar='NAME',
                   help='filter skills/keystones by class (e.g. Lich)')
    p.add_argument('--top', type=int, default=20,
                   help='show top N results (default: 20)')
    return p


def main(argv=None):
    args = _build_parser().parse_args(argv)

    if args.leagues:
        leagues = get_leagues()
        print(f'{"Display Name":<30}  {"URL":<20}  HC')
        print('-' * 60)
        for lg in leagues:
            hc = 'yes' if lg['hardcore'] else ''
            print(f'{lg["displayName"]:<30}  {lg["url"]:<20}  {hc}')
        return 0

    ran_any = False

    if args.classes:
        ran_any = True
        print(f'\nClass popularity  [{args.league}]')
        print(f'{"Class":<28}  {"Count":>8}  {"Pct":>6}')
        print('-' * 50)
        rows = get_class_popularity(args.league)
        for r in rows[:args.top]:
            print(f'{r["name"]:<28}  {r["count"]:>8,}  {r["pct"]:>5.1f}%')

    if args.skills:
        ran_any = True
        label = f'{args.cls} / ' if args.cls else ''
        print(f'\nSkill popularity  [{label}{args.league}]')
        print(f'{"Skill":<40}  {"Count":>8}')
        print('-' * 55)
        rows = get_skill_popularity(args.league, class_name=args.cls, top=args.top)
        for r in rows:
            print(f'{r["name"]:<40}  {r["count"]:>8,}')

    if args.keystones:
        ran_any = True
        label = f'{args.cls} / ' if args.cls else ''
        print(f'\nKeystone popularity  [{label}{args.league}]')
        print(f'{"Keystone":<40}  {"Count":>8}')
        print('-' * 55)
        rows = get_keystone_popularity(args.league, class_name=args.cls, top=args.top)
        for r in rows:
            print(f'{r["name"]:<40}  {r["count"]:>8,}')

    if not ran_any:
        _build_parser().print_help()
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
