"""API: endpoints, validation and errors, through FastAPI's test client."""
import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.config import Settings
from app.main import create_app
from app.schemas import RecommendationsResponse


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    db = tmp_path_factory.mktemp("api") / "circles.db"  # missing on purpose: startup seeds it
    with TestClient(create_app(Settings(db_path=db))) as test_client:
        yield test_client


def test_a1_health_and_docs(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert client.get("/docs").status_code == 200


def test_a1_the_root_url_redirects_to_the_docs(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/docs"
    assert client.get("/").status_code == 200  # following it lands on the docs page
    assert "/" not in client.get("/openapi.json").json()["paths"]  # kept out of the API schema


def test_a2_response_matches_the_contract(client):
    response = client.get("/users/7/recommendations")
    assert response.status_code == 200
    raw = response.json()
    body = RecommendationsResponse.model_validate(raw)
    assert (body.user_id, body.strategy, body.explanation_source) == (7, "personalized", "template")
    assert raw["as_of"] == "2026-09-21T00:00:00Z"
    assert body.profile_nudge is None and body.excluded is None
    assert [r.rank for r in body.recommendations] == [1, 2, 3, 4, 5]
    first = body.recommendations[0]
    assert first.circle.id == 5
    assert first.explanation == " ".join(reason.text for reason in first.reasons)
    assert [c.id for c in first.similar_circles] == [35, 1]


def test_a3_unknown_user_is_a_404(client):
    response = client.get("/users/999/recommendations")
    assert response.status_code == 404
    assert response.json() == {"detail": "User 999 not found"}


@pytest.mark.parametrize("query", ["limit=0", "limit=21", "limit=-1", "limit=five"])
def test_a4_invalid_limits_are_rejected(client, query):
    assert client.get(f"/users/7/recommendations?{query}").status_code == 422


def test_a4_limit_and_user_id_are_validated(client):
    assert len(client.get("/users/7/recommendations?limit=3").json()["recommendations"]) == 3
    assert len(client.get("/users/7/recommendations?limit=20").json()["recommendations"]) == 20
    assert client.get("/users/seven/recommendations").status_code == 422


def test_a5_debug_view_lists_exclusions_with_every_reason(client):
    body = client.get("/users/23/recommendations?include_excluded=true").json()
    assert body["recommendations"][0]["circle"]["id"] == 22
    excluded = {e["circle_id"]: e["reasons"] for e in body["excluded"]}
    assert excluded[20] == ["full"]
    assert excluded[21] == ["unlisted", "inactive"]
    assert excluded[23] == ["already_member"]


def test_a6_startup_seeds_a_missing_database_and_builds_the_catalog_once(tmp_path, monkeypatch):
    db = tmp_path / "fresh.db"
    builds = []
    real_loader = main_module.load_recommender

    def counting_loader(*args, **kwargs):
        builds.append(1)
        return real_loader(*args, **kwargs)

    monkeypatch.setattr(main_module, "load_recommender", counting_loader)
    with TestClient(create_app(Settings(db_path=db))) as fresh:
        assert db.exists()
        for user_id in (7, 15, 23, 42):
            assert fresh.get(f"/users/{user_id}/recommendations").status_code == 200
    assert builds == [1]


def test_x6_the_response_reports_which_explainer_wrote_the_copy(tmp_path):
    class Shout:
        source = "fake"

        def render(self, fact):
            return fact.code.upper()

    with TestClient(create_app(Settings(db_path=tmp_path / "x.db"), explainer=Shout())) as shouting:
        body = shouting.get("/users/7/recommendations").json()
    assert body["explanation_source"] == "fake"
    assert body["recommendations"][0]["explanation"] == "INTEREST_TOPIC MEMBERS_POSTING NEAR_YOU"
    assert body["recommendations"][0]["circle"]["id"] == 5
