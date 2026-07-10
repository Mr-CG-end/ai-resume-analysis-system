import shutil
from pathlib import Path

import pytest
import yaml

from scripts.validate_infrastructure import validate_repository

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
INFRASTRUCTURE_PATHS = (
    "docker-compose.yml",
    "backend/Dockerfile",
    ".github/workflows/ci.yml",
    ".github/workflows/pages.yml",
)


@pytest.fixture
def repository_copy(tmp_path: Path) -> Path:
    for relative_path in INFRASTRUCTURE_PATHS:
        source = REPOSITORY_ROOT / relative_path
        destination = tmp_path / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    return tmp_path


def _replace(repository: Path, relative_path: str, old: str, new: str) -> None:
    path = repository / relative_path
    original = path.read_text(encoding="utf-8")
    assert old in original
    path.write_text(original.replace(old, new, 1), encoding="utf-8")


def test_infrastructure_configuration_matches_contract() -> None:
    assert validate_repository(REPOSITORY_ROOT) == []


def _workflow_actions(relative_path: str) -> list[str]:
    contents = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
    document = yaml.load(contents, Loader=yaml.BaseLoader)
    return [
        step["uses"]
        for job in document["jobs"].values()
        for step in job["steps"]
        if "uses" in step
    ]


def test_ci_uses_current_stable_action_major_versions() -> None:
    assert _workflow_actions(".github/workflows/ci.yml") == [
        "actions/checkout@v7",
        "actions/setup-python@v6",
        "actions/checkout@v7",
        "pnpm/action-setup@v6",
        "actions/setup-node@v6",
    ]


def test_pages_uses_current_stable_action_major_versions() -> None:
    assert _workflow_actions(".github/workflows/pages.yml") == [
        "actions/checkout@v7",
        "pnpm/action-setup@v6",
        "actions/setup-node@v6",
        "actions/configure-pages@v6",
        "actions/upload-pages-artifact@v4",
        "actions/deploy-pages@v5",
    ]


def test_rejects_persistent_redis_volume(repository_copy: Path) -> None:
    _replace(
        repository_copy,
        "docker-compose.yml",
        '    image: redis:7\n',
        '    image: redis:7\n    volumes:\n      - redis-data:/data\n',
    )
    path = repository_copy / "docker-compose.yml"
    path.write_text(path.read_text(encoding="utf-8") + "\nvolumes:\n  redis-data:\n")

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


def test_rejects_dockerfile_without_dependency_install(repository_copy: Path) -> None:
    _replace(
        repository_copy,
        "backend/Dockerfile",
        "RUN python -m pip install --no-cache-dir .\n",
        "# RUN python -m pip install --no-cache-dir .\n",
    )

    assert validate_repository(repository_copy)


def test_rejects_dockerfile_command_present_only_in_comment(repository_copy: Path) -> None:
    _replace(
        repository_copy,
        "backend/Dockerfile",
        'CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]\n',
        '# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]\n'
        'CMD ["uvicorn", "app.main:app"]\n',
    )

    assert validate_repository(repository_copy)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("  id-token: write\n", "  id-token: write\n  issues: write\n"),
        ("          VITE_API_BASE_URL: ${{ vars.VITE_API_BASE_URL }}\n", ""),
        (
            "          VITE_API_BASE_URL: ${{ vars.VITE_API_BASE_URL }}\n",
            "          VITE_API_BASE_URL: ${{ secrets.VITE_API_BASE_URL }}\n",
        ),
    ],
)
def test_rejects_pages_permission_or_api_variable_regressions(
    repository_copy: Path, old: str, new: str
) -> None:
    _replace(repository_copy, ".github/workflows/pages.yml", old, new)

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


def test_rejects_ci_command_in_wrong_job(repository_copy: Path) -> None:
    _replace(
        repository_copy,
        ".github/workflows/ci.yml",
        "      - run: mypy app\n",
        "      - run: echo mypy app\n",
    )

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
    _replace(
        repository_copy,
        ".github/workflows/pages.yml",
        "      - run: pnpm lint\n        working-directory: frontend\n",
        "      - run: pnpm lint\n"
        "        working-directory: frontend\n"
        "        env:\n"
        "          VITE_API_BASE_URL: ${{ vars.VITE_API_BASE_URL }}\n"
        "          VITE_BASE_PATH: /${{ github.event.repository.name }}/\n",
    )

    assert validate_repository(repository_copy)
