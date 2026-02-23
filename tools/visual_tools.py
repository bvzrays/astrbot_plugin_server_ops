"""Visual rendering tool — renders command output as an image."""
from dataclasses import dataclass, field
from astrbot.api.event import AstrMessageEvent
from .base import OpsTool


@dataclass
class RenderOutputTool(OpsTool):
    name: str = "render_output"
    description: str = (
        "执行 Shell 命令并将结果渲染为 VS Code 风格图片发送给用户。"
        "适用于：多行输出、目录树(tree)、日志查看(log)、文件内容(plain)。"
        "当输出超过 5 行时优先使用本工具替代纯文字回复。"
    )
    parameters: dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要执行的命令"},
            "title": {"type": "string", "description": "图片标题"},
            "mode": {
                "type": "string",
                "enum": ["tree", "log", "plain"],
                "description": "渲染模式: tree=目录树, log=日志, plain=普通文本"
            }
        },
        "required": ["command", "title", "mode"],
    })

    async def run(self, event: AstrMessageEvent, command: str, title: str, mode: str = "plain"):
        if not self.ssh_mgr or not self.plugin:
            return "Context error (ssh_mgr or plugin not set)."

        status, stdout, stderr = await self.ssh_mgr.execute_command(command)
        content = stdout if status == 0 else f"Exit {status}:\n{stderr}"

        if not content.strip():
            return "Command returned empty output."

        from ..utils.renderer import Renderer
        renderer = Renderer()
        tmpl, data = renderer.build_template(title, content, mode)

        img_url = await self.plugin.html_render(
            tmpl, data,
            options={"full_page": False, "scale": "device"}
        )
        await event.send(event.image_result(img_url))
        return f"Rendered '{title}' as image ({mode} mode)."
