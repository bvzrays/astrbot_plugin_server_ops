"""Media / file transfer tools."""
from dataclasses import dataclass, field
from astrbot.api.event import AstrMessageEvent
from .base import OpsTool
import httpx


@dataclass
class DownloadToServerTool(OpsTool):
    name: str = "download_to_server"
    description: str = "从 URL 下载文件/图片（自动识别消息中的图片链接），并通过 SFTP 传输至服务器指定路径。"
    parameters: dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "来源 URL"},
            "dest_path": {"type": "string", "description": "服务器目标绝对路径"}
        },
        "required": ["url", "dest_path"],
    })

    async def run(self, event: AstrMessageEvent, url: str, dest_path: str):
        if not self.ssh_mgr:
            return "SSH manager not available."
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.content
            return await self.ssh_mgr.upload_binary(data, dest_path)
        except Exception as e:
            return f"Download/Upload failed: {e}"
