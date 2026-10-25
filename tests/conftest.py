"""Shared fixtures. Tests never touch the circles.db at the project root."""
import pytest

from app.seed import seed_db


@pytest.fixture(scope="session")
def db_path(tmp_path_factory):
    """A database seeded from data/ in a temporary folder, shared by the session."""
    path = tmp_path_factory.mktemp("db") / "circles.db"
    seed_db(path)
    return path
