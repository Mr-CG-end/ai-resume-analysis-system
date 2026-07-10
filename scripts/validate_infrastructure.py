from __future__ import annotations

import re
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _read_required(root: Path, relative_path: str, errors: list[str]) -> str:
    path = root / relative_path
    if not path.is_file():
        errors.append(f"missing required file: {relative_path}")
        return ""
    return path.read_text(encoding="utf-8")


def _compose_service_names(compose: str) -> set[str]:
    in_services = False
    names: set[str] = set()
    for line in compose.splitlines():
        if re.fullmatch(r"services:\s*", line):
            in_services = True
            continue
        if in_services and line and not line.startswith((" ", "#")):
            break
        if in_services:
            match = re.fullmatch(r"  ([A-Za-z0-9_-]+):\s*", line)
            if match:
                names.add(match.group(1))
    return names


def validate_repository(root: Path = REPOSITORY_ROOT) -> list[str]:
    errors: list[str] = []

    compose = _read_required(root, "docker-compose.yml", errors)
    if compose:
        if _compose_service_names(compose) != {"redis"}:
            errors.append("docker-compose.yml must define exactly the redis service")
        if not re.search(r"^\s+image:\s*redis:7\s*$", compose, re.MULTILINE):
            errors.append("docker-compose.yml must use the redis:7 image")
        if not re.search(r"^\s+healthcheck:\s*$", compose, re.MULTILINE):
            errors.append("docker-compose.yml must define a Redis health check")

    dockerfile = _read_required(root, "backend/Dockerfile", errors)
    if dockerfile:
        required_dockerfile_fragments = (
            "FROM python:3.12-slim",
            "EXPOSE 9000",
            '"uvicorn", "app.main:app"',
            '"--host", "0.0.0.0"',
            '"--port", "9000"',
        )
        for fragment in required_dockerfile_fragments:
            if fragment not in dockerfile:
                errors.append(f"backend/Dockerfile is missing: {fragment}")

    ci = _read_required(root, ".github/workflows/ci.yml", errors)
    if ci:
        required_ci_fragments = (
            "push:",
            "pull_request:",
            "ruff check .",
            "mypy app",
            "pytest",
            "pnpm install --frozen-lockfile",
            "pnpm lint",
            "pnpm typecheck",
            "pnpm test --run",
            "pnpm build",
        )
        for fragment in required_ci_fragments:
            if fragment not in ci:
                errors.append(f"ci.yml is missing: {fragment}")

    pages = _read_required(root, ".github/workflows/pages.yml", errors)
    if pages:
        required_pages_fragments = (
            "contents: read",
            "pages: write",
            "id-token: write",
            "actions/configure-pages@v5",
            "actions/upload-pages-artifact@v3",
            "actions/deploy-pages@v4",
            "pnpm install --frozen-lockfile",
            "VITE_BASE_PATH: /${{ github.event.repository.name }}/",
            "path: frontend/dist",
        )
        for fragment in required_pages_fragments:
            if fragment not in pages:
                errors.append(f"pages.yml is missing: {fragment}")

    return errors


def main() -> int:
    errors = validate_repository()
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Infrastructure configuration is valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
