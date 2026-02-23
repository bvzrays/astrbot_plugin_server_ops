# AstrBot Server Ops Agent (v1.1.0)

基于 LLM 的远程服务器运维助手，通过自然语言对话即可实现复杂的 Linux 服务器管理。

## 🌟 核心特性

- **自然语言运维**：直接告诉 Bot "帮我看看系统负载"、"帮我安装 nginx" 或 "重启 docker 容器"。
- **可视化输出**：自主识别输出长度和类型，将目录树 (`ls -R`)、长日志 (`tail`) 等渲染为精美图片发送。
- **自主 Skill 学习**：Agent 会将复杂或常用的操作流程记入长期记忆，下次直接应用知识，无需重复探索。
- **对话隔离系统**：运维对话记录与主聊天窗口完全隔离，支持独立清除和查看。
- **零依赖配置**：无需在服务器端安装 Agent，仅需 SSH 访问权限，支持密码及私钥。
- **高兼容性**：内置宽容算法集合，完美支持各类新旧 Linux 发行版（Ubuntu, CentOS, Debian 等）。

## 📸 功能演示

### 1. 可视化渲染
发送 `/ops 帮我看看网站根目录结构`，Bot 会返回一张带有文件夹和文件图标标注的树形结构图。

### 2. 技能记忆
发送 `/ops 记住怎么检查 nginx 状态并重启`，之后发送 `/ops 查下 nginx` 时，Bot 将直接执行预记的指令。

## 🛠️ 安装

1. 在 AstrBot 插件市场搜索 `astrbot_plugin_server_ops` 进行安装。
2. 或在 `data/plugins` 目录下克隆本项目：
   ```bash
   git clone https://github.com/bvzrays/astrbot_plugin_server_ops.git
   ```

## ⚙️ 配置项

| 配置名 | 描述 | 默认值 |
|--------|------|--------|
| `ssh_host` | 服务器 IP 或域名 | `127.0.0.1` |
| `ssh_port` | SSH 端口 | `22` |
| `ssh_username` | SSH 用户名 | `root` |
| `ssh_password` | SSH 密码 | - |
| `ssh_key_path` | 私钥文件绝对路径 | - |
| `allowed_users` | 允许使用的用户 ID 白名单 | (仅管理员) |

## ⌨️ 常用命令

- `/ops <任务>`：启动运维 Agent 执行任务。
- `/ops_test`：启动 SSH 连接诊断。
- `/ops_skills`：查看已学到的技能库。
- `/ops_forget <名称>`：遗忘特定技能。
- `/ops_log`：查看隔离的运维历史记录。
- `/ops_clear`：清空运维会话记忆。
- `/ops_ls [路径]`：快速查看目录（带渲染）。
- `/ops_cat <路径>`：快速查看文件内容（带渲染）。

## 📝 更新日志

### v1.1.0 (2026-02-23)
- **[NEW]** 自主截图渲染：新增 `render_output` 工具，支持 `tree`/`log`/`plain` 三种可视化模式。
- **[NEW]** 技能学习系统：新增 `LearnSkill` 工具，支持通过指令集长期记忆复杂操作。
- **[NEW]** 对话隔离：运维历史记录 (`ops_history_`) 与全局历史完全物理隔离。
- **[FIX]** SSH 重连 Bug：修复 `SSHClientConnection` 缺少 `is_closing` 属性导致的重连失败。
- **[FIX]** 兼容性提升：引入宽容算法集合 (`_COMPAT_ALGS`)，解决部分服务器握手阶段 `Connection lost` 问题。
- **[ENH]** 性能优化：更智能的连接存活检测 (`_is_conn_alive`)，大幅减少无效重连。

---
Produced by [bvzrays](https://github.com/bvzrays). Powered by [AstrBot](https://github.com/Soulter/AstrBot).
