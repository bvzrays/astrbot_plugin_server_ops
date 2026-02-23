"""Memory tools: KV-based skill store (backward compat) + long-term MEMORY.md."""
from dataclasses import dataclass, field
from astrbot.api.event import AstrMessageEvent
from .base import OpsTool


@dataclass
class LearnSkillTool(OpsTool):
    name: str = "learn_skill"
    description: str = (
        "将高价值运维流程或配置方案保存到 KV 技能库（供下次会话快速调用）。"
        "仅适用于：多步骤工作流、复杂 API 调用、一键管理流程。"
        "禁止记录：ls/cd/cat 等基础命令。"
    )
    parameters: dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "skill_name": {"type": "string", "description": "技能名称（简短英文标识）"},
            "content": {"type": "string", "description": "Markdown 格式的详细步骤"}
        },
        "required": ["skill_name", "content"],
    })

    async def run(self, event: AstrMessageEvent, skill_name: str, content: str):
        if not self.plugin:
            return "Plugin context not available."
        skills = await self.plugin.get_kv_data("ops_skills", {})
        skills[skill_name] = content
        await self.plugin.put_kv_data("ops_skills", skills)
        return f"Skill '{skill_name}' saved to memory."


@dataclass
class ListSkillsTool(OpsTool):
    name: str = "list_skills"
    description: str = "列出 KV 技能库中所有已保存的技能名称。"
    parameters: dict = field(default_factory=lambda: {"type": "object", "properties": {}})

    async def run(self, event: AstrMessageEvent):
        if not self.plugin:
            return "Plugin context not available."
        skills = await self.plugin.get_kv_data("ops_skills", {})
        if not skills:
            return "No KV skills saved yet."
        return "Saved KV skills: " + ", ".join(skills.keys())


@dataclass
class UpdateMemoryTool(OpsTool):
    name: str = "update_memory"
    description: str = (
        "将重要的服务器事实写入长期记忆文件（MEMORY.md）。"
        "应记录：服务端口、部署路径、API 端点、项目配置等长期有效信息。"
    )
    parameters: dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "要追加写入 MEMORY.md 的 Markdown 内容"}
        },
        "required": ["content"],
    })

    async def run(self, event: AstrMessageEvent, content: str):
        if not self.workspace:
            return "Workspace not configured."
        from ..core.memory import MemoryStore
        store = MemoryStore(self.workspace)
        existing = store.read_memory()
        store.write_memory((existing + "\n\n" + content).strip())
        return "Memory updated successfully."


@dataclass
class SearchHistoryTool(OpsTool):
    name: str = "search_history"
    description: str = "在过往会话历史（HISTORY.md）中搜索关键词，找出之前做过的操作。"
    parameters: dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "搜索关键词"}
        },
        "required": ["pattern"],
    })

    async def run(self, event: AstrMessageEvent, pattern: str):
        if not self.workspace:
            return "Workspace not configured."
        from ..core.memory import MemoryStore
        return MemoryStore(self.workspace).search_history(pattern)
