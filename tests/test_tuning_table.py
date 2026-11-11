"""The README tuning table is generated from tuning.py and must not drift from it."""

from dataclasses import fields

from tools import tuning_table
from tuning import Tuning


def test_readme_table_matches_tuning_py():
    readme = tuning_table.README.read_text(encoding="utf-8")
    assert readme == tuning_table.render_readme(readme, tuning_table.table()), (
        "README tuning table is out of date: uv run python tools/tuning_table.py --write"
    )


def test_every_field_has_an_explanation():
    keys = {key: text for _, items in tuning_table.rows() for key, text in items}
    assert set(keys) == {f.name for f in fields(Tuning)}
    assert all(keys.values()), [k for k, v in keys.items() if not v]


def test_continuation_comments_point_at_their_base_key():
    src = (
        "class Tuning:\n"
        "    # ---- moves\n"
        "    chase_speed: float = 1.0  # px/s ...\n"
        "    chase_speed_per_rage: float = 2.0  # ... plus this much at full rage\n"
    )
    assert tuning_table.rows(src) == [
        (
            "moves",
            [
                ("chase_speed", "px/s"),
                ("chase_speed_per_rage", "plus this much at full rage (goes with `chase_speed`)"),
            ],
        )
    ]


def test_defaults_are_formatted_for_people():
    assert tuning_table._fmt(0.5) == "0.5"
    assert tuning_table._fmt(120.0) == "120"
    assert tuning_table._fmt((30.0, 60.0)) == "[30, 60]"
    assert tuning_table._fmt({"popup": 1.5}) == "popup 1.5"
