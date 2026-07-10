from __future__ import annotations

import json
import re
import sys
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
    if not instructions or instructions[0] != ("FROM", "python:3.12-slim"):
        errors.append("backend/Dockerfile must start from python:3.12-slim")

    copies = [argument for instruction, argument in instructions if instruction == "COPY"]
    if not any(re.fullmatch(r"(?:--\S+\s+)*pyproject\.toml\s+\.?/?", item) for item in copies):
        errors.append("backend/Dockerfile must copy pyproject.toml before installing dependencies")
    if not any(re.fullmatch(r"(?:--\S+\s+)*app\s+\.?/?app/?", item) for item in copies):
        errors.append("backend/Dockerfile must copy the application package")

    runs = [argument for instruction, argument in instructions if instruction == "RUN"]
    install_pattern = re.compile(r"^python\s+-m\s+pip\s+install(?:\s+\S+)*\s+\.$")
    if not any(install_pattern.fullmatch(run) for run in runs):
        errors.append("backend/Dockerfile must install project runtime dependencies")

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
    if jobs is None or set(jobs) != {"backend", "frontend"}:
        errors.append("ci.yml must define exactly backend and frontend jobs")
        return

    expected_jobs = {
        "backend": (
            "backend",
            ["python -m pip install -e \".[dev]\"", "ruff check .", "mypy app", "pytest"],
            {"actions/checkout@v4", "actions/setup-python@v5"},
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
            {"actions/checkout@v4", "pnpm/action-setup@v4", "actions/setup-node@v4"},
        ),
    }
    for job_name, (directory, commands, actions) in expected_jobs.items():
        job = jobs[job_name]
        if _working_directory(job) != directory:
            errors.append(f"ci.yml {job_name} job must run from {directory}")
        steps = _job_steps(job, f"ci.yml {job_name} job", errors)
        if steps is None:
            continue
        if _run_commands(steps) != commands:
            errors.append(f"ci.yml {job_name} job commands do not match the contract")
        if set(_uses(steps)) != actions:
            errors.append(f"ci.yml {job_name} job actions do not match the contract")


def _validate_pages(pages: str, errors: list[str]) -> None:
    document = _load_yaml(pages, ".github/workflows/pages.yml", errors)
    if document is None:
        return
    triggers, permissions, jobs = _workflow_parts(document, ".github/workflows/pages.yml", errors)
    push = _mapping(triggers.get("push")) if triggers else None
    if push is None or push.get("branches") != ["main"] or "workflow_dispatch" not in triggers:
        errors.append("pages.yml must run for main pushes and workflow dispatches")
    expected_permissions = {"contents": "read", "pages": "write", "id-token": "write"}
    if permissions != expected_permissions:
        errors.append("pages.yml permissions do not match the least-privilege contract")
    if jobs is None or set(jobs) != {"deploy"}:
        errors.append("pages.yml must define exactly the deploy job")
        return
    steps = _job_steps(jobs["deploy"], "pages.yml deploy job", errors)
    if steps is None:
        return

    expected_actions = [
        "actions/checkout@v4",
        "pnpm/action-setup@v4",
        "actions/setup-node@v4",
        "actions/configure-pages@v5",
        "actions/upload-pages-artifact@v3",
        "actions/deploy-pages@v4",
    ]
    if _uses(steps) != expected_actions:
        errors.append("pages.yml actions do not match the deployment contract")

    expected_commands = [
        "pnpm install --frozen-lockfile",
        "pnpm lint",
        "pnpm typecheck",
        "pnpm test --run",
        "pnpm build",
    ]
    run_steps = [step for step in steps if "run" in step]
    if _run_commands(steps) != expected_commands:
        errors.append("pages.yml commands do not match the build contract")
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
        (step for step in steps if step.get("uses") == "actions/upload-pages-artifact@v3"), None
    )
    if upload_step is None or _mapping(upload_step.get("with")) != {"path": "frontend/dist"}:
        errors.append("pages.yml must upload frontend/dist as the Pages artifact")
    deploy_step = next(
        (step for step in steps if step.get("uses") == "actions/deploy-pages@v4"), None
    )
    if deploy_step is None or deploy_step.get("id") != "deployment":
        errors.append("pages.yml deploy-pages step must expose the deployment result")


def validate_repository(root: Path = REPOSITORY_ROOT) -> list[str]:
    errors: list[str] = []

    compose = _read_required(root, "docker-compose.yml", errors)
    if compose:
        _validate_compose(compose, errors)

    dockerfile = _read_required(root, "backend/Dockerfile", errors)
    if dockerfile:
        _validate_dockerfile(dockerfile, errors)

    ci = _read_required(root, ".github/workflows/ci.yml", errors)
    if ci:
        _validate_ci(ci, errors)

    pages = _read_required(root, ".github/workflows/pages.yml", errors)
    if pages:
        _validate_pages(pages, errors)

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
