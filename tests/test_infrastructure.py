import re
import shutil
from pathlib import Path

import pytest
import yaml

from scripts.validate_infrastructure import validate_repository

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
INFRASTRUCTURE_PATHS = (
    "docker-compose.yml",
    "backend/Dockerfile",
    "backend/pyproject.toml",
    "backend/requirements.lock",
    ".github/workflows/ci.yml",
    ".github/workflows/pages.yml",
    "README.md",
    "docs/04-engineering-standards.md",
    "docs/06-deployment-specification.md",
    "docs/superpowers/plans/2026-07-10-project-foundation.md",
)


@pytest.fixture
def repository_copy(tmp_path: Path) -> Path:
    for relative_path in INFRASTRUCTURE_PATHS:
        source = REPOSITORY_ROOT / relative_path
        if not source.is_file():
            continue
        destination = tmp_path / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    return tmp_path


def _replace(repository: Path, relative_path: str, old: str, new: str) -> None:
    path = repository / relative_path
    original = path.read_text(encoding="utf-8")
    assert old in original
    path.write_text(original.replace(old, new, 1), encoding="utf-8")


def _load_yaml(relative_path: str) -> dict[str, object]:
    contents = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
    document = yaml.load(contents, Loader=yaml.BaseLoader)
    assert isinstance(document, dict)
    return document


def _workflow_actions(relative_path: str) -> list[str]:
    document = _load_yaml(relative_path)
    jobs = document["jobs"]
    assert isinstance(jobs, dict)
    return [
        step["uses"]
        for job in jobs.values()
        for step in job["steps"]
        if "uses" in step
    ]


def test_infrastructure_configuration_matches_contract() -> None:
    assert validate_repository(REPOSITORY_ROOT) == []


def test_ci_runs_backend_root_and_frontend_checks_on_python_3_12_13() -> None:
    document = _load_yaml(".github/workflows/ci.yml")
    jobs = document["jobs"]
    assert isinstance(jobs, dict)
    assert set(jobs) == {"backend", "infrastructure", "frontend"}

    backend_commands = [step["run"] for step in jobs["backend"]["steps"] if "run" in step]
    assert backend_commands == [
        'python -m pip install -e ".[dev]"',
        "ruff format --check .",
        "ruff check .",
        "mypy app",
        "pytest",
    ]
    infrastructure_commands = [
        step["run"] for step in jobs["infrastructure"]["steps"] if "run" in step
    ]
    assert infrastructure_commands == [
        'python -m pip install -e "./backend[dev]"',
        "pytest tests/test_infrastructure.py",
        "python scripts/validate_infrastructure.py",
    ]

    setup_python_steps = [
        step
        for job in jobs.values()
        for step in job["steps"]
        if step.get("uses") == "actions/setup-python@v6"
    ]
    assert len(setup_python_steps) == 2
    assert all(step.get("with", {}).get("python-version") == "3.12.13" for step in setup_python_steps)


def test_ci_uses_current_stable_action_major_versions() -> None:
    assert _workflow_actions(".github/workflows/ci.yml") == [
        "actions/checkout@v7",
        "actions/setup-python@v6",
        "actions/checkout@v7",
        "actions/setup-python@v6",
        "actions/checkout@v7",
        "pnpm/action-setup@v6",
        "actions/setup-node@v6",
    ]


def test_pages_separates_build_and_deploy_permissions() -> None:
    document = _load_yaml(".github/workflows/pages.yml")
    assert document["permissions"] == {}
    jobs = document["jobs"]
    assert isinstance(jobs, dict)
    assert set(jobs) == {"build", "deploy"}

    build = jobs["build"]
    deploy = jobs["deploy"]
    assert build["permissions"] == {"contents": "read"}
    assert "environment" not in build
    assert deploy["permissions"] == {"pages": "write", "id-token": "write"}
    assert deploy["needs"] == "build"
    assert deploy["environment"]["name"] == "github-pages"
    assert [step["uses"] for step in deploy["steps"]] == ["actions/deploy-pages@v5"]


def test_pages_uses_current_stable_action_major_versions() -> None:
    assert _workflow_actions(".github/workflows/pages.yml") == [
        "actions/checkout@v7",
        "pnpm/action-setup@v6",
        "actions/setup-node@v6",
        "actions/configure-pages@v6",
        "actions/upload-pages-artifact@v4",
        "actions/deploy-pages@v5",
    ]


def test_redis_port_is_bound_to_loopback() -> None:
    document = _load_yaml("docker-compose.yml")
    assert document["services"]["redis"]["ports"] == ["127.0.0.1:6379:6379"]


def test_python_and_production_lock_contract_are_exact() -> None:
    pyproject = (REPOSITORY_ROOT / "backend/pyproject.toml").read_text(encoding="utf-8")
    assert 'requires-python = "==3.12.13"' in pyproject
    assert '"pip-tools' in pyproject

    dockerfile = (REPOSITORY_ROOT / "backend/Dockerfile").read_text(encoding="utf-8")
    assert dockerfile.startswith("FROM python:3.12.13-slim-bookworm\n")
    assert "COPY requirements.lock ./\n" in dockerfile
    assert "RUN python -m pip install --no-cache-dir --require-hashes -r requirements.lock\n" in dockerfile
    assert dockerfile.index("RUN python -m pip install") < dockerfile.index("COPY app ./app")

    lock_path = REPOSITORY_ROOT / "backend/requirements.lock"
    assert lock_path.is_file()
    lock = lock_path.read_text(encoding="utf-8")
    requirement_lines = [
        line
        for line in lock.splitlines()
        if line and not line.startswith((" ", "#", "--"))
    ]
    assert requirement_lines
    for index, requirement in enumerate(requirement_lines):
        assert re.match(r"^[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_,.-]+\])?==\S+ \\$", requirement)
        start = lock.index(requirement)
        end = lock.find("\n" + requirement_lines[index + 1], start) if index + 1 < len(requirement_lines) else len(lock)
        assert "--hash=sha256:" in lock[start:end]

    dev_only = ("httpx==", "mypy==", "pip-tools==", "pytest==", "pytest-asyncio==", "ruff==")
    assert not any(line.lower().startswith(dev_only) for line in requirement_lines)


@pytest.mark.parametrize(
    "relative_path",
    [
        "README.md",
        "docs/04-engineering-standards.md",
        "docs/06-deployment-specification.md",
        "docs/superpowers/plans/2026-07-10-project-foundation.md",
    ],
)
def test_documented_python_version_is_exact(relative_path: str) -> None:
    contents = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
    assert "Python 3.12.13" in contents
    assert "Python 3.11" not in contents


def test_rejects_persistent_redis_volume(repository_copy: Path) -> None:
    _replace(
        repository_copy,
        "docker-compose.yml",
        "    image: redis:7\n",
        "    image: redis:7\n    volumes:\n      - redis-data:/data\n",
    )
    path = repository_copy / "docker-compose.yml"
    path.write_text(path.read_text(encoding="utf-8") + "\nvolumes:\n  redis-data:\n")

    assert validate_repository(repository_copy)


def test_rejects_wildcard_redis_port_publication(repository_copy: Path) -> None:
    path = repository_copy / "docker-compose.yml"
    contents = path.read_text(encoding="utf-8")
    contents = contents.replace("127.0.0.1:6379:6379", "0.0.0.0:6379:6379")
    path.write_text(contents, encoding="utf-8")

    assert validate_repository(repository_copy)


def test_rejects_redis_healthcheck_at_wrong_level(repository_copy: Path) -> None:
    _replace(
        repository_copy,
        "docker-compose.yml",
        "    healthcheck:\n"
        '      test: ["CMD", "redis-cli", "ping"]\n'
        "      interval: 5s\n"
        "      timeout: 3s\n"
        "      retries: 5\n",
        "healthcheck:\n"
        '  test: ["CMD", "redis-cli", "ping"]\n'
        "  interval: 5s\n"
        "  timeout: 3s\n"
        "  retries: 5\n",
    )

    assert validate_repository(repository_copy)


def test_rejects_ci_without_root_infrastructure_job(repository_copy: Path) -> None:
    ci_path = repository_copy / ".github/workflows/ci.yml"
    document = yaml.load(ci_path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    if "infrastructure" in document["jobs"]:
        del document["jobs"]["infrastructure"]
        ci_path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    assert validate_repository(repository_copy)


def test_rejects_ci_command_present_only_in_comment(repository_copy: Path) -> None:
    _replace(
        repository_copy,
        ".github/workflows/ci.yml",
        "      - run: mypy app\n",
        "      # required command: mypy app\n",
    )

    assert validate_repository(repository_copy)


def test_rejects_ci_trigger_present_only_in_comment(repository_copy: Path) -> None:
    _replace(
        repository_copy,
        ".github/workflows/ci.yml",
        "  pull_request:\n",
        "  # pull_request:\n",
    )

    assert validate_repository(repository_copy)


def test_rejects_extra_ci_permission(repository_copy: Path) -> None:
    _replace(
        repository_copy,
        ".github/workflows/ci.yml",
        "  contents: read\n",
        "  contents: read\n  issues: write\n",
    )

    assert validate_repository(repository_copy)


def test_rejects_python_version_drift(repository_copy: Path) -> None:
    dockerfile_path = repository_copy / "backend/Dockerfile"
    contents = dockerfile_path.read_text(encoding="utf-8")
    contents = contents.replace("python:3.12.13-slim-bookworm", "python:3.12-slim")
    dockerfile_path.write_text(contents, encoding="utf-8")

    assert validate_repository(repository_copy)


def test_rejects_dockerfile_without_hash_locked_install(repository_copy: Path) -> None:
    dockerfile_path = repository_copy / "backend/Dockerfile"
    contents = dockerfile_path.read_text(encoding="utf-8")
    contents = contents.replace(" --require-hashes", "")
    dockerfile_path.write_text(contents, encoding="utf-8")

    assert validate_repository(repository_copy)


def test_rejects_missing_production_lock(repository_copy: Path) -> None:
    lock_path = repository_copy / "backend/requirements.lock"
    if lock_path.exists():
        lock_path.unlink()

    assert validate_repository(repository_copy)


def test_rejects_combined_pages_build_and_deploy_job(repository_copy: Path) -> None:
    pages_path = repository_copy / ".github/workflows/pages.yml"
    document = yaml.load(pages_path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    if "build" in document["jobs"]:
        document["jobs"] = {"deploy": document["jobs"]["build"]}
        pages_path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    assert validate_repository(repository_copy)


def test_rejects_pages_permissions_crossing_job_boundary(repository_copy: Path) -> None:
    pages_path = repository_copy / ".github/workflows/pages.yml"
    document = yaml.load(pages_path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    if "build" in document["jobs"]:
        document["jobs"]["build"]["permissions"]["pages"] = "write"
        document["jobs"]["deploy"]["permissions"]["contents"] = "read"
        pages_path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    assert validate_repository(repository_copy)


def test_rejects_pages_build_environment_on_wrong_step(repository_copy: Path) -> None:
    _replace(
        repository_copy,
        ".github/workflows/pages.yml",
        "        env:\n"
        "          VITE_API_BASE_URL: ${{ vars.VITE_API_BASE_URL }}\n"
        "          VITE_BASE_PATH: /${{ github.event.repository.name }}/\n",
        "",
    )

    assert validate_repository(repository_copy)
