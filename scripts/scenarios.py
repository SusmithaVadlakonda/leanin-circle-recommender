"""Print, record and check the recommendations for the planted scenarios.

Usage:
    python -m scripts.scenarios                  # print the four planted scenarios as markdown
    python -m scripts.scenarios --readme         # rewrite the README's results block
    python -m scripts.scenarios --check-readme   # fail if the README's results block is stale
    python -m scripts.scenarios --report         # write every user's results to reports/
    python -m scripts.scenarios --update-golden  # accept the planted results as the golden snapshot

Results always come from a fresh database seeded from data/, so they never depend on
the state of circles.db.
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

from app.explain import explain, nudge
from app.recommender import RecommendationSet, Recommender
from app.seed import PROJECT_ROOT, seed_db
from app.service import load_member, load_recommender

README = PROJECT_ROOT / "README.md"
GOLDEN = PROJECT_ROOT / "tests" / "golden" / "planted.json"
REPORT = PROJECT_ROOT / "reports" / "recommendations.md"
START, END = "<!-- scenarios:start -->", "<!-- scenarios:end -->"

SCENARIOS = {
    42: "Cold start",
    7: "Obvious matches",
    15: "Duplicate Circles",
    23: "Full or inactive Circles",
}
REASON_WORDS = {
    "full": "it's full",
    "unlisted": "it's unlisted",
    "inactive": "it's inactive",
}


def _profile_line(result: RecommendationSet, labels: dict[str, str]) -> str:
    member = result.member
    interests = ", ".join(labels.get(t, t) for t in member.topic_interests) or "none stated"
    location = member.location or "not set"
    line = f"Interests: {interests}. Location: {location}. Strategy: {result.strategy.replace('_', ' ')}."
    hint = nudge(result.strategy)
    return f"{line} Nudge: \"{hint}\"" if hint else line


def _table(result: RecommendationSet, engine: Recommender) -> list[str]:
    lines = ["| Rank | Circle | Why it's recommended | Similar Circles |", "|---|---|---|---|"]
    for rank, item in enumerate(explain(result, engine.topic_labels), start=1):
        circle = item.recommendation.circle
        similar = ", ".join(f"#{c.id} {c.name}" for c in item.recommendation.similar) or "none"
        lines.append(f"| {rank} | #{circle.id} {circle.name} | {item.explanation} | {similar} |")
    return lines


def _left_out(result: RecommendationSet, engine: Recommender) -> str | None:
    """Excluded Circles that match the member's stated interests, with the reasons."""
    interests = set(result.member.topic_interests)
    notes = []
    for exclusion in result.excluded:
        circle = exclusion.circle
        reasons = [REASON_WORDS[r] for r in exclusion.reasons if r in REASON_WORDS]
        if circle.topic in interests and reasons:
            notes.append(f"#{circle.id} {circle.name}, because {' and '.join(reasons)}")
    return "Left out: " + "; ".join(notes) + "." if notes else None


def render_scenarios(engine: Recommender, db_path: Path) -> str:
    blocks = []
    for user_id, title in SCENARIOS.items():
        result = engine.recommend(load_member(user_id, db_path))
        lines = [f"#### User {user_id}: {title}", "", _profile_line(result, engine.topic_labels), ""]
        lines += _table(result, engine)
        note = _left_out(result, engine)
        if note:
            lines += ["", note]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n"


def render_report(engine: Recommender, db_path: Path) -> str:
    lines = ["# Recommendations for every user", "", f"As of {engine.as_of.isoformat()}.", ""]
    for user_id in range(1, 101):
        result = engine.recommend(load_member(user_id, db_path))
        lines += [f"## User {user_id}", "", _profile_line(result, engine.topic_labels), ""]
        lines += _table(result, engine) + [""]
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

        block = "\n" + render_scenarios(engine, db_path)
        if args.readme or args.check_readme:
            text = README.read_text()
            start, end = _readme_block(text)
            if args.check_readme:
                if text[start:end] != block:
                    print("README results are stale: run `make docs` and commit the change.", file=sys.stderr)
                    return 1
                print("README results are current.")
                return 0
            README.write_text(text[:start] + block + text[end:])
            print("updated the README's results block")
            return 0

        print(block, end="")
        return 0


if __name__ == "__main__":
    sys.exit(main())
