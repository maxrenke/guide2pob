"""Optional Path of Building (PoE2) data integration.

When a Path of Building Community (PoE2) install is found, guide2pob uses its
data files to resolve accurate gem names, unique item base types, the current
passive-tree version, and ascendancy detection from passive node IDs.

Everything here degrades gracefully: with no install, conversion still works
with prettified gem-name guesses and no unique base lookup.
"""
import os
import re
import glob

# Common install locations; override with --pob-path or POB2_PATH env var.
_DEFAULT_PATHS = [
    os.path.expandvars(r'%APPDATA%\Path of Building Community (PoE2)'),
    os.path.expandvars(r'%PROGRAMFILES%\Path of Building Community (PoE2)'),
    os.path.expanduser('~/Library/Application Support/Path of Building Community (PoE2)'),
    os.path.expanduser('~/.local/share/Path of Building Community (PoE2)'),
]


def find_install(explicit=None):
    """Return a valid PoB2 install path, or None."""
    for cand in [explicit, os.environ.get('POB2_PATH'), *_DEFAULT_PATHS]:
        if cand and os.path.isdir(cand) and os.path.isdir(os.path.join(cand, 'TreeData')):
            return cand
    return None


def find_exe(install=None):
    """Return the PoB2 executable path, or None."""
    base = install or find_install()
    if not base:
        return None
    for name in ('Path of Building-PoE2.exe', 'PathOfBuilding.exe',
                 'Path of Building.exe'):
        p = os.path.join(base, name)
        if os.path.isfile(p):
            return p
    return None


def find_builds_dir(explicit=None):
    """Return the PoB2 user builds directory, or None.

    PoB2 stores user data (builds, settings) in
    ~/Documents/Path of Building (PoE2)/ - separate from the install dir.
    """
    candidates = [
        explicit,
        os.environ.get('POB2_BUILDS_PATH'),
        os.path.join(os.path.expanduser('~'), 'Documents',
                     'Path of Building (PoE2)', 'Builds'),
        os.path.join(os.path.expanduser('~'), 'Documents',
                     'Path of Building Community (PoE2)', 'Builds'),
    ]
    for cand in candidates:
        if cand and os.path.isdir(cand):
            return cand
    return None


def _balanced(s, i):
    """s[i] is '{'; return index past the matching '}'."""
    depth = 0
    while i < len(s):
        if s[i] == '{':
            depth += 1
        elif s[i] == '}':
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return i


class PoBData:
    """Lazily-loaded view over a Path of Building (PoE2) install."""

    def __init__(self, install_path):
        self.path = install_path
        self._gems = None
        self._uniques = None
        self._tree_text = None
        self._tree_version = None

    # -- passive tree ----------------------------------------------------
    @property
    def tree_version(self):
        if self._tree_version is None:
            versions = []
            for d in glob.glob(os.path.join(self.path, 'TreeData', '*')):
                name = os.path.basename(d)
                if re.fullmatch(r'\d+_\d+', name):
                    versions.append(name)
            versions.sort(key=lambda v: tuple(int(x) for x in v.split('_')))
            self._tree_version = versions[-1] if versions else '0_4'
        return self._tree_version

    @property
    def _tree(self):
        if self._tree_text is None:
            f = os.path.join(self.path, 'TreeData', self.tree_version, 'tree.lua')
            self._tree_text = open(f, encoding='utf-8').read()
        return self._tree_text

    def ascendancy_of_node(self, node_id):
        """Return the ascendancy name for a passive node ID, or None."""
        anchor = '[%s]={' % node_id
        i = self._tree.find(anchor)
        if i < 0:
            return None
        block = self._tree[i:_balanced(self._tree, i + len(anchor) - 1)]
        m = re.search(r'ascendancyName="([^"]+)"', block)
        return m.group(1) if m else None

    @property
    def jewel_socket_nodes(self):
        """Set of node IDs (str) that accept jewels.

        Covers both plain Jewel Socket nodes (isJewelSocket=true) and
        notable nodes that contain a socket (containJewelSocket=true).
        """
        if not hasattr(self, '_jewel_socket_nodes'):
            result = set()
            tree = self._tree
            pattern = re.compile(r'(?:isJewelSocket|containJewelSocket)=true')
            for m in pattern.finditer(tree):
                # Scan back for the nearest enclosing [<digits>]={ entry.
                prefix = tree[max(0, m.start() - 2000):m.start()]
                last = None
                for id_m in re.finditer(r'\[(\d{4,})\]={', prefix):
                    last = id_m
                if last:
                    result.add(last.group(1))
            self._jewel_socket_nodes = result
        return self._jewel_socket_nodes

    # -- gems ------------------------------------------------------------
    @property
    def gems(self):
        """Lowercased id/effect -> display name."""
        if self._gems is None:
            self._gems = {}
            f = os.path.join(self.path, 'Data', 'Gems.lua')
            if os.path.isfile(f):
                t = open(f, encoding='utf-8').read()
                for blk in re.finditer(r'\{(.*?)\n\t\}', t, re.S):
                    b = blk.group(1)
                    nm = re.search(r'name = "([^"]+)"', b)
                    if not nm:
                        continue
                    for key in re.findall(
                            r'(?:variantId|grantedEffectId|gameId) = "([^"]+)"', b):
                        k = key.lower()
                        self._gems[k] = nm.group(1)
                        self._gems[k.replace('metadata/items/gems/', '')] = nm.group(1)
        return self._gems

    # -- uniques ---------------------------------------------------------
    @property
    def unique_bases(self):
        """Lowercased unique name -> base type."""
        if self._uniques is None:
            self._uniques = {}
            for f in glob.glob(os.path.join(self.path, 'Data', 'Uniques', '*.lua')):
                t = open(f, encoding='utf-8').read()
                for blk in re.findall(r'\[\[\s*\n(.*?)\n\]\]', t, re.S):
                    lines = [l for l in blk.split('\n') if l.strip()]
                    if len(lines) >= 2:
                        self._uniques[lines[0].strip().lower()] = lines[1].strip()
        return self._uniques

    # -- attribute nodes -------------------------------------------------
    @property
    def attribute_options(self):
        """Map of attribute node parent_id -> {option_0based_idx: (attr_name, option_node_id)}.

        Attribute nodes in PoE2 let players pick Strength/Dexterity/Intelligence.
        PoB tracks which option was chosen via AttributeOverride strNodes/dexNodes/intNodes.
        """
        if not hasattr(self, '_attribute_options'):
            result = {}
            tree = self._tree
            # Find all isAttribute=true nodes and parse their options
            for m in re.finditer(r'\[(\d+)\]=\{', tree):
                node_id = m.group(1)
                block_start = m.start()
                # Quick check: isAttribute before scanning the full block
                snippet = tree[m.end():m.end() + 2000]
                if 'isAttribute=true' not in snippet:
                    continue
                # Parse options={[1]={id=X,name="Y"},...}
                opts_m = re.search(r'options=\{(.*?)\n\t\t\}', snippet, re.S)
                if not opts_m:
                    continue
                opts_text = opts_m.group(1)
                options = {}
                for opt in re.finditer(
                        r'\[(\d+)\]=\{.*?id=(\d+).*?name="([^"]+)"', opts_text, re.S):
                    lua_idx = int(opt.group(1)) - 1  # convert 1-based to 0-based
                    opt_id = opt.group(2)
                    opt_name = opt.group(3).lower()
                    options[lua_idx] = (opt_name, opt_id)
                if options:
                    result[node_id] = options
            self._attribute_options = result
        return self._attribute_options

    # -- mod texts -------------------------------------------------------
    @property
    def mod_texts(self):
        """mod_id -> display text string (from all Mod*.lua data files).

        Text strings use (min-max) range notation, e.g.
        '+(5-8) to Strength'.  Callers substitute actual rolled values.
        """
        if not hasattr(self, '_mod_texts'):
            self._mod_texts = {}
            # Pattern: ["ModId"] = { ...optional fields..., "mod text", statOrder
            pattern = re.compile(
                r'\["([A-Za-z][A-Za-z0-9_]+)"\]\s*=\s*\{.*?"([^"]+)",\s*statOrder',
                re.S)
            mod_files = [
                'ModItem.lua', 'ModItemExclusive.lua', 'ModCorrupted.lua',
                'ModCharm.lua', 'ModFlask.lua', 'ModJewel.lua',
            ]
            for fname in mod_files:
                fpath = os.path.join(self.path, 'Data', fname)
                if not os.path.isfile(fpath):
                    continue
                for m in pattern.finditer(open(fpath, encoding='utf-8').read()):
                    if m.group(1) not in self._mod_texts:
                        self._mod_texts[m.group(1)] = m.group(2)
        return self._mod_texts
