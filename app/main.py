"""FastAPI app: GET /health and GET /users/{user_id}/recommendations.

Run it with `make run`, or `uvicorn app.main:app`. Interactive docs are at /docs.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from app.config import Settings
from app.explain import Explained, Explainer, TemplateExplainer, explain, nudge
from app.recommender import DEFAULT_LIMIT, Circle, RecommendationSet
from app.schemas import (
    CircleOut,
    ExcludedOut,
    HealthOut,
    ReasonOut,
    RecommendationOut,
    RecommendationsResponse,
    SimilarCircleOut,
)
from app.seed import seed_db
from app.service import load_member, load_recommender

MAX_LIMIT = 20


def create_app(settings: Settings | None = None, explainer: Explainer | None = None) -> FastAPI:
    """Build the app. Tests pass their own settings and explainer; the server uses the environment."""
    settings = settings or Settings.from_env()
    explainer = explainer or TemplateExplainer()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not settings.db_path.exists():
            seed_db(settings.db_path)
        # Built once: Circle features don't change between requests. Restart after reseeding.
        app.state.engine = load_recommender(settings.db_path, settings.as_of)
        yield

    app = FastAPI(
        title="Lean In Circle Recommender",
        version="1.0.0",
        summary="Recommends relevant, active Lean In Circles, with a short reason for each.",
        lifespan=lifespan,
    )

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        """The address uvicorn prints at startup. Send whoever opens it to the interactive docs."""
        return RedirectResponse(url="/docs")

    @app.get("/health", response_model=HealthOut, tags=["meta"])
    def health() -> HealthOut:
        return HealthOut(status="ok")

    @app.get(
        "/users/{user_id}/recommendations",
        response_model=RecommendationsResponse,
        tags=["recommendations"],
        responses={404: {"description": "No user with this id"}},
    )
    def recommendations(
        request: Request,
        user_id: int,
        limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT, description="How many Circles to return."),
        include_excluded: bool = Query(
            False, description="Debug view: also list the Circles that were excluded, with every reason."
        ),
    ) -> RecommendationsResponse:
        member = load_member(user_id, settings.db_path)
        if member is None:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")
        engine = request.app.state.engine
        result = engine.recommend(member, limit=limit)
        explained = explain(result, engine.topic_labels, explainer)
        return to_response(result, explained, explainer.source, include_excluded)

    return app


def _circle_out(circle: Circle) -> CircleOut:
    return CircleOut(
        id=circle.id,
        name=circle.name,
        slug=circle.slug,
        description=circle.description,
        topic=circle.topic,
        topic_label=circle.topic_label,
        format=circle.format,
        join_policy=circle.join_policy,
        member_count=circle.member_count,
        max_members=circle.max_members,
        spots_left=circle.spots_left,
        cover_image_url=circle.cover_image_url,
    )


def to_response(
    result: RecommendationSet, explained: list[Explained], source: str, include_excluded: bool
) -> RecommendationsResponse:
    return RecommendationsResponse(
        user_id=result.member.id,
        as_of=result.as_of,
        strategy=result.strategy,
        profile_nudge=nudge(result.strategy),
        explanation_source=source,
        recommendations=[
            RecommendationOut(
                rank=rank,
                score=round(item.recommendation.score, 3),
                circle=_circle_out(item.recommendation.circle),
                explanation=item.explanation,
                reasons=[ReasonOut(code=r.code, text=r.text) for r in item.reasons],
                similar_circles=[
                    SimilarCircleOut(id=c.id, name=c.name, format=c.format) for c in item.recommendation.similar
                ],
            )
            for rank, item in enumerate(explained, start=1)
        ],
        excluded=(
            [ExcludedOut(circle_id=e.circle.id, name=e.circle.name, reasons=list(e.reasons)) for e in result.excluded]
            if include_excluded
            else None
        ),
    )


app = create_app()
