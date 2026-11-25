"""URL helpers shared by the deduplicate node and the database."""

import hashlib
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# Query-string parameters that only track where a click came from, never which job it is.
# Any other parameter is kept, because some sites identify jobs with e.g. ?id=123.
TRACKING_PARAMS = {"gclid", "fbclid", "ref", "referrer", "source", "src", "trk", "trackingid"}


def normalize_url(url: str) -> str:
    """Canonical form of a URL, so that two links to the same job look identical."""
    parts = urlparse(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    query = sorted(
        (key, value)
        for key, value in parse_qsl(parts.query)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMS
    )
    return urlunparse(
        (parts.scheme.lower() or "https", host, parts.path.rstrip("/"), "", urlencode(query), "")
    )


def job_id(url: str) -> str:
    """Short, stable id for a job: a hash of its normalized URL."""
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()[:16]
