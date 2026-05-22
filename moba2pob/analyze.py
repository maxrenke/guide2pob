"""Optional LLM analysis of a converted build.

Three providers are supported, all optional:

* ``anthropic`` - Claude via the Anthropic API (needs ANTHROPIC_API_KEY).
* ``ollama``    - a local model served by Ollama (no key, runs offline).
* ``none``      - skip analysis (default).
"""
import os
import json
import urllib.request

from .convert import _common_item, _skill_groups, gem_name

_SYSTEM = (
    "You are an expert Path of Exile 2 build analyst. Given a build summary, "
    "give a concise, practical analysis: playstyle, core damage and defence "
    "scaling, standout items, weaknesses or risks, and what to prioritise "
    "while gearing. Use short sections. Do not invent items not listed."
)


class AnalysisError(RuntimeError):
    pass


def summarize(variant, meta, pob=None):
    """Build a compact plain-text description of a build variant."""
    lines = [
        f"Class: {meta['class']}  Ascendancy: {meta['ascendancy']}",
        f"Passive nodes allocated: {meta['node_count']}",
        "",
        "Skill setups:",
    ]
    for grp in _skill_groups(variant):
        gems = grp['gems']
        active = gems[0]['name'] or gem_name(gems[0]['slug'], pob)
        supports = [gem_name(g['slug'], pob) for g in gems[1:]]
        sup = f" + {', '.join(supports)}" if supports else ""
        lines.append(f"  - {active}{sup}")

    lines += ["", "Equipment:"]
    for slot, item in (variant.get('equipment') or {}).items():
        ci = _common_item(item)
        if not ci:
            continue
        rarity = 'Unique' if ci.get('isUnique') else 'Rare'
        mods = [d['description'] for d in (ci.get('explicitDescriptions') or [])]
        lines.append(f"  - {slot}: [{rarity}] {ci.get('name', '?')}")
        for m in mods[:6]:
            lines.append(f"      {m}")

    jewels = (variant.get('passiveTree') or {}).get('jewels') or []
    if jewels:
        lines.append("")
        lines.append(f"Jewels: {len(jewels)}")
    return '\n'.join(lines)


def analyze(summary, provider='anthropic', model=None, api_key=None,
            base_url=None, timeout=120):
    """Run an LLM analysis of a build summary. Returns the analysis text."""
    provider = (provider or 'none').lower()
    prompt = ("Analyse this Path of Exile 2 build.\n\n" + summary)
    if provider == 'none':
        return None
    if provider == 'anthropic':
        return _call_anthropic(prompt, model, api_key, timeout)
    if provider == 'ollama':
        return _call_ollama(prompt, model, base_url, timeout)
    raise AnalysisError(f"unknown provider: {provider}")


def _http_json(url, payload, headers, timeout):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json', **headers}, method='POST')
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _call_anthropic(prompt, model, api_key, timeout):
    api_key = api_key or os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise AnalysisError(
            "no Anthropic API key (pass --api-key or set ANTHROPIC_API_KEY)")
    model = model or 'claude-sonnet-4-6'
    try:
        data = _http_json(
            'https://api.anthropic.com/v1/messages',
            {
                'model': model,
                'max_tokens': 1024,
                'system': _SYSTEM,
                'messages': [{'role': 'user', 'content': prompt}],
            },
            {'x-api-key': api_key, 'anthropic-version': '2023-06-01'},
            timeout)
    except Exception as e:  # noqa: BLE001
        raise AnalysisError(f"Anthropic request failed: {e}") from e
    return ''.join(b.get('text', '') for b in data.get('content', []))


def _call_ollama(prompt, model, base_url, timeout):
    base_url = (base_url or os.environ.get('OLLAMA_HOST')
                or 'http://localhost:11434').rstrip('/')
    model = model or 'qwen2.5-coder:14b'
    try:
        data = _http_json(
            base_url + '/api/chat',
            {
                'model': model,
                'stream': False,
                'messages': [
                    {'role': 'system', 'content': _SYSTEM},
                    {'role': 'user', 'content': prompt},
                ],
            },
            {}, timeout)
    except Exception as e:  # noqa: BLE001
        raise AnalysisError(
            f"Ollama request failed ({base_url}); is it running? {e}") from e
    return (data.get('message') or {}).get('content', '')
