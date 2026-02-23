from typing import Any, Optional
from pydantic import Field, ConfigDict
from pydantic.dataclasses import dataclass
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from .ssh_manager import AsyncSSHManager

@dataclass(config=ConfigDict(arbitrary_types_allowed=True))
class ExecuteShellTool(FunctionTool[AstrAgentContext]):
    ssh_mgr: AsyncSSHManager = None
    name: str = "execute_shell"
    description: str = (
        "在远程服务器执行非交互式 Shell 命令。"
        "适用于：查看状态、检查配置、运行脚本等普通命令。"
        "如果是安装软件包，请使用 install_package 工具，它有更长的超时时间。"
        "禁止执行：top、htop、nano、vi、vim 等交互式命令。"
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的非交互式 Shell 命令",
                },
                "timeout": {
                    "type": "integer",
                    "description": "命令超时秒数（可选，默认使用系统配置）",
                }
            },
            "required": ["command"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        **kwargs,
    ) -> ToolExecResult:
        ssh_mgr = self.ssh_mgr
        if not ssh_mgr:
            return "SSHManager not initialized."

        command = kwargs.get("command")
        timeout = kwargs.get("timeout")  # None if not provided
        status, stdout, stderr = await ssh_mgr.execute_command(command, timeout=timeout)

        result = f"Exit Status: {status}\n"
        if stdout:
            result += f"STDOUT:\n{stdout}\n"
        if stderr:
            result += f"STDERR:\n{stderr}\n"
        if not stdout and not stderr:
            result += "(No output)\n"
        return result


@dataclass(config=ConfigDict(arbitrary_types_allowed=True))
class InstallPackageTool(FunctionTool[AstrAgentContext]):
    """专门用于自动化安装软件包，自动处理交互式确认，使用长超时。"""
    ssh_mgr: AsyncSSHManager = None
    install_timeout: int = 600
    name: str = "install_package"
    description: str = (
        "在远程服务器安装软件包或执行一键安装脚本。"
        "自动处理交互式确认提示（如 apt 的 Yes/No），超时时间长达600秒。"
        "适用于：apt install、yum install、curl|bash 安装脚本、pip install 等。"
        "不适用于：需要手动交互填写配置的安装向导（如 MySQL 初始化向导）。"
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "软件安装命令，例如：'apt install -y nginx' 或 'curl -sSL https://example.com/install.sh | bash'",
                }
            },
            "required": ["command"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        **kwargs,
    ) -> ToolExecResult:
        ssh_mgr = self.ssh_mgr
        if not ssh_mgr:
            return "SSHManager not initialized."

        command = kwargs.get("command")
        status, stdout, stderr = await ssh_mgr.execute_install(command, timeout=self.install_timeout)

        result = f"Exit Status: {status}\n"
        if stdout:
            result += f"STDOUT:\n{stdout}\n"
        if stderr:
            result += f"STDERR:\n{stderr}\n"
        if not stdout and not stderr:
            result += "(No output — installation may have completed silently)\n"
        return result


@dataclass(config=ConfigDict(arbitrary_types_allowed=True))
class ReadFileTool(FunctionTool[AstrAgentContext]):
    ssh_mgr: AsyncSSHManager = None
    name: str = "read_file"
    description: str = "读取服务器上指定路径的文件内容。适用于查看配置文件、日志、脚本等。"
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "文件绝对路径，例如：/etc/nginx/nginx.conf",
                }
            },
            "required": ["filepath"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        **kwargs,
    ) -> ToolExecResult:
        ssh_mgr = self.ssh_mgr
        if not ssh_mgr:
            return "SSHManager not initialized."

        filepath = kwargs.get("filepath")
        content = await ssh_mgr.read_file(filepath)
        return content


@dataclass(config=ConfigDict(arbitrary_types_allowed=True))
class WriteFileTool(FunctionTool[AstrAgentContext]):
    ssh_mgr: AsyncSSHManager = None
    name: str = "write_file"
    description: str = "向服务器写入或覆盖文件内容。可用于写配置文件、HTML、脚本等。父目录不存在时会自动创建。"
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "目标文件绝对路径，例如：/var/www/html/index.html",
                },
                "content": {
                    "type": "string",
                    "description": "要写入的文件内容（完整内容，将覆盖原文件）",
                }
            },
            "required": ["filepath", "content"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        **kwargs,
    ) -> ToolExecResult:
        ssh_mgr = self.ssh_mgr
        if not ssh_mgr:
            return "SSHManager not initialized."

        filepath = kwargs.get("filepath")
        content = kwargs.get("content")
        res = await ssh_mgr.write_file(filepath, content)
        return res
