"""
Bluesky posting via AT Protocol. Supports an attached image (the WP chart).

Credentials come from environment (GitHub repo secrets):
    BSKY_HANDLE         e.g. squigglebaseball.bsky.social
    BSKY_APP_PASSWORD   an app password, NOT the account password
"""

from __future__ import annotations

import os
from atproto import Client


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


def post_with_image(text: str, image_path: str, alt: str = "") -> str:
    """Post text with a single attached image. Returns the post URI."""
    client = _client()
    with open(image_path, "rb") as f:
        img_bytes = f.read()
    resp = client.send_image(text=text, image=img_bytes, image_alt=alt)
    return resp.uri


def post_text(text: str) -> str:
    """Text-only post fallback. Returns the post URI."""
    client = _client()
    resp = client.send_post(text=text)
    return resp.uri
