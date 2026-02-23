"""SKILL.md-based skills loading system (Nanobot-inspired).

Skills are Markdown files in {workspace}/skills/{name}/SKILL.md (or built-in).
Frontmatter controls discovery and loading behaviour.
"""

import re
import yaml
from pathlib import Path
from typing import List, Dict, Optional

# Built-in skills directory (bundled with the plugin)
BUILTIN_SKILLS_DIR = Path(__file__).parent.parent / "skills"


class SkillsLoader:
    """Load and manage agent skills from SKILL.md files."""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.workspace_skills = workspace / "skills"
        self.builtin_skills = BUILTIN_SKILLS_DIR

    # ------------------------------------------------------------------ #
    #  Discovery                                                           #
    # ------------------------------------------------------------------ #

    def list_skills(self) -> List[Dict[str, str]]:
        """List all available skills from workspace and built-in dirs."""
        skills: Dict[str, Dict] = {}

        # Workspace skills take priority
        for src_dir, source in [
            (self.workspace_skills, "workspace"),
            (self.builtin_skills, "builtin"),
        ]:
            if not src_dir.exists():
                continue
            for skill_dir in src_dir.iterdir():
                if skill_dir.is_dir():
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.exists() and skill_dir.name not in skills:
                        skills[skill_dir.name] = {
                            "name": skill_dir.name,
                            "path": str(skill_file),
                            "source": source,
                        }

        return list(skills.values())

    def load_skill(self, name: str) -> Optional[str]:
        """Load raw SKILL.md content by skill name."""
        for src_dir in [self.workspace_skills, self.builtin_skills]:
            skill_file = src_dir / name / "SKILL.md"
            if skill_file.exists():
                return skill_file.read_text(encoding="utf-8")
        return None

    # ------------------------------------------------------------------ #
    #  Metadata parsing                                                    #
    # ------------------------------------------------------------------ #

    def get_skill_metadata(self, name: str) -> Dict:
        """Parse YAML frontmatter from a skill."""
        content = self.load_skill(name)
        if not content:
            return {}
        if content.startswith("---"):
            m = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
            if m:
                try:
                    return yaml.safe_load(m.group(1)) or {}
                except Exception:
                    pass
        return {}

    def _strip_frontmatter(self, content: str) -> str:
        if content.startswith("---"):
            m = re.match(r"^---\n.*?\n---\n?", content, re.DOTALL)
            if m:
                return content[m.end():].strip()
        return content

    # ------------------------------------------------------------------ #
    #  Context injection helpers                                           #
    # ------------------------------------------------------------------ #

    def get_always_skills(self) -> List[str]:
        """Return names of skills with `always: true` in their frontmatter."""
        result = []
        for s in self.list_skills():
            meta = self.get_skill_metadata(s["name"])
            if meta.get("always") or meta.get("nanobot", {}).get("always"):
                result.append(s["name"])
        return result

    def build_always_context(self) -> str:
        """Build full-text injection for always-loaded skills."""
        parts = []
        for name in self.get_always_skills():
            content = self.load_skill(name)
            if content:
                parts.append(f"### Skill: {name}\n\n{self._strip_frontmatter(content)}")
        return "\n\n---\n\n".join(parts)

    def build_skills_summary(self) -> str:
        """Build XML summary of all skills for lazy-loading by Agent."""
        skills = self.list_skills()
        if not skills:
            return ""

        lines = ["<skills>"]
        for s in skills:
            meta = self.get_skill_metadata(s["name"])
            desc = meta.get("description", s["name"])
            name = s["name"]
            path = s["path"]
            lines += [
                "  <skill>",
                f"    <name>{name}</name>",
                f"    <description>{desc}</description>",
                f"    <location>{path}</location>",
                "  </skill>",
            ]
        lines.append("</skills>")
        return "\n".join(lines)
