"""Builds the recommender's domain objects from the database, for the API and the scripts."""
from datetime import datetime

from app import models
from app.models import DbPath
from app.recommender import Circle, Member, Recommender


def load_recommender(db_path: DbPath, as_of: datetime | None = None) -> Recommender:
    """Build the Circle catalog once. "Now" defaults to the latest timestamp in the data."""
    as_of = as_of or models.get_snapshot_time(db_path)
    circles = [Circle.from_row(row) for row in models.get_circle_catalog(as_of, db_path)]
    return Recommender(circles, models.get_topic_labels(db_path), as_of)


def load_member(user_id: int, db_path: DbPath) -> Member | None:
    """The member with their stated interests and Circles, or None if there's no such user."""
    user = models.get_user(user_id, db_path)
    if user is None:
        return None
    return Member.from_user(user, models.get_user_memberships(user_id, db_path))
