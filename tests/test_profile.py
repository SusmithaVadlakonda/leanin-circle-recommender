"""Interest profile: stated interests, bio keywords, and the topics of a member's Circles."""
import json
from collections import Counter

import pytest
from factories import SNAPSHOT, make_circle, make_member

from app import models
from app.recommender import Circle, Member, build_profile, strategy_for, topics_in_text
from app.seed import DATA_DIR

# The generator's six generic bios, with the topics a reader would take from each.
GENERIC_BIOS = {
    "Building my leadership toolkit one conversation at a time.": {"leadership-skills"},
    "First-time manager figuring it out alongside a great team.": {"managing-a-team"},
    "Career changer, ex-consultant, now in tech.": set(),
    "Passionate about mentoring the next generation of women leaders.": {
        "leadership-skills",
        "sponsorship-mentorship",
    },
    "Returning to work after a career break and finding my footing.": {"career-breaks"},
    "Advocate for pay equity and transparent promotion paths.": {"negotiation", "getting-promoted"},
}
PLANTED = (7, 15, 23, 42)


def _sources(profile):
    return {topic: (i.source, i.weight) for topic, i in profile.items()}


def test_p1_each_source_has_its_weight():
    member = make_member(
        topic_interests=["negotiation"],
        bio="Passionate about mentoring the next generation of women leaders.",
        circle_ids={1},
    )
    profile = build_profile(member, {1: make_circle(id=1, topic="resilience")})
    assert _sources(profile) == {
        "negotiation": ("stated", 1.0),
        "leadership-skills": ("bio", 0.6),
        "sponsorship-mentorship": ("bio", 0.6),
    }


def test_p1_a_stated_interest_outranks_the_same_topic_in_the_bio():
    member = make_member(topic_interests=["negotiation"], bio="Prepping for a big comp conversation.")
    assert _sources(build_profile(member, {})) == {"negotiation": ("stated", 1.0)}


def test_p2_circle_topics_apply_only_without_stated_interests():
    circles = {
        1: make_circle(id=1, name="Seen & Heard", topic="visibility-recognition"),
        2: make_circle(id=2, topic=None),
    }
    profile = build_profile(make_member(circle_ids={1, 2}), circles)
    assert {t: (i.source, i.weight, i.via_circle) for t, i in profile.items()} == {
        "visibility-recognition": ("circle", 0.4, "Seen & Heard"),
    }

    with_stated = make_member(topic_interests=["negotiation"], circle_ids={1})
    assert "visibility-recognition" not in build_profile(with_stated, circles)


def test_p2_a_bio_topic_outranks_the_same_topic_from_a_circle():
    member = make_member(
        bio="First-time manager figuring it out alongside a great team.", circle_ids={1}
    )
    profile = build_profile(member, {1: make_circle(id=1, topic="managing-a-team")})
    assert _sources(profile) == {"managing-a-team": ("bio", 0.6)}


@pytest.mark.parametrize("bio, topics", GENERIC_BIOS.items())
def test_p3_keyword_list_maps_each_generic_bio(bio, topics):
    assert set(topics_in_text(bio)) == topics


def test_p3_generic_bios_are_exactly_the_datasets_unplanted_bios():
    users = json.loads((DATA_DIR / "users.json").read_text())
    unplanted = {u["bio"] for u in users if u["bio"] and u["id"] not in PLANTED}
    assert unplanted == set(GENERIC_BIOS)


def test_p3_planted_bios_restate_their_stated_interests():
    users = {u["id"]: u for u in json.loads((DATA_DIR / "users.json").read_text())}
    for uid in (7, 15, 23):
        assert set(topics_in_text(users[uid]["bio"])) == set(users[uid]["topic_interests"])


def test_p4_a_member_with_nothing_gets_cold_start():
    member = make_member()
    profile = build_profile(member, {})
    assert profile == {}
    assert strategy_for(member, profile) == "cold_start"
    assert strategy_for(make_member(topic_interests=["confidence"]), {"confidence": None}) == "personalized"
    bio_only = make_member(bio="Returning to work after a career break.")
    assert strategy_for(bio_only, build_profile(bio_only, {})) == "inferred"


def test_strategy_split_across_the_dataset(db_path):
    circles = {
        row["id"]: Circle.from_row(row) for row in models.get_circle_catalog(SNAPSHOT, db_path)
    }
    split = Counter()
    for user_id in range(1, 101):
        user = models.get_user(user_id, db_path)
        member = Member.from_user(user, models.get_user_memberships(user_id, db_path))
        split[strategy_for(member, build_profile(member, circles))] += 1
    # 70 stated interests, 12 bio only, 17 memberships only, and user 42.
    assert split == {"personalized": 70, "inferred": 29, "cold_start": 1}
