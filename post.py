"""
Bluesky posting via AT Protocol. Supports an attached image (the WP chart).

Credentials come from environment (GitHub repo secrets):
    BSKY_HANDLE         e.g. squigglebaseball.bsky.social
    BSKY_APP_PASSWORD   an app password, NOT the account password
"""

from __future__ import annotations

import os
from atproto import Client, client_utils


def _client() -> Client:
    # Sanitize: a leading "@" or stray whitespace in the secret makes Bluesky
    # try to parse the handle as an email and fail with InvalidEmail.
    handle = os.environ["BSKY_HANDLE"].strip().lstrip("@")
    app_password = os.environ["BSKY_APP_PASSWORD"].strip()
    if not handle:
        raise ValueError("BSKY_HANDLE is empty after sanitizing — "
                         "set it to e.g. squigglebaseball.bsky.social (no @).")
    c = Client()
    c.login(handle, app_password)
    return c


def _build_richtext(text: str):
    """
    Convert plain text into a TextBuilder, turning #hashtag tokens into real
    Bluesky tag facets (clickable/searchable) while leaving the rest as text.
    """
    tb = client_utils.TextBuilder()
    for token in _tokenize(text):
        if token.startswith("#") and len(token) > 1:
            tb.tag(token, token[1:])     # display '#LAD', tag value 'LAD'
        else:
            tb.text(token)
    return tb


def _tokenize(text: str):
    """Split text but keep #hashtags as standalone tokens (with surrounding
    whitespace preserved as its own tokens)."""
    import re
    # split on hashtags while keeping delimiters
    parts = re.split(r"(#\w+)", text)
    return [p for p in parts if p != ""]


def post_with_image(text: str, image_path: str, alt: str = "") -> str:
    """Post text (with clickable hashtags) plus one attached image."""
    client = _client()
    with open(image_path, "rb") as f:
        img_bytes = f.read()
    tb = _build_richtext(text)
    resp = client.send_image(text=tb, image=img_bytes, image_alt=alt)
    return resp.uri


def post_text(text: str) -> str:
    """Text-only post fallback, with clickable hashtags. Returns the URI."""
    client = _client()
    resp = client.send_post(text=_build_richtext(text))
    return resp.uri
