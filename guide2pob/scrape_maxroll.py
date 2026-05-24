"""Fetch and parse Maxroll PoE2 build guides and planner pages.

Maxroll uses a Remix framework; the full planner state is embedded in a
``window.__remixContext`` blob in the page HTML. Build guide pages embed
a link to a planner page (/poe2/planner/<id>); planner pages contain the
full structured build data.
"""
import html as _html
import json
import re
import urllib.request

_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) '
                   'Gecko/20100101 Firefox/128.0'),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}


class ScrapeError(RuntimeError):
    pass


def fetch_html(url, timeout=30):
    if 'maxroll.gg' not in url:
        raise ScrapeError(f"not a maxroll.gg URL: {url}")
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode('utf-8', errors='replace')
    except Exception as e:  # noqa: BLE001
        raise ScrapeError(f"failed to fetch {url}: {e}") from e


def _extract_remix_context(html):
    marker = 'window.__remixContext = '
    i = html.find(marker)
    if i < 0:
        raise ScrapeError("no __remixContext in page - layout may have changed")
    start = i + len(marker)
    depth = 0
    for j in range(start, len(html)):
        c = html[j]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return json.loads(html[start:j + 1])
    raise ScrapeError("could not parse __remixContext object")


def _parse_planner_html(html):
    """Return (profile, planner_data) from a planner page HTML."""
    ctx = _extract_remix_context(html)
    loader = ctx.get('state', {}).get('loaderData', {})
    planner_entry = loader.get('poe2-planner-by-id')
    if not planner_entry:
        raise ScrapeError("no planner data in __remixContext - layout may have changed")
    profile = planner_entry.get('profile')
    if not profile:
        raise ScrapeError("no profile in planner data")
    raw = profile.get('data')
    if not raw:
        raise ScrapeError("no data field in planner profile")
    try:
        outer = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ScrapeError(f"could not parse planner data JSON: {e}") from e
    # The outer object has keys: 'planner' (passives/skills/equipment/ascendancy),
    # 'items' (item lookup dict), 'embeds', etc.
    inner = outer.get('planner')
    if not inner:
        raise ScrapeError("planner data has no 'planner' key - layout may have changed")
    # Merge item lookup into the inner planner dict so callers have one object.
    inner = dict(inner)
    inner['items'] = outer.get('items') or {}
    return profile, inner


def _guide_planner_id(html):
    """Find a planner ID embedded in a guide page."""
    m = re.search(r'maxroll\.gg/poe2/planner/([A-Za-z0-9_-]+)', html)
    return m.group(1) if m else None


def load_build(source, timeout=30):
    """Load a Maxroll build from a guide URL, planner URL, or local file.

    Returns ``(profile, planner_data, guide_html)`` where:
    - ``profile``  is the Maxroll profile dict (has ``name``, ``ascendancy``, etc.)
    - ``planner_data``  is the decoded inner build JSON
    - ``guide_html``  is the guide page HTML (or None)
    """
    if source.startswith('http://') or source.startswith('https://'):
        html = fetch_html(source, timeout=timeout)
        if '/build-guides/' in source:
            guide_html = html
            pid = _guide_planner_id(html)
            if not pid:
                raise ScrapeError("no planner URL found in the guide page")
            planner_html = fetch_html(
                f'https://maxroll.gg/poe2/planner/{pid}', timeout=timeout)
            profile, planner = _parse_planner_html(planner_html)
            return profile, planner, guide_html
        # Planner page directly
        profile, planner = _parse_planner_html(html)
        return profile, planner, None

    # Local file
    text = open(source, encoding='utf-8').read()
    if source.endswith('.json'):
        data = json.loads(text)
        if 'planner' in data and 'items' in data:
            # Raw outer JSON (as saved from the planner page)
            inner = dict(data['planner'])
            inner['items'] = data.get('items') or {}
            return {'name': 'build', 'class': '', 'ascendancy': ''}, inner, None
        raise ScrapeError("JSON file not recognized as Maxroll planner data")
    profile, planner = _parse_planner_html(text)
    return profile, planner, text


def slug_from_url(url):
    """Extract a filesystem-safe slug from a Maxroll URL."""
    m = re.search(r'/build-guides/([A-Za-z0-9-]+)', url)
    if m:
        return m.group(1)
    m = re.search(r'/planner/([A-Za-z0-9_-]+)', url)
    return m.group(1) if m else None


def passive_variants(planner):
    """Return the list of passive-tree variant dicts from the planner."""
    return (planner.get('passives') or {}).get('variants') or []


def equipment_variants(planner):
    """Return the list of equipment variant dicts from the planner."""
    return (planner.get('equipment') or {}).get('variants') or []


def skill_steps(planner):
    """Return the list of skill-step dicts (progression phases)."""
    return (planner.get('skills') or {}).get('steps') or []


def guide_text(html):
    """Extract plain text from the main article body of a Maxroll guide page.

    Maxroll renders guide content inside ``<div id="main-article">``. Text is
    extracted from heading and paragraph tags; the Video and Changelog sections
    are omitted since they add no useful notes content.

    Returns an empty string when no content is found or ``html`` is None.
    """
    if not html:
        return ''
    start = html.find('id="main-article"')
    if start < 0:
        return ''
    # Skip past the closing '>' of the opening tag so the attribute text
    # doesn't appear in the extracted content.
    start = html.find('>', start)
    if start < 0:
        return ''
    start += 1  # step past the '>'
    # Stop before video / changelog sections or the site footer.
    end = len(html)
    for stop in ('id="video-header"', 'id="changelog-header"', 'class="_Footer_'):
        i = html.find(stop, start)
        if 0 < i < end:
            # Back up to the last '<' before this marker so we don't include a
            # partial opening tag in the content.
            tag_start = html.rfind('<', start, i)
            end = tag_start if tag_start > start else i
    content = html[start:end]

    def _strip(h):
        h = re.sub(r'<br\s*/?>', '\n', h)
        h = re.sub(r'</(p|h[1-6]|li|div)>', '\n', h)
        h = re.sub(r'<li[^>]*>', '- ', h)
        h = re.sub(r'<h([1-6])[^>]*>',
                   lambda m: '\n' + '#' * int(m.group(1)) + ' ', h)
        h = re.sub(r'<[^>]+>', '', h)
        h = _html.unescape(h)
        lines = [ln.strip() for ln in h.splitlines()]
        return '\n'.join(ln for ln in lines if ln)

    return _strip(content)
