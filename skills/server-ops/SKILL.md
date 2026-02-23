---
name: server-ops
description: Core server operations skills for managing Linux servers via SSH
always: true
---

# Server Operations Agent Skills

You are connected to a remote Linux server via SSH. Below are the key principles and available tools for this context.

## Core Tools

| Tool | Purpose |
|------|---------|
| `execute_shell` | Run any non-interactive shell command |
| `install_package` | Install packages with auto-confirmed prompts (long timeout) |
| `read_file` | Read server file contents |
| `write_file` | Write or overwrite text files on the server |
| `download_to_server` | Download a file from a URL and place it on the server via SFTP |
| `render_output` | Execute a command and send the result as a rendered image (use for trees/logs) |
| `update_memory` | Write permanent facts to MEMORY.md |
| `search_history` | Search past operation history |
| `web_fetch` | Fetch and read a web page |
| `web_search` | Search with Brave API (if key configured) |

## Decision Patterns

### When to `render_output` vs `execute_shell`
- Use `render_output` whenever: output is multi-line (>10 lines), tree structure, log tailing
- Use `execute_shell` for: status checks, quick single-line output, chained commands

### When to `update_memory`
Record facts that save time in future sessions:
- Service port numbers, deploy paths
- API endpoints or tokens discovered during operations
- Non-obvious file locations (e.g., "nginx config is at /opt/nginx/sites/blog.conf")
- Working one-liner commands for recurring tasks

Do NOT record: intermediate exploration steps, transient command output.

### Package Management Detection
```bash
# Detect package manager
which apt && echo "debian" || which yum && echo "rpm" || which brew && echo "brew"
```

### Service Management
```bash
# Start / stop / status
systemctl start nginx
systemctl stop nginx
systemctl status nginx --no-pager

# Journald logs (last 100 lines)
journalctl -u nginx -n 100 --no-pager
```

### File Transfer Heuristic
If the user sends an image or a file URL:
1. Identify the destination path from context or ask
2. Call `download_to_server` with {{ url, dest_path }}
