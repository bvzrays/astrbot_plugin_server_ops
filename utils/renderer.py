"""Renderer: builds Jinja2 template + data dict for AstrBot html_render()."""


class Renderer:
    """Builds VS Code-styled HTML templates for rendering via AstrBot's html_render."""

    def build_template(self, title: str, content: str, mode: str = "plain"):
        """Return (tmpl_str, data_dict) suitable for html_render(tmpl, data, options)."""

        # Pre-process content per mode
        if mode == "tree":
            lines = content.strip().split('\n')
            processed_lines = []
            for line in lines:
                if not line:
                    continue
                icon = "📁" if ('/' in line or line.rstrip().endswith(':')) else "📄"
                processed_lines.append({"icon": icon, "text": line, "cls": "tree-dir" if icon == "📁" else "tree-file"})
            tmpl = _TREE_TMPL
            data = {"title": title, "subtitle": "Directory Tree", "lines": processed_lines}

        elif mode == "log":
            lines = content.strip().split('\n')
            processed_lines = []
            for line in lines:
                if not line:
                    continue
                low = line.lower()
                cls = "log-error" if "error" in low or "err" in low else \
                      "log-warn" if "warn" in low else "log-normal"
                processed_lines.append({"text": line, "cls": cls})
            tmpl = _LOG_TMPL
            data = {"title": title, "subtitle": "Log Viewer", "lines": processed_lines}

        else:  # plain
            tmpl = _PLAIN_TMPL
            data = {"title": title, "subtitle": "Terminal Output", "content": content}

        return tmpl, data


# ─────────────────────── Jinja2 Templates ─────────────────────────────────── #

_BASE_STYLE = """
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: transparent; font-family: 'Consolas', 'Monaco', monospace; }
  .card {
    display: inline-block;
    background: #1e1e1e;
    color: #d4d4d4;
    padding: 18px 22px;
    border-radius: 10px;
    border: 1px solid #333;
    min-width: 380px;
    max-width: 1000px;
  }
  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid #444;
    padding-bottom: 10px;
    margin-bottom: 14px;
  }
  .title { color: #4ec9b0; font-weight: bold; font-size: 14px; }
  .subtitle { color: #6a9955; font-size: 11px; }
  .body { font-size: 13px; line-height: 1.7; }
</style>
"""

_PLAIN_TMPL = _BASE_STYLE + """
<body>
<div class="card">
  <div class="header">
    <span class="title">{{ title }}</span>
    <span class="subtitle">{{ subtitle }}</span>
  </div>
  <div class="body"><pre style="white-space:pre-wrap;color:#d4d4d4;">{{ content }}</pre></div>
</div>
</body>
"""

_TREE_TMPL = _BASE_STYLE + """
<style>
  .tree-dir { color: #dcb67a; } .tree-file { color: #d4d4d4; }
</style>
<body>
<div class="card">
  <div class="header">
    <span class="title">{{ title }}</span>
    <span class="subtitle">{{ subtitle }}</span>
  </div>
  <div class="body">
    {% for l in lines %}
    <div class="{{ l.cls }}">{{ l.icon }} {{ l.text }}</div>
    {% endfor %}
  </div>
</div>
</body>
"""

_LOG_TMPL = _BASE_STYLE + """
<style>
  .log-error { color: #f48771; } .log-warn { color: #cca700; } .log-normal { color: #d4d4d4; }
</style>
<body>
<div class="card">
  <div class="header">
    <span class="title">{{ title }}</span>
    <span class="subtitle">{{ subtitle }}</span>
  </div>
  <div class="body">
    {% for l in lines %}
    <div class="{{ l.cls }}">{{ l.text }}</div>
    {% endfor %}
  </div>
</div>
</body>
"""
