# Server Ops Agent v3 🚀

基于 LLM 的智能远程服务器运维助手，让您通过自然语言管理 Linux 服务器。

## ✨ v3.0 新特性

1. **🔇 UX 降噪**：优化 Hook 逻辑，减少执行过程中的无用消息气泡，让对话更清爽。
2. **🌳 视觉化目录树 (`/ops_ls`)**：新增指令，一键查看服务器文件夹结构，带图标和颜色区分。
3. **🎨 统一 VS Code 风格**：所有图片渲染（文件查看、日志、目录树）均采用精致的 VS Code 深色主题。
4. **🤖 智能提示词优化**：参考 GitHub Copilot 策略，Agent 现在更主动、更严谨，且会隐藏实现细节。
5. **🛠️ 延续 v2 优势**：长超时安装、全自动确认、持续会话记忆。

## 📖 指令列表

| 指令 | 说明 | 示例 |
| :--- | :--- | :--- |
| `/ops <任务>` | 执行运维任务（核心指令） | `/ops 安装 nginx 并配置 80 端口` |
| `/ops_ls [路径]` | 查看目录结构（带图标渲染） | `/ops_ls /var/www` |
| `/ops_cat <路径>` | 查看文件内容（代码风格渲染） | `/ops_cat /etc/nginx/nginx.conf` |
| `/ops_log` | 查看当前会话的操作记录图 | `/ops_log` |
| `/ops_clear` | 清空会话记忆 | `/ops_clear` |

## ⚙️ 配置项说明

在 AstrBot 管理面板中进行配置：

| 配置项 | 说明 | 默认值 |
| :--- | :--- | :--- |
| `ssh_host` | 服务器 IP 或域名 | `127.0.0.1` |
| `max_steps` | Agent 解决任务的最大尝试步数 | `15` |
| `cmd_default_timeout` | 普通命令超时（秒） | `30` |
| `install_timeout` | 安装任务专用超时（秒） | `600` |
| `history_max_turns` | 对话记忆的最大轮数 | `10` |
| `allowed_users` | 白名单 ID（逗号分隔） | `(空，仅限管理员)` |
| `render_file_as_image` | 是否开启文件图片化渲染 | `true` |

## 🚀 快速开始

1. **安装**：将其放入插件目录并重启。
2. **配置**：在管理面板设置 SSH 的 Host、User 和密码。
3. **对话**：
   - `/ops 帮我写一个简单的静态 HTML 博客放在 /var/www/html`
   - `/ops 帮我安装 1panel`
   - `/ops 检查一下刚才安装的状态`

---
*Powered by AstrBot*
