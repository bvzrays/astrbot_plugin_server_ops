"""File read/write tools."""
from dataclasses import dataclass, field
from astrbot.api.event import AstrMessageEvent
from .base import OpsTool


@dataclass
class ReadFileTool(OpsTool):
    name: str = "read_file"
    description: str = "读取远程服务器上指定路径的文件内容。"
    parameters: dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "filepath": {"type": "string", "description": "文件绝对路径"}
        },
        "required": ["filepath"],
    })

    async def run(self, event: AstrMessageEvent, filepath: str):
        if not self.ssh_mgr:
            return "SSH manager not available."
        return await self.ssh_mgr.read_file(filepath)


@dataclass
class WriteFileTool(OpsTool):
    name: str = "write_file"
    description: str = "向远程服务器写入或覆盖文本文件内容。"
    parameters: dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "filepath": {"type": "string", "description": "目标绝对路径"},
            "content": {"type": "string", "description": "文本内容"}
        },
        "required": ["filepath", "content"],
    })

    async def run(self, event: AstrMessageEvent, filepath: str, content: str):
        if not self.ssh_mgr:
            return "SSH manager not available."
        return await self.ssh_mgr.write_file(filepath, content)
