"""Shared fixtures. Tests never touch the circles.db at the project root."""
import pytest

from app.seed import seed_db


@pytest.fixture(scope="session")
def db_path(tmp_path_factory):
    """A database seeded from data/ in a temporary folder, shared by the session."""
    path = tmp_path_factory.mktemp("db") / "circles.db"
    seed_db(path)
    return path


@pytest.fixture(scope="session")
def engine(db_path):
    """The recommender over the seeded catalog, as of the data's snapshot time."""
    from app.service import load_recommender

    return load_recommender(db_path)


@pytest.fixture(scope="session")
def members(db_path):
    """Every user in the dataset as a Member, keyed by id."""
    from app.service import load_member

    return {user_id: load_member(user_id, db_path) for user_id in range(1, 101)}
