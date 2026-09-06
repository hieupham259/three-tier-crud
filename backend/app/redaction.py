"""Helpers that keep MongoDB credentials out of logs and error messages."""

from __future__ import annotations

import re

# userinfo of a MongoDB connection string: the user and password that precede the "@" host part
_URI_USERINFO = re.compile(r"(?i)(mongodb(?:\+srv)?://)([^/?#@\s]+)@")


def redact(text: str) -> str:
    """Replace any ``user:password@`` segment of a MongoDB URI inside *text* with ``***@``."""
    return _URI_USERINFO.sub(r"\1***@", text)


def describe_uri(uri: str) -> str:
    """Return ``scheme://hosts/database`` for logging: no credentials, no query options."""
    scheme, separator, rest = uri.partition("://")
    if not separator:
        return "<invalid-uri>"
    authority, _, tail = rest.partition("/")
    hosts = authority.rsplit("@", 1)[-1]
    database = tail.partition("?")[0]
    return f"{scheme}://{hosts}/{database}"
