from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

JdErrorCode = Literal["JD_TOO_SHORT", "JD_TOO_LONG", "JD_KEYWORDS_NOT_FOUND"]

SKILL_ALIASES: dict[str, tuple[str, ...]] = {
    "Python": ("python",),
    "Java": ("java",),
    "JavaScript": ("javascript", "js"),
    "TypeScript": ("typescript", "ts"),
    "React": ("react",),
    "Vue.js": ("vue.js", "vuejs", "vue3", "vue"),
    "Vite": ("vite",),
    "ECharts": ("echarts",),
    "Axios": ("axios",),
    "FastAPI": ("fastapi",),
    "Django": ("django",),
    "Flask": ("flask",),
    "Spring Boot": ("spring boot",),
    "Node.js": ("node.js", "nodejs", "node"),
    "RESTful API": ("restful api", "rest api", "restful"),
    "GraphQL": ("graphql",),
    "Redis": ("redis",),
    "PostgreSQL": ("postgresql", "postgres"),
    "MySQL": ("mysql",),
    "MongoDB": ("mongodb",),
    "Docker": ("docker",),
    "Kubernetes": ("kubernetes", "k8s"),
    "Git": ("git",),
    "Linux": ("linux",),
    "AWS": ("aws",),
    "Alibaba Cloud": ("alibaba cloud", "阿里云"),
    "Serverless": ("serverless", "无服务器"),
    "CI/CD": ("ci/cd", "cicd", "持续集成", "持续交付"),
}

RESPONSIBILITY_ALIASES: dict[str, tuple[str, ...]] = {
    "Backend Development": ("backend development", "后端开发"),
    "Frontend Development": ("frontend development", "前端开发"),
    "API Development": ("api development", "接口开发"),
    "System Design": ("system design", "系统设计"),
    "Data Analysis": ("data analysis", "数据分析"),
    "Automated Testing": ("automated testing", "自动化测试"),
    "Deployment": ("deployment", "部署上线"),
    "Performance Optimization": ("performance optimization", "性能优化"),
    "Team Collaboration": ("team collaboration", "团队协作"),
    "Project Management": ("project management", "项目管理"),
}

RESPONSIBILITY_LABELS: dict[str, str] = {
    "Backend Development": "后端开发",
    "Frontend Development": "前端开发",
    "API Development": "接口开发",
    "System Design": "系统设计",
    "Data Analysis": "数据分析",
    "Automated Testing": "自动化测试",
    "Deployment": "部署上线",
    "Performance Optimization": "性能优化",
    "Team Collaboration": "团队协作",
    "Project Management": "项目管理",
}


class JdValidationError(ValueError):
    """A stable, public-safe validation failure for a job description."""

    def __init__(self, code: JdErrorCode) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class JdKeywords:
    skills: tuple[str, ...]
    responsibilities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ParsedJobDescription(JdKeywords):
    normalized_text: str


def _is_ascii_alias(alias: str) -> bool:
    return alias.isascii()


def _alias_pattern(alias: str) -> re.Pattern[str]:
    escaped = re.escape(unicodedata.normalize("NFKC", alias))
    if _is_ascii_alias(alias):
        return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE)
    return re.compile(escaped)


def _extract_catalog(
    text: str,
    catalog: dict[str, tuple[str, ...]],
) -> tuple[str, ...]:
    matches: list[tuple[int, int, str]] = []
    for catalog_order, (canonical, aliases) in enumerate(catalog.items()):
        positions = [
            match.start()
            for alias in aliases
            if (match := _alias_pattern(alias).search(text)) is not None
        ]
        if positions:
            matches.append((min(positions), catalog_order, canonical))
    matches.sort()
    return tuple(canonical for _, _, canonical in matches)


def extract_catalog_keywords(
    text: str,
    catalog: dict[str, tuple[str, ...]],
) -> tuple[str, ...]:
    """Extract canonical catalog entries from arbitrary text in first-hit order."""
    return _extract_catalog(unicodedata.normalize("NFKC", text), catalog)


def extract_jd_keywords(job_description: str) -> ParsedJobDescription:
    """Normalize, validate and deterministically extract frozen v1 JD keywords."""
    normalized_text = unicodedata.normalize("NFKC", job_description)
    if len(normalized_text) > 10_000:
        raise JdValidationError("JD_TOO_LONG")
    if len(normalized_text.strip()) < 20:
        raise JdValidationError("JD_TOO_SHORT")

    skills = _extract_catalog(normalized_text, SKILL_ALIASES)
    responsibilities = _extract_catalog(normalized_text, RESPONSIBILITY_ALIASES)
    if not skills and not responsibilities:
        raise JdValidationError("JD_KEYWORDS_NOT_FOUND")
    return ParsedJobDescription(
        normalized_text=normalized_text.strip(),
        skills=skills,
        responsibilities=responsibilities,
    )
