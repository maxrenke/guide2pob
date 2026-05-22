"""Upload Path of Building codes to pobb.in.

pobb.in hosts PoB builds and is what Path of Building itself uses for its
"Import from URL" feature. Uploading returns a short ``https://pobb.in/<id>``
link that opens directly in PoB.
"""
import urllib.request

_POBBIN_POST = 'https://pobb.in/pob/'


class UploadError(RuntimeError):
    pass


def _to_urlsafe(code):
    """pobb.in expects URL-safe base64 (it rejects '+' and '/')."""
    return code.strip().replace('+', '-').replace('/', '_')


def upload_pobbin(code, timeout=30):
    """Upload a PoB import code to pobb.in; return the shareable URL."""
    body = _to_urlsafe(code).encode('ascii')
    req = urllib.request.Request(
        _POBBIN_POST, data=body, method='POST',
        headers={
            'User-Agent': 'moba2pob (+https://github.com/maxrenke/moba2pob)',
            'Content-Type': 'text/plain',
        })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ident = resp.read().decode('utf-8', errors='replace').strip()
    except urllib.error.HTTPError as e:
        detail = e.read().decode('utf-8', errors='replace')[:200]
        raise UploadError(f"pobb.in rejected the build (HTTP {e.code}): {detail}") from e
    except Exception as e:  # noqa: BLE001
        raise UploadError(f"pobb.in upload failed: {e}") from e
    if not ident or '/' in ident or len(ident) > 64:
        raise UploadError(f"unexpected pobb.in response: {ident!r}")
    return {
        'id': ident,
        'url': f'https://pobb.in/{ident}',
        # PoB2 registers a protocol handler for pob2:// links. Clicking this
        # opens the build directly in PoB2 (Import from URL flow).
        'pob2_url': f'pob2://pobbin/{ident}',
    }
