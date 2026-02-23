import re
import asyncio
from pathlib import Path

from astrbot.api.star import Star, register
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api import logger, ToolSet
from astrbot.api.all import Context
import astrbot.api.message_components as Comp
from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.message.message_event_result import MessageChain

# Core architecture
from .core.ssh import AsyncSSHManager
from .core.context_builder import ContextBuilder
from .core.memory import MemoryStore

# Tools (all @dataclass + run(event, ...) AstrBot API)
from .tools.shell_tools import ExecuteShellTool, InstallPackageTool
from .tools.file_tools import ReadFileTool, WriteFileTool
from .tools.media_tools import DownloadToServerTool
from .tools.memory_tools import (
    LearnSkillTool, ListSkillsTool, UpdateMemoryTool, SearchHistoryTool
)
from .tools.visual_tools import RenderOutputTool
from .tools.web_tools import WebSearchTool, WebFetchTool

# Utils
from .utils.renderer import Renderer


class OpsProgressHooks(BaseAgentRunHooks[AstrAgentContext]):
    """Sends tool call progress messages to the QQ chat."""

    # Map tool name → emoji
    _ICONS = {
        "execute_shell": "⚡",
        "install_package": "📦",
        "read_file": "📖",
        "write_file": "✏️",
        "download_to_server": "⬇️",
        "render_output": "🖼️",
        "update_memory": "🧠",
        "search_history": "🔍",
        "learn_skill": "📚",
        "list_skills": "📋",
        "web_search": "🌐",
        "web_fetch": "🌐",
    }

    async def on_tool_start(self, run_context, tool, tool_args: dict):
        event = run_context.context.event
        icon = self._ICONS.get(tool.name, "🔨")
        lines = [f"{icon} 调用工具: **{tool.name}**"]
        # Show key arg as a hint
        hint_key = next(
            (k for k in ("command", "filepath", "query", "url", "skill_name") if k in tool_args),
            None,
        )
        if hint_key and tool_args[hint_key]:
            val = str(tool_args[hint_key])[:150]
            lines.append(f"```\n{val}\n```")
        try:
            await event.send(MessageChain().message("\n".join(lines)))
        except Exception:
            pass  # Never let hooks crash the agent


@register("astrbot_plugin_server_ops", "bvzrays", "模块化服务器运维 AI Agent (Nanobot 架构)", "3.0.0")
class ServerOpsPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self.config = config or {}
        self.ssh_mgr: "AsyncSSHManager | None" = None
        self._ctx_builder: "ContextBuilder | None" = None

    async def terminate(self):
        if self.ssh_mgr and getattr(self.ssh_mgr, '_conn', None):
            try:
                self.ssh_mgr._conn.close()
                await self.ssh_mgr._conn.wait_closed()
            except Exception:
                pass
            self.ssh_mgr._conn = None

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    def _get_workspace(self) -> Path:
        ws_raw = self.config.get("agent_workspace", "").strip()
        if ws_raw:
            return Path(ws_raw)
        try:
            return Path(self.context.get_data_dir()) / "server_ops_workspace"
        except Exception:
            return Path("data/server_ops_workspace")

    def _init_ssh(self):
        if not self.ssh_mgr:
            self.ssh_mgr = AsyncSSHManager(
                host=self.config.get("ssh_host", "127.0.0.1"),
                port=self.config.get("ssh_port", 22),
                username=self.config.get("ssh_username", "root"),
                password=self.config.get("ssh_password"),
                key_path=self.config.get("ssh_key_path"),
                passphrase=self.config.get("ssh_key_passphrase"),
                default_timeout=self.config.get("cmd_default_timeout", 30),
                output_max_chars=self.config.get("output_max_chars", 4000),
            )

    def _check_permission(self, event: AstrMessageEvent) -> bool:
        if event.is_admin():
            return True
        uid = str(event.get_sender_id())
        allowed = [u.strip() for u in self.config.get("allowed_users", "").split(",") if u.strip()]
        return not allowed or uid in allowed

    def _make_tool(self, cls, workspace, **extra):
        """Construct a tool and inject context."""
        t = cls()
        t.ssh_mgr = self.ssh_mgr
        t.plugin = self
        t.workspace = workspace
        for k, v in extra.items():
            setattr(t, k, v)
        return t

    def _build_toolset(self, workspace: Path) -> ToolSet:
        mk = lambda cls, **kw: self._make_tool(cls, workspace, **kw)
        tools = [
            mk(ExecuteShellTool),
            mk(InstallPackageTool),
            mk(ReadFileTool),
            mk(WriteFileTool),
            mk(DownloadToServerTool),
            mk(RenderOutputTool),
            mk(UpdateMemoryTool),
            mk(SearchHistoryTool),
            mk(LearnSkillTool),
            mk(ListSkillsTool),
            mk(WebFetchTool, max_chars=self.config.get("web_fetch_max_chars", 10000)),
        ]
        web_key = self.config.get("web_search_api_key", "").strip()
        if web_key:
            tools.append(mk(WebSearchTool, api_key=web_key))
        return ToolSet(tools)

    async def _extract_image_urls(self, event: AstrMessageEvent):
        urls = []
        try:
            for seg in event.get_messages():
                if isinstance(seg, Comp.Image):
                    url = getattr(seg, 'url', None) or getattr(seg, 'file', None)
                    if url and str(url).startswith("http"):
                        urls.append(str(url))
        except Exception:
            pass
        return urls

    # ------------------------------------------------------------------ #
    #  /ops — Main Agent Command                                           #
    # ------------------------------------------------------------------ #

    @filter.command("ops")
    async def ops(self, event: AstrMessageEvent):
        """通过自然语言执行服务器运维任务。"""
        if not self._check_permission(event):
            yield event.plain_result("❌ 你没有使用运维 Agent 的权限。")
            return

        query = re.sub(r'^([/*!]\s*)?ops\s*', '', event.message_str, flags=re.IGNORECASE).strip()
        if not query:
            yield event.plain_result("请输入任务，如：/ops 检查 nginx 状态")
            return

        self._init_ssh()
        workspace = self._get_workspace()
        workspace.mkdir(parents=True, exist_ok=True)

        agent_name = self.config.get("agent_name", "OpsBot")

        # Build context & system prompt via ContextBuilder
        if not self._ctx_builder:
            self._ctx_builder = ContextBuilder(workspace, agent_name=agent_name)

        ops_skills = await self.get_kv_data("ops_skills", {})
        extra = ""
        if ops_skills:
            extra = "## Remembered Workflows\n" + "\n".join(
                f"- **{k}**: {v}" for k, v in ops_skills.items()
            )
        system_prompt = self._ctx_builder.build_system_prompt(
            ssh_host=self.config.get("ssh_host", ""),
            ssh_user=self.config.get("ssh_username", ""),
            extra_context=extra,
        )

        # Build ToolSet
        tool_set = self._build_toolset(workspace)

        # Image URLs for vision LLMs
        image_urls = await self._extract_image_urls(event)

        umo = event.unified_msg_origin

        # Get provider ID
        try:
            provider_id = await self.context.get_current_chat_provider_id(umo)
        except Exception as e:
            yield event.plain_result(f"❌ 无法获取 LLM 提供商：{e}\n请先在 AstrBot 中配置模型。")
            return

        yield event.plain_result(f"🚀 {agent_name} 启动：{query}")

        try:
            # ── THE KEY FIX: use AstrBot's built-in tool loop agent ──────────
            # This handles: LLM call → detect tool_calls → execute → feed back → repeat
            show_progress = self.config.get("show_progress", True)
            llm_resp = await self.context.tool_loop_agent(
                event=event,
                chat_provider_id=provider_id,
                prompt=query,
                image_urls=image_urls if image_urls else [],
                tools=tool_set,
                system_prompt=system_prompt,
                max_steps=self.config.get("max_iterations", 40),
                tool_call_timeout=self.config.get("cmd_default_timeout", 60),
                # Pass custom hooks → sends progress msgs to QQ chat
                agent_hooks=OpsProgressHooks() if show_progress else None,
            )

            if llm_resp and llm_resp.completion_text:
                yield event.plain_result(llm_resp.completion_text)
            elif not llm_resp:
                yield event.plain_result("⚠️ Agent 未返回最终响应。")

            # Background memory consolidation
            asyncio.create_task(self._maybe_consolidate(umo, workspace))

        except Exception as e:
            logger.exception(f"[ServerOps] ops error: {e}")
            yield event.plain_result(f"❌ 执行异常: {e}")

    async def _maybe_consolidate(self, umo: str, workspace: Path):
        """Consolidate conversation history to MEMORY.md if threshold reached."""
        try:
            conv_mgr = self.context.conversation_manager
            curr_cid = await conv_mgr.get_curr_conversation_id(umo)
            if not curr_cid:
                return
            conversation = await conv_mgr.get_conversation(umo, curr_cid)
            if not conversation:
                return
            import json
            history = json.loads(conversation.history or "[]")
            mem_window = self.config.get("memory_window", 50)
            if len(history) < mem_window:
                return
            store = MemoryStore(workspace)
            provider = self.context.get_using_provider(umo)
            if provider:
                await store.consolidate(history, provider, "")
                logger.info("[ServerOps] Memory consolidation complete.")
        except Exception as e:
            logger.warning(f"[ServerOps] Memory consolidation error: {e}")

    # ------------------------------------------------------------------ #
    #  Utility commands                                                    #
    # ------------------------------------------------------------------ #

    async def _render_and_send(self, event, title, content, mode):
        renderer = Renderer()
        tmpl, data = renderer.build_template(title, content, mode)
        try:
            img_url = await self.html_render(
                tmpl, data,
                options={"full_page": False, "scale": "device"}
            )
            yield event.image_result(img_url)
        except Exception:
            yield event.plain_result(content[:2000])

    @filter.command("ops_ls")
    async def ops_ls(self, event: AstrMessageEvent):
        path = re.sub(r'^([/*!]\s*)?ops_ls\s*', '', event.message_str, flags=re.IGNORECASE).strip() or "."
        self._init_ssh()
        status, stdout, stderr = await self.ssh_mgr.execute_command(f"ls -F {path}")
        if status != 0:
            yield event.plain_result(f"Error: {stderr}")
            return
        async for msg in self._render_and_send(event, f"📂 {path}", stdout, "tree"):
            yield msg

    @filter.command("ops_cat")
    async def ops_cat(self, event: AstrMessageEvent):
        path = re.sub(r'^([/*!]\s*)?ops_cat\s*', '', event.message_str, flags=re.IGNORECASE).strip()
        if not path:
            yield event.plain_result("用法：/ops_cat <路径>")
            return
        self._init_ssh()
        content = await self.ssh_mgr.read_file(path)
        async for msg in self._render_and_send(event, f"📄 {path}", content, "plain"):
            yield msg

    @filter.command("ops_memory")
    async def ops_memory(self, event: AstrMessageEvent):
        """查看 Agent 的长期记忆（MEMORY.md）。"""
        store = MemoryStore(self._get_workspace())
        mem = store.read_memory()
        if not mem:
            yield event.plain_result("📭 记忆库为空。")
            return
        async for msg in self._render_and_send(event, "🧠 Long-term Memory", mem, "plain"):
            yield msg

    @filter.command("ops_skills")
    async def ops_skills(self, event: AstrMessageEvent):
        """查看所有技能（SKILL.md + KV skills）。"""
        ws = self._get_workspace()
        from .core.skills import SkillsLoader
        loader = SkillsLoader(ws)
        file_skills = loader.list_skills()
        kv_skills = await self.get_kv_data("ops_skills", {})

        lines = []
        if file_skills:
            lines.append("## SKILL.md 技能")
            for s in file_skills:
                meta = loader.get_skill_metadata(s["name"])
                lines.append(f"- **{s['name']}** [{s['source']}]: {meta.get('description', '')}")
        if kv_skills:
            lines.append("\n## KV 记忆技能")
            for k in kv_skills:
                lines.append(f"- **{k}**")

        if not lines:
            yield event.plain_result("技能库为空。")
            return
        async for msg in self._render_and_send(event, "📚 Skills Library", "\n".join(lines), "plain"):
            yield msg

    @filter.command("ops_forget")
    async def ops_forget(self, event: AstrMessageEvent):
        name = re.sub(r'^([/*!]\s*)?ops_forget\s*', '', event.message_str, flags=re.IGNORECASE).strip()
        skills = await self.get_kv_data("ops_skills", {})
        if name in skills:
            del skills[name]
            await self.put_kv_data("ops_skills", skills)
            yield event.plain_result(f"✅ 已移除技能：{name}")
        else:
            yield event.plain_result(f"⚠️ 未找到技能：{name}")

    @filter.command("ops_clear")
    async def ops_clear(self, event: AstrMessageEvent):
        """在 AstrBot 中新建一条对话（清除上下文）。"""
        umo = event.unified_msg_origin
        conv_mgr = self.context.conversation_manager
        await conv_mgr.new_conversation(umo)
        yield event.plain_result("✅ 已开启新对话，上下文已重置。")

    @filter.command("ops_test")
    async def ops_test(self, event: AstrMessageEvent):
        yield event.plain_result(f"🔍 测试 SSH 连接：{self.config.get('ssh_host', '(未配置)')}…")
        try:
            self._init_ssh()
            await self.ssh_mgr._get_conn()
            yield event.plain_result("✅ SSH 连接成功！")
        except Exception as e:
            yield event.plain_result(f"❌ 连接失败: {e}")
