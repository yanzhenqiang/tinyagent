import json
import os
import re
import shutil
from pathlib import Path


class SkillsLoader:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.workspace_skills = workspace / "skills"

    def list_skills(self) -> list[dict[str, str]]:
        skills = []
        if self.workspace_skills.exists():
            for skill_dir in self.workspace_skills.iterdir():
                if skill_dir.is_dir():
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.exists() and not any(skill["name"] == skill_dir.name for skill in skills):
                        skills.append({"name": skill_dir.name, "path": str(skill_file)})
        return skills

    def load_skill(self, name: str) -> str | None:
        workspace_skill = self.workspace_skills / name / "SKILL.md"
        if workspace_skill.exists():
            return workspace_skill.read_text(encoding="utf-8")
        return None

    def load_skills_for_context(self) -> str:
        result = []
        for s in self.list_skills():
            meta = self.get_skill_metadata(s["name"])
            skill_meta = self._parse_tinyagent_metadata(meta.get("metadata", ""))
            if skill_meta.get("always") or meta.get("always"):
                result.append(s["name"])
        parts = []
        for name in result:
            content = self.load_skill(name)
            if content:
                content = self._strip_frontmatter(content)
                parts.append(f"### Skill: {name}\n\n{content}")
        return "\n\n---\n\n".join(parts) if parts else ""

    def build_skills_summary(self) -> str:
        all_skills = self.list_skills()
        if not all_skills:
            return ""
        def escape_xml(s: str) -> str:
            return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        lines = ["<skills>"]
        for s in all_skills:
            name = escape_xml(s["name"])
            path = s["path"]
            desc = escape_xml(self._get_skill_description(s["name"]))
            lines.append("  <skill>")
            lines.append(f"    <name>{name}</name>")
            lines.append(f"    <description>{desc}</description>")
            lines.append(f"    <location>{path}</location>")
            lines.append("  </skill>")
        lines.append("</skills>")
        return "\n".join(lines)

    def _get_skill_description(self, name: str) -> str:
        meta = self.get_skill_metadata(name)
        if meta and meta.get("description"):
            return meta["description"]
        return name

    def _strip_frontmatter(self, content: str) -> str:
        """Remove YAML frontmatter from markdown content."""
        if content.startswith("---"):
            match = re.match(r"^---\n.*?\n---\n", content, re.DOTALL)
            if match:
                return content[match.end():].strip()
        return content

    def _parse_tinyagent_metadata(self, raw: str) -> dict:
        try:
            data = json.loads(raw)
            return data.get("tinyagent", {}) if isinstance(data, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}


    def get_skill_metadata(self, name: str) -> dict | None:
        content = self.load_skill(name)
        if not content:
            return None
        if content.startswith("---"):
            match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
            if match:
                metadata = {}
                for line in match.group(1).split("\n"):
                    if ":" in line:
                        key, value = line.split(":", 1)
                        metadata[key.strip()] = value.strip().strip('"\'')
                return metadata
        return None
