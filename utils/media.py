"""Media utilities: extract image URLs from AstrBot message objects."""

from typing import List, Optional
from astrbot.api.event import AstrMessageEvent
from astrbot.core.message.components import Image


async def extract_image_urls(event: AstrMessageEvent) -> List[str]:
    """Extract all image URLs from an AstrBot message event."""
    urls: List[str] = []
    try:
        for seg in event.get_messages():
            if isinstance(seg, Image):
                url = getattr(seg, 'url', None) or getattr(seg, 'file', None)
                if url and url.startswith("http"):
                    urls.append(url)
    except Exception:
        pass
    return urls
