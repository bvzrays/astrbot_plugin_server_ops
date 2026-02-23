from typing import Any, Optional, List
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


@dataclass(config=ConfigDict(arbitrary_types_allowed=True))
class RenderOutputTool(FunctionTool[AstrAgentContext]):
    """执行命令并将结果渲染为图片发送给用户。"""
    ssh_mgr: AsyncSSHManager = None
    plugin: Any = None # ServerOpsPlugin instance
    name: str = "render_output"
    description: str = (
        "执行命令并将输出渲染为图片发送给用户。"
        "当你认为输出内容较多、格式敏感（如目录树、代码、多行日志）或用户要求截图时使用。"
        "支持渲染模式：tree (目录树), log (多行日志), plain (普通文本)。"
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的命令，如 'ls -R' 或 'tail -n 100 /var/log/syslog'",
                },
                "title": {
                    "type": "string",
                    "description": "图片的标题，如 '目录结构' 或 'Nginx 日志'",
                },
                "mode": {
                    "type": "string",
                    "enum": ["tree", "log", "plain"],
                    "description": "渲染模式",
                }
            },
            "required": ["command", "title", "mode"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        **kwargs,
    ) -> ToolExecResult:
        if not self.ssh_mgr or not self.plugin:
            return "SSH or Plugin context not initialized."
        
        command = kwargs.get("command")
        title = kwargs.get("title")
        mode = kwargs.get("mode")
        event = context.context.event
        
        status, stdout, stderr = await self.ssh_mgr.execute_command(command)
        content = stdout if status == 0 else f"Err ({status}):\n{stderr}"
        
        if not content.strip():
            return "命令执行成功，但输出为空，未进行渲染。"

        # 根据模式处理内容
        subtitle = "Command Output"
        if mode == "tree":
             # 简单的 tree 模拟处理：为每一行添加图标
             lines = content.strip().split('\n')
             formatted_list = ""
             for line in lines:
                if not line: continue
                if line.endswith('/') or '/' in line[:5]:
                    formatted_list += f"<span style='color: #dcb67a;'>📁 {line}</span>\n"
                else:
                    formatted_list += f"<span style='color: #d4d4d4;'>📄 {line}</span>\n"
             content = formatted_list
             subtitle = "Directory Tree"
        elif mode == "log":
             # 日志样式：角色着色
             lines = content.strip().split('\n')
             log_content = ""
             for line in lines:
                 if "err" in line.lower() or "fail" in line.lower():
                     log_content += f"<div style='color: #f48771;'>{line}</div>"
                 elif "warn" in line.lower():
                     log_content += f"<div style='color: #cca700;'>{line}</div>"
                 else:
                     log_content += f"<div>{line}</div>"
             content = log_content
             subtitle = "Log Viewer"

        html = self.plugin._render_vs_code_style(title, content, subtitle)
        img_url = await self.plugin.html_render(html, {})
        await event.send(event.image_result(img_url))
        
        return f"已成功将 '{title}' 的结果渲染为图片并发送至用户。"


@dataclass(config=ConfigDict(arbitrary_types_allowed=True))
class LearnSkillTool(FunctionTool[AstrAgentContext]):
    """让 Agent 学习并记住一项操作技能。"""
    plugin: Any = None
    name: str = "learn_skill"
    description: str = (
        "学习并记住一项操作技能。当你完成了一个复杂任务，或者用户要求你'记住'某个操作时使用。"
        "这些记忆将在未来的对话中为你提供参考，直接告诉你如何执行特定任务。"
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "技能名称，如 '检查Nginx配置' 或 '重启Docker容器'",
                },
                "content": {
                    "type": "string",
                    "description": "技能的详细执行步骤、命令或注意事项（Markdown格式）",
                }
            },
            "required": ["skill_name", "content"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        **kwargs,
    ) -> ToolExecResult:
        if not self.plugin: return "Plugin context not initialized."
        
        name = kwargs.get("skill_name")
        content = kwargs.get("content")
        
        skills = await self.plugin.get_kv_data("ops_skills", {})
        skills[name] = content
        await self.plugin.put_kv_data("ops_skills", skills)
        
        return f"技能 '{name}' 已成功存入我的长期记忆。下次你询问相关任务时我将能直接应用此知识。"


@dataclass(config=ConfigDict(arbitrary_types_allowed=True))
class ListSkillsTool(FunctionTool[AstrAgentContext]):
    """查看已记录的技能列表。"""
    plugin: Any = None
    name: str = "list_skills"
    description: str = "如果你不确定自己学过哪些技能，可以使用此工具查看记忆库中的所有技能名称。"
    parameters: dict = Field(default_factory=lambda: {"type": "object", "properties": {}})

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        **kwargs,
    ) -> ToolExecResult:
        if not self.plugin: return "Plugin context not initialized."
        skills = await self.plugin.get_kv_data("ops_skills", {})
        if not skills:
            return "我的记忆库目前是空的，没有已学习的技能。"
        
        res = "我已学习的技能列表：\n"
        for i, name in enumerate(skills.keys(), 1):
            res += f"{i}. {name}\n"
        return res
