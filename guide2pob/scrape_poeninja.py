"""Query poe.ninja for PoE2 build popularity data.

Public API
----------
get_leagues()               -> list[dict]  (name, url, displayName, hardcore)
get_snapshot(league_url)    -> dict         (version, snapshotName, total)
get_class_popularity(league_url) -> list[dict]  sorted by count desc
get_skill_popularity(league_url, class_name=None) -> list[dict]  sorted by count desc
"""
import json
import struct
import urllib.request

_BASE = 'https://poe.ninja'
_UA = 'guide2pob/1.0'

# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #

def _get_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': _UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def _get_bytes(url):
    req = urllib.request.Request(url, headers={'User-Agent': _UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read()


# --------------------------------------------------------------------------- #
# Minimal protobuf decoder (zero external dependencies)
# --------------------------------------------------------------------------- #

def _read_varint(buf, pos):
    result = 0
    shift = 0
    while pos < len(buf):
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, pos
        shift += 7
    raise ValueError('truncated varint')


def _decode_msg(buf, pos=0, end=None, strict=False):
    """Decode a protobuf message into {field_number: [value, ...]}.

    Values are:
      int        for wire type 0 (varint)
      bytes      for wire type 2 (length-delimited) when not valid UTF-8
      str        for wire type 2 when valid UTF-8
      dict       for wire type 2 when it looks like a nested message

    strict=True raises ValueError if a length-delimited field overflows the
    buffer or if any bytes are left unconsumed (used by _try_nested to reject
    false positives like SHA1 hashes that start with valid tag bytes).
    """
    if end is None:
        end = len(buf)
    fields = {}
    while pos < end:
        try:
            tag, pos = _read_varint(buf, pos)
        except (ValueError, IndexError):
            break
        fn = tag >> 3
        wt = tag & 7
        if wt == 0:
            val, pos = _read_varint(buf, pos)
            fields.setdefault(fn, []).append(val)
        elif wt == 2:
            n, pos = _read_varint(buf, pos)
            if strict and pos + n > end:
                raise ValueError('length-delimited field overflows buffer')
            data = buf[pos:pos + n]
            pos += n
            # Try nested message first (heuristic: strict parse must consume all bytes)
            nested = _try_nested(data)
            if nested is not None:
                fields.setdefault(fn, []).append(nested)
            else:
                try:
                    fields.setdefault(fn, []).append(data.decode('utf-8'))
                except UnicodeDecodeError:
                    fields.setdefault(fn, []).append(data)
        elif wt == 5:
            pos += 4
        elif wt == 1:
            pos += 8
        else:
            if strict:
                raise ValueError(f'unknown wire type {wt} at pos {pos}')
            break   # unknown wire type - give up on this message
    if strict and pos != end:
        raise ValueError(f'unconsumed bytes: pos={pos} end={end}')
    return fields


def _try_nested(data):
    """Return decoded dict if data parses as a complete, valid protobuf message.

    Uses strict mode: out-of-bounds length fields or unconsumed trailing bytes
    cause rejection (handles e.g. SHA1 hashes that start with a valid tag byte).
    """
    if not data:
        return None
    # A valid protobuf message starts with a tag byte where wt in {0,1,2,5}.
    tag = data[0]
    wt = tag & 7
    if wt not in (0, 1, 2, 5):
        return None
    try:
        result = _decode_msg(data, strict=True)
        return result if result else None
    except (ValueError, IndexError):
        return None


def _scalar(fields, fn):
    """Return the first scalar value for field fn, or None."""
    vals = fields.get(fn, [])
    return vals[0] if vals else None


def _strings(fields, fn):
    """Return all string values for field fn."""
    return [v for v in fields.get(fn, []) if isinstance(v, str)]


# --------------------------------------------------------------------------- #
# Index / snapshot resolution
# --------------------------------------------------------------------------- #

def get_leagues():
    """Return list of available PoE2 build leagues.

    Each entry: {'name': str, 'url': str, 'displayName': str, 'hardcore': bool}
    """
    data = _get_json(f'{_BASE}/poe2/api/data/index-state')
    leagues = []
    for entry in data.get('buildLeagues', []):
        leagues.append({
            'name': entry.get('name', ''),
            'url': entry.get('url', ''),
            'displayName': entry.get('displayName', ''),
            'hardcore': bool(entry.get('hardcore', False)),
        })
    return leagues


def get_snapshot(league_url):
    """Return snapshot info for the given league URL slug.

    Returns {'version': str, 'snapshotName': str} or raises KeyError.
    """
    data = _get_json(f'{_BASE}/poe2/api/data/index-state')
    for entry in data.get('snapshotVersions', []):
        if entry.get('url') == league_url:
            return {
                'version': entry['version'],
                'snapshotName': entry['snapshotName'],
            }
    raise KeyError(f'no snapshot for league url {league_url!r}')


# --------------------------------------------------------------------------- #
# Search + dictionary resolution
# --------------------------------------------------------------------------- #

def _fetch_search(version, snapshot_name, class_name=None):
    """Fetch and decode the search protobuf for a given league snapshot.

    Returns the decoded dict for the inner result message (field 1 of outer).
    """
    url = f'{_BASE}/poe2/api/builds/{version}/search?overview={snapshot_name}'
    if class_name:
        url += f'&class={urllib.request.quote(class_name)}'
    raw = _get_bytes(url)
    outer = _decode_msg(raw)
    # The result is wrapped in field 1
    result_list = outer.get(1, [])
    if not result_list:
        return {}
    first = result_list[0]
    return first if isinstance(first, dict) else {}


def _fetch_dictionary(hash_str):
    """Fetch a poe.ninja dimension dictionary. Returns (type_name, [str, ...])."""
    url = f'{_BASE}/poe2/api/builds/dictionary/{hash_str}'
    raw = _get_bytes(url)
    msg = _decode_msg(raw)
    type_name = _scalar(msg, 1) or ''
    if not isinstance(type_name, str):
        type_name = ''
    names = _strings(msg, 2)
    return type_name, names


def _dim_entries(result, dim_name):
    """Return list of (id, count) pairs for a named dimension.

    Matches by dim internal name (field 1) OR display name (field 2).
    """
    for dim in result.get(2, []):
        if not isinstance(dim, dict):
            continue
        name_val = _scalar(dim, 1)
        disp_val = _scalar(dim, 2)
        if isinstance(name_val, str) and name_val == dim_name:
            pass  # matched by internal name
        elif isinstance(disp_val, str) and disp_val == dim_name:
            pass  # matched by display name
        else:
            continue
        entries = []
        for entry in dim.get(3, []):
            if isinstance(entry, dict):
                eid = _scalar(entry, 1)
                cnt = _scalar(entry, 2)
                if eid is not None and cnt is not None:
                    entries.append((eid, cnt))
        return entries
    return []


def _dim_hash(result, dim_name):
    """Extract the dictionary hash for a dimension.

    The hash mapping (field 6) uses the display name as its key.  This
    function builds a display-name lookup from the dimensions list so we can
    find the hash by either internal or display name.
    """
    # Build internal->display mapping from the dimensions
    name_to_display = {}
    for dim in result.get(2, []):
        if isinstance(dim, dict):
            n = _scalar(dim, 1)
            d = _scalar(dim, 2)
            if isinstance(n, str) and isinstance(d, str):
                name_to_display[n] = d

    # Resolve the lookup key to a display name
    display_key = name_to_display.get(dim_name, dim_name)

    for mapping in result.get(6, []):
        if not isinstance(mapping, dict):
            continue
        key = _scalar(mapping, 1)
        hash_val = _scalar(mapping, 2)
        if isinstance(key, str) and key in (dim_name, display_key):
            return hash_val if isinstance(hash_val, str) else None
    return None


def _resolve_ids(id_count_pairs, names_list):
    """Map (id, count) pairs to {name: count} using 1-based indexing into names_list."""
    result = {}
    for eid, cnt in id_count_pairs:
        idx = eid - 1  # IDs are 1-based
        if 0 <= idx < len(names_list):
            result[names_list[idx]] = cnt
    return result


# --------------------------------------------------------------------------- #
# Public high-level functions
# --------------------------------------------------------------------------- #

def get_class_popularity(league_url='vaal'):
    """Return class popularity for a league, sorted by count descending.

    Returns list of {'name': str, 'count': int, 'pct': float}.
    """
    snap = get_snapshot(league_url)
    result = _fetch_search(snap['version'], snap['snapshotName'])

    total = _scalar(result, 1) or 1

    entries = _dim_entries(result, 'class')
    hash_str = _dim_hash(result, 'class')
    if not hash_str:
        return []
    _, names = _fetch_dictionary(hash_str)

    named = _resolve_ids(entries, names)
    rows = sorted(
        [{'name': k, 'count': v, 'pct': round(v / total * 100, 2)}
         for k, v in named.items()],
        key=lambda r: r['count'], reverse=True)
    return rows


def get_skill_popularity(league_url='vaal', class_name=None, top=None):
    """Return skill popularity for a league (optionally filtered by class).

    Parameters
    ----------
    league_url  : str   e.g. 'vaal'
    class_name  : str   e.g. 'Lich' or 'Witch' - filters results server-side
    top         : int   if set, return only top-N results

    Returns list of {'name': str, 'count': int}.
    """
    snap = get_snapshot(league_url)
    result = _fetch_search(snap['version'], snap['snapshotName'],
                           class_name=class_name)

    entries = _dim_entries(result, 'skills')
    hash_str = _dim_hash(result, 'skills')
    if not hash_str:
        return []
    _, names = _fetch_dictionary(hash_str)

    named = _resolve_ids(entries, names)
    rows = sorted(
        [{'name': k, 'count': v} for k, v in named.items()],
        key=lambda r: r['count'], reverse=True)
    if top:
        rows = rows[:top]
    return rows


def get_keystone_popularity(league_url='vaal', class_name=None, top=None):
    """Return keystone/notable passive popularity for a league."""
    snap = get_snapshot(league_url)
    result = _fetch_search(snap['version'], snap['snapshotName'],
                           class_name=class_name)

    entries = _dim_entries(result, 'keypassives')
    hash_str = _dim_hash(result, 'keypassives')
    if not hash_str:
        return []
    _, names = _fetch_dictionary(hash_str)

    named = _resolve_ids(entries, names)
    rows = sorted(
        [{'name': k, 'count': v} for k, v in named.items()],
        key=lambda r: r['count'], reverse=True)
    if top:
        rows = rows[:top]
    return rows
