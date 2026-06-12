"""
Bluesky posting via AT Protocol. Mirrors the Cmon Blue flow.

Credentials come from environment (GitHub repo secrets):
    BSKY_HANDLE     e.g. squiggle.bsky.social
    BSKY_APP_PASSWORD   an app password, NOT the account password
"""

from __future__ import annotations

import os
from atproto import Client


def post_to_bluesky(text: str) -> str:
    handle = os.environ["BSKY_HANDLE"]
    app_password = os.environ["BSKY_APP_PASSWORD"]
    client = Client()
    client.login(handle, app_password)
    resp = client.send_post(text=text)
    return resp.uri
