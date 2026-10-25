"""Response models. They define the JSON contract and the interactive docs at /docs."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class HealthOut(BaseModel):
    status: Literal["ok"]


class CircleOut(BaseModel):
    id: int
    name: str
    slug: str
    description: str | None
    topic: str | None
    topic_label: str | None
    format: Literal["in_person", "virtual", "hybrid"]
    join_policy: Literal["open", "request"]
    member_count: int
    max_members: int | None = Field(description="Null means the Circle is uncapped.")
    spots_left: int | None = Field(description="Null means the Circle is uncapped.")
    cover_image_url: str | None


class SimilarCircleOut(BaseModel):
    id: int
    name: str
    format: Literal["in_person", "virtual", "hybrid"]


class ReasonOut(BaseModel):
    code: str = Field(description="Stable reason code, such as interest_topic or request_to_join.")
    text: str


class RecommendationOut(BaseModel):
    rank: int
    score: float = Field(description="For debugging and tuning. Not meant for display to members.")
    circle: CircleOut
    explanation: str = Field(description="Member-facing sentence: the three reasons joined.")
    reasons: list[ReasonOut]
    similar_circles: list[SimilarCircleOut] = Field(
        description="Near-duplicate Circles on the same topic, folded under this result."
    )


class ExcludedOut(BaseModel):
    circle_id: int
    name: str
    reasons: list[str] = Field(description="Every reason: already_member, unlisted, full or inactive.")


class RecommendationsResponse(BaseModel):
    user_id: int
    as_of: datetime = Field(description='The moment treated as "now" for activity calculations.')
    strategy: Literal["personalized", "inferred", "cold_start"]
    profile_nudge: str | None = Field(description="A prompt to add interests, when the member has none.")
    explanation_source: str = Field(description='What wrote the explanations: "template" in this version.')
    recommendations: list[RecommendationOut]
    excluded: list[ExcludedOut] | None = Field(
        default=None, description="Null unless include_excluded=true."
    )
