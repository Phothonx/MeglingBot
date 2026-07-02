"""Small input-parsing helpers shared by the cogs."""

import re
import unicodedata
from urllib.parse import urlparse

import emoji as emoji_lib
from discord import PartialEmoji

CUSTOM_EMOJI_PATTERN = re.compile(r"<a?:\w+:\d+>")
SHORTCODE_PATTERN = re.compile(r":[\w+-]+:")


def parse_emoji(text: str) -> PartialEmoji | None:
    """Parse a custom discord emoji (<:name:id>), a unicode emoji, or a
    :shortcode: as copied from Discord's emoji picker."""
    text = text.strip()
    if CUSTOM_EMOJI_PATTERN.fullmatch(text):
        return PartialEmoji.from_str(text)
    if SHORTCODE_PATTERN.fullmatch(text):
        text = emoji_lib.emojize(text, language="alias")  # unknown names pass through
    if text and all(unicodedata.category(char) in {"So", "Sk", "Cf", "Mn"} for char in text):
        return PartialEmoji(name=text)
    return None


def valid_url(text: str | None) -> bool:
    """True for well-formed http(s) URLs — the only schemes Discord embeds accept."""
    if not text:
        return False
    parsed = urlparse(text.strip())
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)
