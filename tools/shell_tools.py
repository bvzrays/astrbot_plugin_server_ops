"""Shell execution tools."""
from dataclasses import dataclass, field
from astrbot.api.event import AstrMessageEvent
from .base import OpsTool


@dataclass
class ExecuteShellTool(OpsTool):
    name: str = "execute_shell"
    description: str = "在远程服务器执行非交互式 Shell 命令并返回结果。禁止使用 top/vim 等交互式命令。"
    parameters: dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要执行的 Shell 命令"},
            "timeout": {"type": "number", "description": "超时秒数，默认 30"}
        },
        "required": ["command"],
    })

    async def run(self, event: AstrMessageEvent, command: str, timeout: float = None):
        if not self.ssh_mgr:
            return "SSH manager not available."
        status, stdout, stderr = await self.ssh_mgr.execute_command(command, timeout=timeout)
        return f"Exit: {status}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"


@dataclass
class InstallPackageTool(OpsTool):
    name: str = "install_package"
    description: str = "在远程服务器安装软件包（自动确认 Y/N，超时 10 分钟）。"
    parameters: dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "安装指令，如 'apt install nginx'"}
        },
        "required": ["command"],
    })

    async def run(self, event: AstrMessageEvent, command: str):
        if not self.ssh_mgr:
            return "SSH manager not available."
        status, stdout, stderr = await self.ssh_mgr.execute_install(command)
        return f"Exit: {status}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
