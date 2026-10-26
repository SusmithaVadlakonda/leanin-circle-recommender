"""Print, record and check the recommendations for the planted scenarios.

Usage:
    python -m scripts.scenarios                  # print the four planted scenarios as markdown
    python -m scripts.scenarios --readme         # rewrite the README's scenario block
    python -m scripts.scenarios --check-readme   # fail if the README's scenario block is stale
    python -m scripts.scenarios --report         # write every user's results to reports/
    python -m scripts.scenarios --update-golden  # accept the planted results as the golden snapshot

Results always come from a fresh database seeded from data/, so they never depend on
the state of circles.db. The README block calls the real API in process, so the input
and output it shows are exactly what a request returns.
"""
import argparse
import json
import sys
import tempfile
import warnings
from dataclasses import dataclass
from pathlib import Path

warnings.filterwarnings("ignore", message="Using .httpx. with .starlette.testclient. is deprecated")

from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.explain import explain, nudge  # noqa: E402
from app.main import create_app  # noqa: E402
from app.recommender import Member, RecommendationSet, Recommender  # noqa: E402
from app.seed import PROJECT_ROOT, seed_db  # noqa: E402
from app.service import load_member, load_recommender  # noqa: E402

README = PROJECT_ROOT / "README.md"
GOLDEN = PROJECT_ROOT / "tests" / "golden" / "planted.json"
REPORT = PROJECT_ROOT / "reports" / "recommendations.md"
START, END = "<!-- scenarios:start -->", "<!-- scenarios:end -->"
BASE_URL = "http://127.0.0.1:8000"


@dataclass(frozen=True)
class Scenario:
    title: str
    planted: str  # what the dataset README says was planted
    path: str  # the request shown as the input
    why: str  # why the output is right; every claim here is enforced by tests/test_scenarios.py


SCENARIOS = {
    42: Scenario(
        title="Cold start",
        planted="No memberships, no stated interests and an empty profile.",
        path="/users/42/recommendations",
        why="There's nothing to personalize on, so the list holds the most active open Circles, each on a "
        "different topic. All five are hybrid or virtual, because the member's location is unknown. "
        "The response asks the member to add interests.",
    ),
    7: Scenario(
        title="Obvious matches",
        planted="Interested in leadership skills and public speaking, with strong active Circles for both: "
        "#5 Women Who Lead and #6 Speak Up Circle.",
        path="/users/7/recommendations",
        why="Women Who Lead and Speak Up Circle take the first two places, as the dataset README expects.",
    ),
    15: Scenario(
        title="Duplicate Circles",
        planted="Interested in negotiation, where #10, #11 and #12 are three near-identical active Circles.",
        path="/users/15/recommendations",
        why="Only one negotiation Circle takes a slot. The other two are attached to it as similar Circles, "
        "so the member still sees them without losing three of five places to one topic.",
    ),
    23: Scenario(
        title="Full or inactive Circles",
        planted="Interested in getting promoted. #20 The Promotion Path is full and #21 Career Climbers is "
        "inactive, while #22 Level Up Collective is healthy.",
        path="/users/23/recommendations?include_excluded=true",
        why="Level Up Collective leads. The Promotion Path and Career Climbers appear nowhere, not even as "
        "similar Circles. The request turns on include_excluded, so the response lists them with the reasons.",
    ),
}
REASON_WORDS = {"already_member": "already a member", "full": "full", "unlisted": "unlisted", "inactive": "inactive"}


# ---- README block: input and output from the real API ---------------------------


def compact_json(value, indent: int = 0, width: int = 100) -> str:
    """Pretty JSON that keeps short objects and lists on one line, so a long response stays readable."""
    flat = json.dumps(value, ensure_ascii=False)
    if not isinstance(value, (dict, list)) or len(flat) + indent <= width:
        return flat
    pad = " " * (indent + 2)
    if isinstance(value, dict):
        items = [f"{pad}{json.dumps(k)}: {compact_json(v, indent + 2, width)}" for k, v in value.items()]
        return "{\n" + ",\n".join(items) + "\n" + " " * indent + "}"
    items = [f"{pad}{compact_json(v, indent + 2, width)}" for v in value]
    return "[\n" + ",\n".join(items) + "\n" + " " * indent + "]"


def _profile(member: Member, labels: dict[str, str]) -> str:
    interests = ", ".join(labels.get(t, t) for t in member.topic_interests)
    parts = [
        f"Stated interests: {interests}." if interests else "No stated interests.",
        f"Location: {member.location}." if member.location else "No location.",
        f'Bio: "{member.bio}"' if member.bio else "No bio.",
    ]
    return "**Profile.** " + " ".join(parts)


def _summary(body: dict) -> list[str]:
    lines = ["| Rank | Circle | Why it's recommended | Similar Circles |", "|---|---|---|---|"]
    for rec in body["recommendations"]:
        circle = rec["circle"]
        similar = ", ".join(f"#{s['id']} {s['name']}" for s in rec["similar_circles"]) or "none"
        lines.append(f"| {rec['rank']} | #{circle['id']} {circle['name']} | {rec['explanation']} | {similar} |")
    return lines


def _scenario_block(user_id: int, scenario: Scenario, body: dict, member: Member, labels: dict[str, str]) -> str:
    rendered = compact_json(body)
    assert json.loads(rendered) == body, "compact_json must not change the response"

    lines = [
        f"### User {user_id}: {scenario.title}",
        "",
        f"**What's planted.** {scenario.planted}",
        "",
        _profile(member, labels),
        "",
        "**Input**",
        "",
        "```bash",
        f'curl -s "{BASE_URL}{scenario.path}"',
        "```",
        "",
        "**Output**",
        "",
        f"Strategy: `{body['strategy']}`."
        + (f' Nudge: "{body["profile_nudge"]}"' if body["profile_nudge"] else ""),
        "",
        *_summary(body),
    ]
    if body["excluded"]:
        lines += ["", "Left out, from the response's excluded list:", ""]
        lines += [
            f"- #{e['circle_id']} {e['name']}: {', '.join(REASON_WORDS.get(r, r) for r in e['reasons'])}"
            for e in body["excluded"]
        ]
    lines += [
        "",
        f"**Why this is right.** {scenario.why}",
        "",
        "<details>",
        f"<summary>Full JSON response for user {user_id}</summary>",
        "",
        "```json",
        rendered,
        "```",
        "",
        "</details>",
    ]
    return "\n".join(lines)


def render_scenarios(db_path: Path, labels: dict[str, str]) -> str:
    blocks = []
    with TestClient(create_app(Settings(db_path=db_path))) as client:
        for user_id, scenario in SCENARIOS.items():
            response = client.get(scenario.path)
            response.raise_for_status()
            blocks.append(_scenario_block(user_id, scenario, response.json(), load_member(user_id, db_path), labels))
    return "\n\n".join(blocks) + "\n"


# ---- every-user report and the golden snapshot ------------------------------------


def _report_profile(result: RecommendationSet, labels: dict[str, str]) -> str:
    member = result.member
    interests = ", ".join(labels.get(t, t) for t in member.topic_interests) or "none stated"
    location = member.location or "not set"
    line = f"Interests: {interests}. Location: {location}. Strategy: {result.strategy.replace('_', ' ')}."
    hint = nudge(result.strategy)
    return f'{line} Nudge: "{hint}"' if hint else line


def _report_table(result: RecommendationSet, engine: Recommender) -> list[str]:
    lines = ["| Rank | Circle | Why it's recommended | Similar Circles |", "|---|---|---|---|"]
    for rank, item in enumerate(explain(result, engine.topic_labels), start=1):
        circle = item.recommendation.circle
        similar = ", ".join(f"#{c.id} {c.name}" for c in item.recommendation.similar) or "none"
        lines.append(f"| {rank} | #{circle.id} {circle.name} | {item.explanation} | {similar} |")
    return lines


def render_report(engine: Recommender, db_path: Path) -> str:
    lines = ["# Recommendations for every user", "", f"As of {engine.as_of.isoformat()}.", ""]
    for user_id in range(1, 101):
        result = engine.recommend(load_member(user_id, db_path))
        lines += [f"## User {user_id}", "", _report_profile(result, engine.topic_labels), ""]
        lines += _report_table(result, engine) + [""]
    return "\n".join(lines)


def planted_ids(engine: Recommender, db_path: Path) -> dict[str, list[int]]:
    return {
        str(uid): [r.circle.id for r in engine.recommend(load_member(uid, db_path)).recommendations]
        for uid in sorted(SCENARIOS)
    }


def _readme_block(readme_text: str) -> tuple[int, int]:
    start, end = readme_text.find(START), readme_text.find(END)
    if start == -1 or end == -1 or end < start:
        raise SystemExit(f"README.md has no {START} ... {END} block")
    return start + len(START), end


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--readme", action="store_true")
    action.add_argument("--check-readme", action="store_true")
    action.add_argument("--report", action="store_true")
    action.add_argument("--update-golden", action="store_true")
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "scenarios.db"
        seed_db(db_path)
        engine = load_recommender(db_path)

        if args.update_golden:
            GOLDEN.parent.mkdir(parents=True, exist_ok=True)
            # One user per line, so a ranking change shows up as a one-line diff.
            rows = [f"  {json.dumps(uid)}: {json.dumps(ids)}" for uid, ids in planted_ids(engine, db_path).items()]
            GOLDEN.write_text("{\n" + ",\n".join(rows) + "\n}\n")
            print(f"wrote {GOLDEN.relative_to(PROJECT_ROOT)}")
            return 0
        if args.report:
            REPORT.parent.mkdir(parents=True, exist_ok=True)
            REPORT.write_text(render_report(engine, db_path))
            print(f"wrote {REPORT.relative_to(PROJECT_ROOT)}")
            return 0

        block = "\n" + render_scenarios(db_path, engine.topic_labels)
        if args.readme or args.check_readme:
            text = README.read_text()
            start, end = _readme_block(text)
            if args.check_readme:
                if text[start:end] != block:
                    print("README scenarios are stale: run `make docs` and commit the change.", file=sys.stderr)
                    return 1
                print("README scenarios are current.")
                return 0
            README.write_text(text[:start] + block + text[end:])
            print("updated the README's scenario block")
            return 0

        print(block, end="")
        return 0


if __name__ == "__main__":
    sys.exit(main())
