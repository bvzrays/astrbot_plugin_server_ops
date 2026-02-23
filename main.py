import re
import traceback
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.core.agent.tool import ToolSet
from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.agent.message import Message
from astrbot.core.astr_agent_context import AgentContextWrapper, AstrAgentContext
from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
from .tools_config import (
    ExecuteShellTool, ReadFileTool, WriteFileTool, InstallPackageTool,
    RenderOutputTool, LearnSkillTool, ListSkillsTool
)

class OpsAgentHooks(BaseAgentRunHooks):
    """
    运维 Agent 的运行时钩子，优化 v3.1：兼顾降噪与进度反馈。
    """
    def __init__(self, event: AstrMessageEvent, show_thought: bool = True):
        self.event = event
        self.show_thought = show_thought

    async def on_tool_start(self, run_context: ContextWrapper, tool: FunctionTool, tool_args: dict | None) -> None:
        # v3 降噪反馈：只发送一条简洁的执行状态
        msg = f"⚙️ 正在执行：{tool.name}"
        # 尝试从描述中提取更友好的人文描述
        if "检查" in tool.description: msg = "🔍 正在检查服务器状态..."
        elif "安装" in tool.description: msg = "📦 正在安装组件..."
        elif "写入" in tool.description: msg = "📝 正在更新配置文件..."
        elif "读取" in tool.description: msg = "📖 正在读取系统文件..."
        elif "render" in tool.name: msg = "🎨 正在生成并渲染执行截图..."
        elif "learn" in tool.name: msg = "🧠 正在将此操作步骤记入长期记忆..."
        
        await self.event.send(self.event.plain_result(msg))

    async def on_tool_end(self, run_context: ContextWrapper, tool: FunctionTool, tool_args: dict | None, tool_result: any) -> None:
        # v3 降噪：结束时不发独立消息
        pass

@register("astrbot_plugin_server_ops", "bvzrays", "基于 LLM 的远程服务器运维 Agent", "1.1.0")
class ServerOpsPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.ssh_mgr = None

    async def terminate(self):
        """摧毁插件实例时关闭 SSH 连接"""
        if self.ssh_mgr and self.ssh_mgr._conn:
            self.ssh_mgr._conn.close()
            await self.ssh_mgr._conn.wait_closed()
            self.ssh_mgr._conn = None

    async def _check_permission(self, event: AstrMessageEvent, config: dict) -> bool:
        """检查用户权限：管理员或白名单"""
        if event.is_admin():
            return True
        allowed = config.get("allowed_users", "").strip()
        if allowed:
            allowed_list = [uid.strip() for uid in allowed.split(",")]
            if str(event.get_sender_id()) in allowed_list:
                return True
        return False

    async def _get_ops_config(self):
        metadata = self.context.get_registered_star("astrbot_plugin_server_ops")
        config = metadata.config if metadata and metadata.config else {}
        if not config:
            config = self.context.get_config()
        return config

    async def _init_ssh(self, config, force=False):
        if not self.ssh_mgr or force:
            self.ssh_mgr = AsyncSSHManager(
                host=config.get("ssh_host", "127.0.0.1"),
                port=config.get("ssh_port", 22),
                username=config.get("ssh_username", "root"),
                password=config.get("ssh_password"),
                key_path=config.get("ssh_key_path"),
                passphrase=config.get("ssh_key_passphrase"),
                default_timeout=config.get("cmd_default_timeout", 30),
                output_max_chars=config.get("output_max_chars", 3000)
            )
        return self.ssh_mgr

    @filter.command("ops")
    async def ops(self, event: AstrMessageEvent):
        """通过自然语言执行运维任务。"""
        logger.debug(f"Ops command triggered with message: {event.message_str}")
        config = await self._get_ops_config()
        if not await self._check_permission(event, config):
            yield event.plain_result("抱歉，您没有使用运维 Agent 的权限。")
            return

        # 彻底剥离指令前缀和指令名
        query = re.sub(r'^([/*!]\s*)?ops\s*', '', event.message_str, flags=re.IGNORECASE).strip()
        if not query:
            yield event.plain_result("请输入运维任务描述，例如：/ops 查看系统负载")
            return

        # 初始化 SSH 连接
        self.ssh_mgr = await self._init_ssh(config)
        yield event.plain_result(f"🚀 运维 Agent 已启动：{query}")

        # 背景知识：加载已学习的 Skills
        skills = await self.get_kv_data("ops_skills", {})
        skills_prompt = ""
        if skills:
            skills_prompt = "\n\n你已掌握的特定操作技能（Skill Memory）：\n"
            for name, content in skills.items():
                skills_prompt += f"### {name}\n{content}\n\n"

        # System Prompt 设定 (v3.2 全能增强版)
        system_prompt = (
            "你是一个极简、高效的远程服务器运维专家。你被集成在 AstrBot 平台中。\n"
            "你的唯一任务是：使用提供的 SSH 工具**立即**执行操作，严禁废话。\n\n"
            "核心指令：\n"
            "1. **行动优先**：收到任务后，你必须在第一回合就调用工具。\n"
            "2. **可视化优先**：当任务涉及展示目录结构(如ls -R)或查看多行日志(如tail)时，必须优先使用 `render_output` 工具将其渲染为图片，而不是发送长文字。\n"
            "3. **长期记忆**：当你完成了一个相对复杂或用户明确要求的任务后，应主动调用 `learn_skill` 工具将关键步骤记入你的记忆库。\n"
            "4. **探针逻辑**：如果不确定服务器状态，先用探测工具调研再做决策。\n"
            "5. **简洁反馈**：每一个回合，你只需要给出一句非常简短的当前动作说明，然后立即调用工具。\n"
            f"{skills_prompt}"
        )

        # 准备工具集
        tools = ToolSet([
            ExecuteShellTool(ssh_mgr=self.ssh_mgr),
            ReadFileTool(ssh_mgr=self.ssh_mgr),
            WriteFileTool(ssh_mgr=self.ssh_mgr),
            InstallPackageTool(ssh_mgr=self.ssh_mgr, install_timeout=config.get("install_timeout", 600)),
            RenderOutputTool(ssh_mgr=self.ssh_mgr, plugin=self),
            LearnSkillTool(plugin=self),
            ListSkillsTool(plugin=self)
        ])

        try:
            # 3. 持续会话隔离：使用 ops_history 前缀
            user_id = event.get_sender_id()
            history_key = f"ops_history_{user_id}"
            history_data = await self.get_kv_data(history_key, []) or []
            
            messages = []
            for m in history_data:
                if m.get('role') == 'user':
                    messages.append(Message(role='user', content=m['content']))

            hooks = OpsAgentHooks(event, show_thought=config.get("show_thought", True))
            umo = event.unified_msg_origin
            prov_id = await self.context.get_current_chat_provider_id(umo)
            prov = await self.context.provider_manager.get_provider_by_id(prov_id)
            
            agent_context = AstrAgentContext(context=self.context, event=event)
            agent_runner = ToolLoopAgentRunner()
            tool_executor = FunctionToolExecutor()
            
            await agent_runner.reset(
                provider=prov,
                request=ProviderRequest(
                    system_prompt=system_prompt,
                    prompt=query,
                    contexts=messages,
                    func_tool=tools 
                ),
                run_context=AgentContextWrapper(
                    context=agent_context,
                    tool_call_timeout=config.get("agent_timeout", 60),
                ),
                tool_executor=tool_executor,
                agent_hooks=hooks
            )

            async for resp in agent_runner.step_until_done(config.get("max_steps", 15)):
                if resp.type == "llm_result":
                    content = resp.data["chain"].get_plain_text().strip()
                    if not content: continue
                    is_final = agent_runner.done() or any(kw in content for kw in ["完成", "总结", "已经", "成功", "失败"])
                    if is_final:
                        yield event.plain_result(f"🏁 任务总结:\n{content}")
                    else:
                        yield event.plain_result(f"💡 Agent：{content}")

            # 4. 保存对话历史
            current_msgs = agent_runner.run_context.messages
            new_history = [{"role": m.role, "content": (m.content[0].text if isinstance(m.content, list) else str(m.content))} 
                           for m in current_msgs if m.role in ["user", "assistant"]]
            
            max_turns = config.get("history_max_turns", 10)
            if len(new_history) > max_turns * 2: new_history = new_history[-(max_turns * 2):]
            await self.put_kv_data(history_key, new_history)

        except Exception as e:
            logger.error(f"Ops Agent Error: {traceback.format_exc()}")
            yield event.plain_result(f"❌ 运维执行出错: {str(e)}")

    @filter.command("ops_clear")
    async def ops_clear(self, event: AstrMessageEvent):
        """清空当前运维会话的历史记忆。"""
        user_id = event.get_sender_id()
        history_key = f"ops_history_{user_id}"
        await self.put_kv_data(history_key, [])
        yield event.plain_result("✅ 运维对话隔离记忆已清空。")

    @filter.command("ops_test")
    async def ops_test(self, event: AstrMessageEvent):
        """测试 SSH 连接并返回详细诊断。"""
        config = await self._get_ops_config()
        if not await self._check_permission(event, config):
            yield event.plain_result("无权限。")
            return
        
        yield event.plain_result(f"🔍 正在启动 SSH 连接诊断 (Target: {config.get('ssh_host')})...\n(注: 为了兼容性，已强制仅使用密码认证并延长握手等待时间)")
        
        try:
            ssh = await self._init_ssh(config, force=True)
            status, stdout, stderr = await ssh.execute_command("echo 'SSH_TEST_SUCCESS'")
        except Exception as e:
            status, stdout, stderr = -1, "", str(e)

        if status == 0 and "SSH_TEST_SUCCESS" in stdout:
            yield event.plain_result("✅ SSH 连接成功！服务器响应正常。")
        else:
            diag_msg = f"❌ SSH 连接失败。\n\n[精细化诊断]:\n{stderr}\n\n[配置盘点]:\n- Host: {config.get('ssh_host')}\n- Port: {config.get('ssh_port')}\n- User: {config.get('ssh_username')}\n- Auth: Password"
            yield event.plain_result(diag_msg)

    def _render_vs_code_style(self, title: str, content: str, subtitle: str = "") -> str:
        """统一渲染 VS Code 风格的 HTML"""
        return f"""
        <div style="background: #1e1e1e; color: #d4d4d4; padding: 15px; font-family: 'Segoe UI', 'Consolas', monospace; border-radius: 8px; border: 1px solid #333; box-shadow: 0 4px 12px rgba(0,0,0,0.5);">
            <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #333; padding-bottom: 8px; margin-bottom: 12px;">
                <span style="color: #4ec9b0; font-weight: bold; font-size: 13px;">{title}</span>
                <span style="color: #6a9955; font-size: 11px;">{subtitle}</span>
            </div>
            <pre style="margin: 0; white-space: pre-wrap; word-wrap: break-word; font-size: 13px; line-height: 1.5;">{content}</pre>
        </div>
        """

    @filter.command("ops_cat")
    async def ops_cat(self, event: AstrMessageEvent):
        """查看服务器文件内容并渲染为图片。用法：/ops_cat <路径>"""
        logger.debug(f"Ops_cat triggered with message: {event.message_str}")
        config = await self._get_ops_config()
        if not await self._check_permission(event, config):
            yield event.plain_result("无权限。")
            return
        
        path = event.message_str
        for prefix_cmd in ["/ops_cat", "*ops_cat", "!ops_cat", "ops_cat"]:
            if path.startswith(prefix_cmd):
                path = path[len(prefix_cmd):].strip()
                break
                
        if not path:
            yield event.plain_result("请输入文件路径。")
            return
        
        ssh = await self._init_ssh(config)
        content = await ssh.read_file(path)
        
        if config.get("render_file_as_image", True):
            img_url = await self.html_render(self._render_vs_code_style(f"📄 {path}", content, "File Viewer"), {})
            yield event.image_result(img_url)
        else:
            yield event.plain_result(f"文件内容 ({path}):\n{content}")

    @filter.command("ops_ls")
    async def ops_ls(self, event: AstrMessageEvent):
        """查看服务器目录结构。用法：/ops_ls [路径]"""
        logger.debug(f"Ops_ls triggered with message: {event.message_str}")
        config = await self._get_ops_config()
        if not await self._check_permission(event, config):
            yield event.plain_result("无权限。")
            return
        
        path = event.message_str
        for prefix_cmd in ["/ops_ls", "*ops_ls", "!ops_ls", "ops_ls"]:
            if path.startswith(prefix_cmd):
                path = path[len(prefix_cmd):].strip()
                break
        path = path or "."
        ssh = await self._init_ssh(config)
        
        # 使用 ls -F 获取带标识的列表
        status, stdout, stderr = await ssh.execute_command(f"ls -F --color=never {path}")
        if status != 0:
            yield event.plain_result(f"错误: {stderr}")
            return

        lines = stdout.strip().split('\n')
        formatted_list = ""
        for line in lines:
            if not line: continue
            if line.endswith('/'):
                formatted_list += f"<span style='color: #dcb67a;'>📁 {line}</span>\n"
            elif line.endswith('*'):
                formatted_list += f"<span style='color: #b5cea8;'>🚀 {line}</span>\n"
            elif line.endswith('@'):
                formatted_list += f"<span style='color: #4fc1ff;'>🔗 {line}</span>\n"
            else:
                formatted_list += f"<span style='color: #d4d4d4;'>📄 {line}</span>\n"

        img_url = await self.html_render(self._render_vs_code_style(f"📂 Explorer: {path}", formatted_list, "Directory Tree"), {})
        yield event.image_result(img_url)

    @filter.command("ops_log")
    async def ops_log(self, event: AstrMessageEvent):
        """查看并渲染当前会话的历史操作记录。"""
        logger.debug(f"Ops_log triggered with message: {event.message_str}")
        user_id = event.get_sender_id()
        history_key = f"ops_history_{user_id}"
        history_data = await self.get_kv_data(history_key, [])
        
        if not history_data:
            yield event.plain_result("当前没有历史记录。")
            return
        
        log_content = ""
        for m in history_data:
            role_color = "#569cd6" if m['role'] == 'user' else "#ce9178"
            role_name = "USER" if m['role'] == 'user' else "AGENT"
            log_content += f"<div style='margin-bottom: 8px;'><b style='color: {role_color}'>{role_name}></b> {m['content']}</div>"

        img_url = await self.html_render(self._render_vs_code_style(f"🕒 Session History", log_content, str(user_id)), {})
        yield event.image_result(img_url)

    @filter.command("ops_skills")
    async def ops_skills(self, event: AstrMessageEvent):
        """列出所有已学到的运维技能。"""
        skills = await self.get_kv_data("ops_skills", {})
        if not skills:
            yield event.plain_result("🧠 目前还没有学习到任何技能。你可以通过 /ops 指令让 Agent 学习。")
            return
        
        content = ""
        for name, detail in skills.items():
            content += f"### {name}\n{detail}\n\n"
        
        img_url = await self.html_render(self._render_vs_code_style("🧠 已学技能库", content, "Skill Memory"), {})
        yield event.image_result(img_url)

    @filter.command("ops_forget")
    async def ops_forget(self, event: AstrMessageEvent):
        """忘掉某个已学的技能。用法：/ops_forget <技能名>"""
        name = re.sub(r'^([/*!]\s*)?ops_forget\s*', '', event.message_str, flags=re.IGNORECASE).strip()
        if not name:
            yield event.plain_result("请输入要忘掉的技能名称。")
            return
        
        skills = await self.get_kv_data("ops_skills", {})
        if name in skills:
            del skills[name]
            await self.put_kv_data("ops_skills", skills)
            yield event.plain_result(f"✅ 已从记忆中移除技能：{name}")
        else:
            yield event.plain_result(f"⚠️ 找不到名为 '{name}' 的技能。")

