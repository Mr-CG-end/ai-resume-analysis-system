from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _read_required(root: Path, relative_path: str, errors: list[str]) -> str:
    path = root / relative_path
    if not path.is_file():
        errors.append(f"missing required file: {relative_path}")
        return ""
    return path.read_text(encoding="utf-8")


def _mapping(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        return None
    return {key: item for key, item in value.items() if isinstance(key, str)}


def _load_yaml(contents: str, relative_path: str, errors: list[str]) -> dict[str, object] | None:
    try:
        document = yaml.load(contents, Loader=yaml.BaseLoader)
    except yaml.YAMLError as error:
        errors.append(f"{relative_path} is not valid YAML: {error}")
        return None
    mapping = _mapping(document)
    if mapping is None:
        errors.append(f"{relative_path} must contain a YAML mapping")
    return mapping


def _validate_compose(compose: str, errors: list[str]) -> None:
    document = _load_yaml(compose, "docker-compose.yml", errors)
    if document is None:
        return
    services = _mapping(document.get("services"))
    if services is None or set(services) != {"redis"}:
        errors.append("docker-compose.yml must define exactly the redis service")
        return
    redis = _mapping(services["redis"])
    if redis is None:
        errors.append("docker-compose.yml redis service must be a mapping")
        return
    if redis.get("image") != "redis:7":
        errors.append("docker-compose.yml must use the redis:7 image")
    healthcheck = _mapping(redis.get("healthcheck"))
    if healthcheck is None or not healthcheck.get("test"):
        errors.append("docker-compose.yml must define a Redis health check command")
    if redis.get("ports") != ["127.0.0.1:6379:6379"]:
        errors.append("docker-compose.yml must publish Redis only on 127.0.0.1:6379")
    if "volumes" in redis or "volumes" in document:
        errors.append("docker-compose.yml must not configure persistent Redis volumes")


def _dockerfile_instructions(dockerfile: str) -> list[tuple[str, str]]:
    instructions: list[tuple[str, str]] = []
    continuation = ""
    for raw_line in dockerfile.splitlines():
        stripped = raw_line.strip()
        if not continuation and (not stripped or stripped.startswith("#")):
            continue
        logical_line = f"{continuation} {stripped}".strip()
        if logical_line.endswith("\\"):
            continuation = logical_line[:-1].rstrip()
            continue
        continuation = ""
        match = re.fullmatch(r"([A-Za-z]+)\s+(.+)", logical_line)
        if match:
            instructions.append((match.group(1).upper(), match.group(2).strip()))
    return instructions


def _validate_dockerfile(dockerfile: str, errors: list[str]) -> None:
    instructions = _dockerfile_instructions(dockerfile)
    expected_base = "python:3.12.13-slim-bookworm"
    if not instructions or instructions[0] != ("FROM", expected_base):
        errors.append(f"backend/Dockerfile must start from {expected_base}")

    copies = [argument for instruction, argument in instructions if instruction == "COPY"]
    if not any(
        re.fullmatch(r"(?:--\S+\s+)*requirements\.lock\s+\.?/?", item) for item in copies
    ):
        errors.append("backend/Dockerfile must copy requirements.lock before installing dependencies")
    if not any(re.fullmatch(r"(?:--\S+\s+)*app\s+\.?/?app/?", item) for item in copies):
        errors.append("backend/Dockerfile must copy the application package")

    runs = [argument for instruction, argument in instructions if instruction == "RUN"]
    expected_install = (
        "python -m pip install --no-cache-dir --require-hashes -r requirements.lock"
    )
    if expected_install not in runs:
        errors.append("backend/Dockerfile must install the hash-locked runtime dependencies")

    install_index = next(
        (index for index, item in enumerate(instructions) if item == ("RUN", expected_install)),
        None,
    )
    app_copy_index = next(
        (
            index
            for index, (instruction, argument) in enumerate(instructions)
            if instruction == "COPY" and re.fullmatch(r"(?:--\S+\s+)*app\s+\.?/?app/?", argument)
        ),
        None,
    )
    if install_index is None or app_copy_index is None or install_index >= app_copy_index:
        errors.append("backend/Dockerfile must install dependencies before copying app/")

    exposes = [argument.split() for instruction, argument in instructions if instruction == "EXPOSE"]
    if not any("9000" in ports for ports in exposes):
        errors.append("backend/Dockerfile must expose port 9000")

    commands = [argument for instruction, argument in instructions if instruction == "CMD"]
    expected_command = [
        "uvicorn",
        "app.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "9000",
    ]
    try:
        final_command = json.loads(commands[-1]) if commands else None
    except json.JSONDecodeError:
        final_command = None
    if final_command != expected_command:
        errors.append("backend/Dockerfile final CMD must run uvicorn on 0.0.0.0:9000")


def _workflow_parts(
    document: dict[str, object], relative_path: str, errors: list[str]
) -> tuple[dict[str, object] | None, dict[str, object] | None, dict[str, object] | None]:
    triggers = _mapping(document.get("on"))
    permissions = _mapping(document.get("permissions"))
    jobs = _mapping(document.get("jobs"))
    if triggers is None:
        errors.append(f"{relative_path} must define mapping-style triggers")
    if permissions is None:
        errors.append(f"{relative_path} must define workflow permissions")
    if jobs is None:
        errors.append(f"{relative_path} must define jobs")
    return triggers, permissions, jobs


def _job_steps(job: object, label: str, errors: list[str]) -> list[dict[str, object]] | None:
    job_mapping = _mapping(job)
    if job_mapping is None or not isinstance(job_mapping.get("steps"), list):
        errors.append(f"{label} must define a steps list")
        return None
    steps: list[dict[str, object]] = []
    for step in job_mapping["steps"]:
        step_mapping = _mapping(step)
        if step_mapping is None:
            errors.append(f"{label} steps must be mappings")
            return None
        steps.append(step_mapping)
    return steps


def _working_directory(job: object) -> object:
    job_mapping = _mapping(job)
    defaults = _mapping(job_mapping.get("defaults")) if job_mapping else None
    run_defaults = _mapping(defaults.get("run")) if defaults else None
    return run_defaults.get("working-directory") if run_defaults else None


def _run_commands(steps: list[dict[str, object]]) -> list[object]:
    return [step["run"] for step in steps if "run" in step]


def _uses(steps: list[dict[str, object]]) -> list[object]:
    return [step["uses"] for step in steps if "uses" in step]


def _validate_ci(ci: str, errors: list[str]) -> None:
    document = _load_yaml(ci, ".github/workflows/ci.yml", errors)
    if document is None:
        return
    triggers, permissions, jobs = _workflow_parts(document, ".github/workflows/ci.yml", errors)
    if triggers is not None and not {"push", "pull_request"}.issubset(triggers):
        errors.append("ci.yml must run on pushes and pull requests")
    if permissions != {"contents": "read"}:
        errors.append("ci.yml permissions must be exactly contents: read")
    if jobs is None or set(jobs) != {"backend", "infrastructure", "frontend"}:
        errors.append("ci.yml must define exactly backend, infrastructure and frontend jobs")
        return

    expected_jobs = {
        "backend": (
            "backend",
            [
                "python -m pip install -e \".[dev]\"",
                "ruff format --check .",
                "ruff check .",
                "mypy app",
                "pytest",
            ],
            {"actions/checkout@v7", "actions/setup-python@v6"},
        ),
        "infrastructure": (
            None,
            [
                'python -m pip install -e "./backend[dev]"',
                "pytest tests/test_infrastructure.py",
                "python scripts/validate_infrastructure.py",
            ],
            {"actions/checkout@v7", "actions/setup-python@v6"},
        ),
        "frontend": (
            "frontend",
            [
                "pnpm install --frozen-lockfile",
                "pnpm lint",
                "pnpm typecheck",
                "pnpm test --run",
                "pnpm build",
            ],
            {"actions/checkout@v7", "pnpm/action-setup@v6", "actions/setup-node@v6"},
        ),
    }
    for job_name, (directory, commands, actions) in expected_jobs.items():
        job = jobs[job_name]
        if _working_directory(job) != directory:
            expected_directory = directory or "the repository root"
            errors.append(f"ci.yml {job_name} job must run from {expected_directory}")
        steps = _job_steps(job, f"ci.yml {job_name} job", errors)
        if steps is None:
            continue
        if _run_commands(steps) != commands:
            errors.append(f"ci.yml {job_name} job commands do not match the contract")
        if set(_uses(steps)) != actions:
            errors.append(f"ci.yml {job_name} job actions do not match the contract")
        setup_python = next(
            (step for step in steps if step.get("uses") == "actions/setup-python@v6"), None
        )
        if setup_python is not None:
            options = _mapping(setup_python.get("with"))
            if options is None or options.get("python-version") != "3.12.13":
                errors.append(f"ci.yml {job_name} job must use Python 3.12.13")


def _validate_pages(pages: str, errors: list[str]) -> None:
    document = _load_yaml(pages, ".github/workflows/pages.yml", errors)
    if document is None:
        return
    triggers, permissions, jobs = _workflow_parts(document, ".github/workflows/pages.yml", errors)
    push = _mapping(triggers.get("push")) if triggers else None
    if push is None or push.get("branches") != ["main"] or "workflow_dispatch" not in triggers:
        errors.append("pages.yml must run for main pushes and workflow dispatches")
    if permissions != {}:
        errors.append("pages.yml workflow-level permissions must be empty")
    if jobs is None or set(jobs) != {"build", "deploy"}:
        errors.append("pages.yml must define separate build and deploy jobs")
        return

    build = _mapping(jobs["build"])
    deploy = _mapping(jobs["deploy"])
    if build is None or deploy is None:
        errors.append("pages.yml build and deploy jobs must be mappings")
        return
    if _mapping(build.get("permissions")) != {"contents": "read"}:
        errors.append("pages.yml build job permissions must be exactly contents: read")
    if "environment" in build:
        errors.append("pages.yml build job must not own an environment")
    if _mapping(deploy.get("permissions")) != {"pages": "write", "id-token": "write"}:
        errors.append("pages.yml deploy job permissions must be exactly pages and id-token write")
    if deploy.get("needs") != "build":
        errors.append("pages.yml deploy job must need the build job")
    environment = _mapping(deploy.get("environment"))
    expected_environment = {
        "name": "github-pages",
        "url": "${{ steps.deployment.outputs.page_url }}",
    }
    if environment != expected_environment:
        errors.append("pages.yml deploy job must own the github-pages environment")

    build_steps = _job_steps(build, "pages.yml build job", errors)
    deploy_steps = _job_steps(deploy, "pages.yml deploy job", errors)
    if build_steps is None or deploy_steps is None:
        return

    expected_build_actions = [
        "actions/checkout@v7",
        "pnpm/action-setup@v6",
        "actions/setup-node@v6",
        "actions/configure-pages@v6",
        "actions/upload-pages-artifact@v4",
    ]
    if _uses(build_steps) != expected_build_actions:
        errors.append("pages.yml build actions do not match the build contract")

    expected_commands = [
        "pnpm install --frozen-lockfile",
        "pnpm lint",
        "pnpm typecheck",
        "pnpm test --run",
        "pnpm build",
    ]
    run_steps = [step for step in build_steps if "run" in step]
    if _run_commands(build_steps) != expected_commands:
        errors.append("pages.yml build commands do not match the build contract")
    if any(step.get("working-directory") != "frontend" for step in run_steps):
        errors.append("pages.yml commands must run from frontend")

    build_step = next((step for step in run_steps if step.get("run") == "pnpm build"), None)
    expected_environment = {
        "VITE_API_BASE_URL": "${{ vars.VITE_API_BASE_URL }}",
        "VITE_BASE_PATH": "/${{ github.event.repository.name }}/",
    }
    if build_step is None or _mapping(build_step.get("env")) != expected_environment:
        errors.append("pages.yml build must use repository variables and the repository-aware base path")

    upload_step = next(
        (
            step
            for step in build_steps
            if step.get("uses") == "actions/upload-pages-artifact@v4"
        ),
        None,
    )
    if upload_step is None or _mapping(upload_step.get("with")) != {"path": "frontend/dist"}:
        errors.append("pages.yml must upload frontend/dist as the Pages artifact")
    if _run_commands(deploy_steps) or _uses(deploy_steps) != ["actions/deploy-pages@v5"]:
        errors.append("pages.yml deploy job must only deploy the Pages artifact")
        return
    deploy_step = deploy_steps[0]
    if deploy_step.get("id") != "deployment":
        errors.append("pages.yml deploy-pages step must expose the deployment result")


def _normalize_package_name(requirement: str) -> str:
    match = re.match(r"^([A-Za-z0-9_.-]+)", requirement)
    return re.sub(r"[-_.]+", "-", match.group(1)).lower() if match else ""


def _validate_pyproject(pyproject: str, errors: list[str]) -> None:
    try:
        document = tomllib.loads(pyproject)
    except tomllib.TOMLDecodeError as error:
        errors.append(f"backend/pyproject.toml is not valid TOML: {error}")
        return
    project = document.get("project")
    if not isinstance(project, dict):
        errors.append("backend/pyproject.toml must define [project]")
        return
    if project.get("requires-python") != "==3.12.13":
        errors.append("backend/pyproject.toml requires-python must be exactly 3.12.13")
    optional = project.get("optional-dependencies")
    dev = optional.get("dev") if isinstance(optional, dict) else None
    if not isinstance(dev, list) or not any(
        isinstance(item, str) and _normalize_package_name(item) == "pip-tools" for item in dev
    ):
        errors.append("backend/pyproject.toml dev dependencies must include pip-tools")

    ruff = document.get("tool", {}).get("ruff", {})
    mypy = document.get("tool", {}).get("mypy", {})
    if not isinstance(ruff, dict) or ruff.get("target-version") != "py312":
        errors.append("backend/pyproject.toml Ruff target must be py312")
    if not isinstance(mypy, dict) or mypy.get("python_version") != "3.12":
        errors.append("backend/pyproject.toml mypy Python version must be 3.12")


def _validate_requirements_lock(lock: str, errors: list[str]) -> None:
    requirement_lines = [
        line for line in lock.splitlines() if line and not line.startswith((" ", "#", "--"))
    ]
    if not requirement_lines:
        errors.append("backend/requirements.lock must contain pinned runtime dependencies")
        return

    pattern = re.compile(
        r"^[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_,.-]+\])?==[^\s;\\]+(?:\s*;\s*[^\\]+)?\s+\\$"
    )
    for index, requirement in enumerate(requirement_lines):
        if pattern.fullmatch(requirement) is None:
            errors.append(f"backend/requirements.lock entry is not exactly pinned: {requirement}")
            continue
        start = lock.index(requirement)
        end = (
            lock.find("\n" + requirement_lines[index + 1], start)
            if index + 1 < len(requirement_lines)
            else len(lock)
        )
        if "--hash=sha256:" not in lock[start:end]:
            errors.append(f"backend/requirements.lock entry has no SHA-256 hash: {requirement}")

    locked_names = {_normalize_package_name(item) for item in requirement_lines}
    required_runtime_names = {"fastapi", "pydantic-settings", "redis", "uvicorn"}
    if not required_runtime_names.issubset(locked_names):
        errors.append("backend/requirements.lock is missing a direct runtime dependency")
    forbidden_dev_names = {"httpx", "mypy", "pip-tools", "pytest", "pytest-asyncio", "ruff"}
    if locked_names & forbidden_dev_names:
        errors.append("backend/requirements.lock must not contain direct development-only tools")


def _validate_python_documentation(root: Path, errors: list[str]) -> None:
    paths = (
        "README.md",
        "docs/04-engineering-standards.md",
        "docs/06-deployment-specification.md",
        "docs/superpowers/plans/2026-07-10-project-foundation.md",
    )
    for relative_path in paths:
        contents = _read_required(root, relative_path, errors)
        if contents and ("Python 3.12.13" not in contents or "Python 3.11" in contents):
            errors.append(f"{relative_path} must document Python 3.12.13 exactly")


def validate_repository(root: Path = REPOSITORY_ROOT) -> list[str]:
    errors: list[str] = []

    compose = _read_required(root, "docker-compose.yml", errors)
    if compose:
        _validate_compose(compose, errors)

    dockerfile = _read_required(root, "backend/Dockerfile", errors)
    if dockerfile:
        _validate_dockerfile(dockerfile, errors)

    pyproject = _read_required(root, "backend/pyproject.toml", errors)
    if pyproject:
        _validate_pyproject(pyproject, errors)

    lock = _read_required(root, "backend/requirements.lock", errors)
    if lock:
        _validate_requirements_lock(lock, errors)

    ci = _read_required(root, ".github/workflows/ci.yml", errors)
    if ci:
        _validate_ci(ci, errors)

    pages = _read_required(root, ".github/workflows/pages.yml", errors)
    if pages:
        _validate_pages(pages, errors)

    _validate_python_documentation(root, errors)

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
