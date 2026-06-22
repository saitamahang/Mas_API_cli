from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any

from pangu.agent.errors import AgentError


DEFAULT_SKILL_NAME = "pangu-agent"
BUNDLED_SKILL_NAMES = ("pangu-agent", "pangu")


def normalize_skill_name(name: str) -> str:
    if name not in BUNDLED_SKILL_NAMES:
        choices = ", ".join(BUNDLED_SKILL_NAMES)
        raise AgentError("unknown_skill", f"未知内置 skill: {name}，可选值: {choices}", "choose_supported_skill")
    return name


def skill_source(name: str = DEFAULT_SKILL_NAME) -> tuple[str, str]:
    """Read the bundled skill from package data resources."""
    name = normalize_skill_name(name)

    # Editable checkout and installed wheels both store canonical skills under pangu/data/skills.
    pkg_root = Path(__file__).resolve().parents[1]
    candidate = pkg_root / "data" / "skills" / name / "SKILL.md"
    if candidate.exists():
        return candidate.read_text(encoding="utf-8"), str(candidate)

    # Non-standard importers: resolve through importlib resources.
    resource = resources.files("pangu").joinpath("data", "skills", name, "SKILL.md")
    if resource.is_file():
        return resource.read_text(encoding="utf-8"), str(resource)

    raise AgentError("skill_source_missing", f"找不到内置的 {name} SKILL.md 源文件", "check_installation")


def skill_source_path(name: str = DEFAULT_SKILL_NAME) -> str:
    _, source = skill_source(name)
    return source


def skill_dest_path(name: str = DEFAULT_SKILL_NAME) -> Path:
    name = normalize_skill_name(name)
    return Path.home() / ".claude" / "skills" / name / "SKILL.md"


def install_skill(force: bool, name: str = DEFAULT_SKILL_NAME) -> dict[str, Any]:
    name = normalize_skill_name(name)
    source_text, source = skill_source(name)
    dest = skill_dest_path(name)
    exists_before = dest.exists()
    if exists_before and not force:
        raise AgentError(
            "skill_already_installed",
            f"{name} skill 已安装到 {dest}，使用 --force 覆盖",
            "pass_force_or_skip",
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(source_text, encoding="utf-8")
    return {
        "name": name,
        "source": source,
        "installed_to": str(dest),
        "exists_before": exists_before,
        "force": force,
    }


def skill_status(name: str = DEFAULT_SKILL_NAME) -> dict[str, Any]:
    dest = skill_dest_path(name)
    src_text, src = skill_source(name)
    installed = dest.exists()
    up_to_date = False
    if installed:
        up_to_date = dest.read_text(encoding="utf-8") == src_text
    return {
        "name": normalize_skill_name(name),
        "installed": installed,
        "up_to_date": up_to_date,
        "source": src,
        "destination": str(dest),
        "next_action": "install" if not installed else ("up_to_date" if up_to_date else "reinstall_with_force"),
    }
