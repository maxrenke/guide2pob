"""Generate build-customized PoE2 loot filters from NeverSink/FilterBlade bases.

Pipeline: (optionally) back up existing filters and install a NeverSink base
zip, classify a build's archetype from its PoB2 XML, compose a highlight
override block, and inject it into NeverSink's OVERRIDE AREA 1 (first-match-wins)
so build-relevant drops get loud styling. The base is never edited in place.
"""
import datetime
import os
import re
import zipfile

from .buildfile import parse_pob_xml
from .pobdata import find_builds_dir

# --- locations -------------------------------------------------------------

def find_filter_dir(explicit=None):
    """PoE2's loot-filter directory (the game reads *.filter from here)."""
    if explicit:
        return explicit
    return os.path.join(os.path.expanduser('~'), 'Documents', 'My Games',
                        'Path of Exile 2')


# --- injection -------------------------------------------------------------

BEGIN = "# >>> BUILD-FILTER BEGIN (managed by guide2pob — do not edit inside) <<<"
END = "# >>> BUILD-FILTER END <<<"

# NeverSink's highest-priority override block starts at a `# !! Waypoint c0.<x>`
# line (c0.start on PoE2, c0.alpha on PoE1) — present only in the body, never
# the table of contents, so it's a safe anchor for both games.
_ANCHORS = [
    re.compile(r'!!\s*Waypoint\s+c0\.(start|alpha)'),
    re.compile(r'!!\s*Waypoint\s+c0\.'),
    re.compile(r'!!\s*Waypoint\s+c1\.'),
]


def _strip_existing(lines):
    out, skipping = [], False
    for ln in lines:
        s = ln.strip()
        if s == BEGIN.strip():
            skipping = True
            continue
        if s == END.strip():
            skipping = False
            continue
        if not skipping:
            out.append(ln)
    return out


def _find_anchor(lines):
    for anchor in _ANCHORS:
        for i, ln in enumerate(lines):
            if anchor.search(ln):
                return i
    return None


def inject_block(base_text, block_text):
    """Return ``base_text`` with ``block_text`` inserted into the override area.

    Idempotent: a previously injected block (BEGIN/END markers) is replaced.
    """
    lines = _strip_existing(base_text.splitlines())
    idx = _find_anchor(lines)
    if idx is None:
        idx = 0  # no recognizable anchor: insert at the very top
    payload = [''] + [BEGIN] + block_text.splitlines() + [END] + ['']
    merged = lines[:idx + 1] + payload + lines[idx + 1:]
    return '\n'.join(merged) + '\n'


# --- archetypes ------------------------------------------------------------

STRICTNESS_LABEL = {
    0: 'Soft', 1: 'Regular', 2: 'Semi-Strict', 3: 'Strict',
    4: 'Very Strict', 5: 'Uber Strict', 6: 'Uber Plus Strict',
}

_LOUD = ['SetFontSize 45', 'SetTextColor 230 100 255 255',
         'SetBorderColor 230 100 255 255', 'SetBackgroundColor 35 0 45 255',
         'PlayAlertSound 1 300', 'MinimapIcon 0 Purple Diamond', 'PlayEffect Purple']
_ES = ['SetFontSize 40', 'SetBorderColor 120 120 255 255', 'MinimapIcon 1 Blue Circle']
_EVA = ['SetFontSize 40', 'SetBorderColor 100 230 100 255', 'MinimapIcon 1 Green Circle']
_ARM = ['SetFontSize 40', 'SetBorderColor 230 180 80 255', 'MinimapIcon 1 Yellow Circle']
_JEWEL = ['SetFontSize 40', 'SetBorderColor 100 200 255 255', 'MinimapIcon 1 Cyan Circle']

ARCHETYPES = {
    'caster': [
        ('caster weapons + foci (chaos/spell/ES rares)',
         ['Wands', 'Sceptres', 'Staves', 'Foci'], _LOUD),
        ('energy shield armour', ['Helmets', 'Body Armours', 'Gloves', 'Boots'], _ES),
        ('resist/ES/spell jewellery', ['Rings', 'Amulets', 'Belts'], _JEWEL),
    ],
    'minion': [
        ('minion weapons + foci', ['Sceptres', 'Wands', 'Foci', 'Staves'], _LOUD),
        ('ES/hybrid armour', ['Helmets', 'Body Armours', 'Gloves', 'Boots'], _ES),
        ('spirit/resist jewellery', ['Rings', 'Amulets', 'Belts'], _JEWEL),
    ],
    'attack_armour': [
        ('melee weapons', ['Maces', 'Two Hand Maces', 'Spears', 'Quarterstaves'], _LOUD),
        ('armour bases', ['Helmets', 'Body Armours', 'Gloves', 'Boots', 'Bucklers'], _ARM),
        ('life/resist jewellery', ['Rings', 'Amulets', 'Belts'], _JEWEL),
    ],
    'attack_bow': [
        ('bows + quivers', ['Bows', 'Quivers'], _LOUD),
        ('evasion bases', ['Helmets', 'Body Armours', 'Gloves', 'Boots'], _EVA),
        ('life/resist jewellery', ['Rings', 'Amulets', 'Belts'], _JEWEL),
    ],
    'crossbow': [
        ('crossbows', ['Crossbows'], _LOUD),
        ('armour/evasion bases', ['Helmets', 'Body Armours', 'Gloves', 'Boots'], _ARM),
        ('life/resist jewellery', ['Rings', 'Amulets', 'Belts'], _JEWEL),
    ],
}

CLASS_ARCHETYPE = {
    'Witch': 'caster', 'Sorceress': 'caster',
    'Warrior': 'attack_armour', 'Mercenary': 'crossbow',
    'Ranger': 'attack_bow', 'Huntress': 'attack_bow',
    'Monk': 'attack_armour', 'Druid': 'caster',
}

_MINION_HINTS = ('skeleton', 'zombie', 'minion', 'spectre', 'raise ', 'summon',
                 'golem', 'infernal legion', 'companion', 'srs')


def classify(class_name, ascend_name=None, skill_groups=None, override=None):
    """Pick an archetype from class/ascendancy, upgrading to 'minion' when the
    build's skills look summoner-y. ``override`` wins outright."""
    if override:
        return override
    if skill_groups:
        text = ' '.join(
            (g.get('label', '') + ' ' + ' '.join(g.get('gems', [])))
            for g in skill_groups).lower()
        if any(h in text for h in _MINION_HINTS):
            return 'minion'
    return CLASS_ARCHETYPE.get(class_name, 'caster')


def compose_block(archetype):
    rules = ARCHETYPES.get(archetype)
    if not rules:
        raise ValueError(f'unknown archetype {archetype!r}; '
                         f'choose from {sorted(ARCHETYPES)}')
    lines = [f'# Build-specific highlights ({archetype})']
    for comment, classes, style in rules:
        lines.append(f'# build: {comment}')
        lines.append('Show')
        lines.append('    Class ' + ' '.join(f'"{c}"' for c in classes))
        lines.append('    Rarity Rare')
        lines += ['    ' + s for s in style]
        lines.append('')
    return '\n'.join(lines)


# --- base-filter install ---------------------------------------------------

def backup_and_install(zip_path, filter_dir):
    """Move existing *.filter to _old_filters_<date>/ and extract base filters
    from ``zip_path``. Returns the list of installed filenames."""
    os.makedirs(filter_dir, exist_ok=True)
    existing = [f for f in os.listdir(filter_dir) if f.endswith('.filter')]
    if existing:
        stamp = datetime.date.today().strftime('%Y%m%d')
        bdir = os.path.join(filter_dir, f'_old_filters_{stamp}')
        os.makedirs(bdir, exist_ok=True)
        for f in existing:
            os.replace(os.path.join(filter_dir, f), os.path.join(bdir, f))
    installed = []
    with zipfile.ZipFile(zip_path) as z:
        for n in z.namelist():
            if n.endswith('.filter'):
                z.extract(n, filter_dir)
                installed.append(os.path.basename(n))
    return installed


def pick_base(filter_dir, installed, strictness):
    """Return the path of the installed base matching the strictness index."""
    for f in installed:
        if re.search(rf'_{strictness}_', f):
            return os.path.join(filter_dir, f)
    return os.path.join(filter_dir, installed[0]) if installed else None


# --- build resolution ------------------------------------------------------

def safe_filename(s):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', (s or '').strip())[:100] or 'build'


def read_build(build_arg, builds_dir=None):
    """Resolve a build (path or name substring) to (name, class, ascend, skills)."""
    if not build_arg:
        return None, None, None, None
    path = build_arg
    if not os.path.isfile(path):
        bd = builds_dir or find_builds_dir()
        if bd:
            for root, _, files in os.walk(bd):
                for f in files:
                    if f.endswith('.xml') and build_arg.lower() in f.lower():
                        path = os.path.join(root, f)
                        break
                if os.path.isfile(path):
                    break
    if not os.path.isfile(path):
        raise FileNotFoundError(f'build not found: {build_arg}')
    parsed = parse_pob_xml(open(path, encoding='utf-8').read(), prefer='largest')
    name = os.path.splitext(os.path.basename(path))[0]
    return (name, parsed.get('class_name'), parsed.get('ascend_name'),
            parsed.get('skill_groups'))


# --- orchestrator ----------------------------------------------------------

def generate(*, zip_path=None, build=None, name=None, archetype=None,
             strictness=3, filter_dir=None, builds_dir=None):
    """Run the full pipeline. Returns a result dict with paths and metadata."""
    filter_dir = find_filter_dir(filter_dir)
    bname, cls, asc, skills = read_build(build, builds_dir)
    arche = classify(cls, asc, skills, archetype)
    out_name = safe_filename(name or bname or f'{arche} build')

    backed_up = None
    if zip_path:
        before = set(f for f in os.listdir(filter_dir)
                     if f.endswith('.filter')) if os.path.isdir(filter_dir) else set()
        installed = backup_and_install(zip_path, filter_dir)
        backed_up = sorted(before)
    else:
        installed = [f for f in os.listdir(filter_dir) if f.endswith('.filter')
                     and 'BUILD-FILTER' not in open(
                         os.path.join(filter_dir, f), encoding='utf-8',
                         errors='ignore').read(200)]

    base = pick_base(filter_dir, installed, strictness)
    if not base:
        raise FileNotFoundError('no base filter found; pass zip_path')

    label = STRICTNESS_LABEL.get(strictness, 'Strict')
    out_path = os.path.join(filter_dir, f'{out_name} [{label}].filter')
    block = compose_block(arche)
    new_text = inject_block(open(base, encoding='utf-8', errors='replace').read(), block)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(new_text)

    return {
        'build_name': bname, 'class': cls, 'ascendancy': asc,
        'archetype': arche, 'base': base, 'output': out_path,
        'installed': installed, 'backed_up': backed_up,
    }
