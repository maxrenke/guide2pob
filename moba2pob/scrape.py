"""Fetch and parse Mobalytics PoE2 build guides.

Mobalytics is a Next.js app that embeds the full structured build inside a
``window.__PRELOADED_STATE__`` blob in the page HTML, so no login, browser
automation, or API key is needed - a plain HTTP GET with browser-like headers
is enough.
"""
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
    """Download a Mobalytics build page."""
    if 'mobalytics.gg' not in url:
        raise ScrapeError(f"not a mobalytics URL: {url}")
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode('utf-8', errors='replace')
    except Exception as e:  # noqa: BLE001 - surface any network failure cleanly
        raise ScrapeError(f"failed to fetch {url}: {e}") from e


def _extract_preloaded_state(html):
    """Pull the window.__PRELOADED_STATE__ JSON object out of page HTML."""
    marker = 'window.__PRELOADED_STATE__='
    i = html.find(marker)
    if i < 0:
        raise ScrapeError("no __PRELOADED_STATE__ in page - layout may have changed")
    start = i + len(marker)
    # The assignment is followed by a JSON object; find its balanced extent.
    depth = 0
    for j in range(start, len(html)):
        c = html[j]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return json.loads(html[start:j + 1])
    raise ScrapeError("could not parse __PRELOADED_STATE__ object")


def _find_build_document(obj):
    """Recursively locate the userGeneratedDocumentBySlug build document."""
    if isinstance(obj, dict):
        if 'userGeneratedDocumentBySlug' in obj:
            doc = obj['userGeneratedDocumentBySlug']
            data = (doc or {}).get('data', {}).get('data')
            if data and 'buildVariants' in data:
                return data
        for v in obj.values():
            found = _find_build_document(v)
            if found:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _find_build_document(v)
            if found:
                return found
    return None


def parse_build(html):
    """Return the Mobalytics build document dict from page HTML."""
    state = _extract_preloaded_state(html)
    doc = _find_build_document(state)
    if not doc:
        raise ScrapeError("no build document found in page state")
    return doc


def load_build(source):
    """Load a build from a Mobalytics URL or a local HTML/JSON file.

    Returns ``(doc, html)`` where ``html`` is the page source (or ``None`` for
    pure JSON inputs). Keeping the HTML around lets callers pull display-only
    bits like variant tab labels that aren't in the embedded build state.
    """
    if source.startswith('http://') or source.startswith('https://'):
        html = fetch_html(source)
        return parse_build(html), html
    text = open(source, encoding='utf-8').read()
    if source.endswith('.json'):
        data = json.loads(text)
        if 'buildVariants' in data:
            return data, None
        doc = _find_build_document(data)
        if doc:
            return doc, None
        raise ScrapeError("JSON file has no build document")
    return parse_build(text), text


def variant_labels(html, variants):
    """Return display labels for build variants, scraped from tab elements.

    Mobalytics renders each variant as a React-Aria tab whose label is the
    first text node after the opening tag. The labels aren't in the build
    JSON, so we read them from the rendered HTML.
    """
    if not html:
        return [None] * len(variants)
    out = []
    for v in variants:
        vid = v.get('id')
        if not vid:
            out.append(None)
            continue
        m = re.search(r'data-key="' + re.escape(str(vid)) + r'"', html)
        if not m:
            out.append(None)
            continue
        segment = html[m.start():m.start() + 4000]
        for text in re.findall(r'>([^<>]+?)<', segment):
            t = text.strip()
            if t and len(t) <= 40:
                out.append(t)
                break
        else:
            out.append(None)
    return out


def build_variants(doc):
    """Return the list of build variant dicts."""
    return (doc.get('buildVariants') or {}).get('values') or []


def slug_from_url(url):
    m = re.search(r'/builds/([A-Za-z0-9-]+)', url)
    return m.group(1) if m else None
