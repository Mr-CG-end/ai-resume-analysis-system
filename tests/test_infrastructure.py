from pathlib import Path

from scripts.validate_infrastructure import validate_repository

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_infrastructure_configuration_matches_contract() -> None:
    assert validate_repository(REPOSITORY_ROOT) == []
