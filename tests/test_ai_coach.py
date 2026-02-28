"""Tests for the exercise-to-split filtering logic in ai_coach."""

import pytest

from handlers.ai_coach import (
    SESSION_MUSCLE_GROUPS,
    SPLIT_SESSIONS,
    _ALL_MUSCLE_GROUPS,
    _filter_exercises_for_session,
)


def _ex(name: str, muscle_group: str, sets: int = 3) -> dict:
    """Helper to build a minimal exercise dict."""
    return {
        "name": name,
        "muscle_group": muscle_group,
        "sets": sets,
        "sets_config": [{"weight": 60, "reps": 10}] * sets,
    }


# ── PPL ──────────────────────────────────────────────────────────────────

class TestPPLFiltering:
    def test_push_day_keeps_chest_shoulders_triceps(self):
        exercises = [
            _ex("Bench Press", "chest"),
            _ex("Overhead Press", "shoulders"),
            _ex("Tricep Pushdown", "triceps"),
        ]
        result = _filter_exercises_for_session(exercises, "PPL", "Push Day")
        assert len(result) == 3

    def test_push_day_removes_back(self):
        exercises = [
            _ex("Bench Press", "chest"),
            _ex("Barbell Row", "back"),
        ]
        result = _filter_exercises_for_session(exercises, "PPL", "Push Day")
        assert len(result) == 1
        assert result[0]["name"] == "Bench Press"

    def test_pull_day_keeps_back_biceps_shoulders(self):
        exercises = [
            _ex("Lat Pulldown", "back"),
            _ex("Barbell Curl", "biceps"),
            _ex("Face Pull", "shoulders"),
        ]
        result = _filter_exercises_for_session(exercises, "PPL", "Pull Day")
        assert len(result) == 3

    def test_legs_day_removes_lateral_raise(self):
        """The exact scenario from the user's request."""
        exercises = [
            _ex("Squat", "quads"),
            _ex("Lateral Raise", "shoulders"),
            _ex("Romanian Deadlift", "hamstrings"),
        ]
        result = _filter_exercises_for_session(exercises, "PPL", "Legs Day")
        assert len(result) == 2
        names = [e["name"] for e in result]
        assert "Lateral Raise" not in names
        assert "Squat" in names
        assert "Romanian Deadlift" in names

    def test_legs_day_keeps_all_lower_body(self):
        exercises = [
            _ex("Squat", "quads"),
            _ex("RDL", "hamstrings"),
            _ex("Hip Thrust", "glutes"),
            _ex("Calf Raise", "calves"),
        ]
        result = _filter_exercises_for_session(exercises, "PPL", "Legs Day")
        assert len(result) == 4


# ── Core is always allowed ──────────────────────────────────────────────

class TestCoreAlwaysAllowed:
    @pytest.mark.parametrize("split,session", [
        ("PPL", "Push Day"),
        ("PPL", "Pull Day"),
        ("PPL", "Legs Day"),
        ("UpperLower", "Upper Body"),
        ("UpperLower", "Lower Body"),
        ("FullBody", "Full Body"),
        ("BroSplit", "Chest Day"),
        ("BroSplit", "Back Day"),
        ("BroSplit", "Shoulders Day"),
        ("BroSplit", "Arms Day"),
        ("BroSplit", "Legs Day"),
    ])
    def test_core_allowed_on_every_session(self, split, session):
        exercises = [_ex("Plank", "core")]
        result = _filter_exercises_for_session(exercises, split, session)
        assert len(result) == 1


# ── Full Body ────────────────────────────────────────────────────────────

class TestFullBodyFiltering:
    def test_keeps_everything(self):
        exercises = [
            _ex("Bench Press", "chest"),
            _ex("Squat", "quads"),
            _ex("Barbell Curl", "biceps"),
            _ex("Lateral Raise", "shoulders"),
        ]
        result = _filter_exercises_for_session(exercises, "FullBody", "Full Body")
        assert len(result) == 4


# ── Bro Split ────────────────────────────────────────────────────────────

class TestBroSplitFiltering:
    def test_arms_day_keeps_biceps_triceps(self):
        exercises = [
            _ex("Barbell Curl", "biceps"),
            _ex("Tricep Pushdown", "triceps"),
        ]
        result = _filter_exercises_for_session(exercises, "BroSplit", "Arms Day")
        assert len(result) == 2

    def test_arms_day_removes_chest(self):
        exercises = [
            _ex("Barbell Curl", "biceps"),
            _ex("Bench Press", "chest"),
        ]
        result = _filter_exercises_for_session(exercises, "BroSplit", "Arms Day")
        assert len(result) == 1
        assert result[0]["name"] == "Barbell Curl"

    def test_chest_day_removes_back(self):
        exercises = [
            _ex("Bench Press", "chest"),
            _ex("Barbell Row", "back"),
        ]
        result = _filter_exercises_for_session(exercises, "BroSplit", "Chest Day")
        assert len(result) == 1
        assert result[0]["name"] == "Bench Press"

    def test_shoulders_day_removes_quads(self):
        exercises = [
            _ex("Overhead Press", "shoulders"),
            _ex("Squat", "quads"),
        ]
        result = _filter_exercises_for_session(exercises, "BroSplit", "Shoulders Day")
        assert len(result) == 1
        assert result[0]["name"] == "Overhead Press"


# ── Upper / Lower ────────────────────────────────────────────────────────

class TestUpperLowerFiltering:
    def test_upper_keeps_all_upper_muscles(self):
        exercises = [
            _ex("Bench Press", "chest"),
            _ex("Lat Pulldown", "back"),
            _ex("OHP", "shoulders"),
            _ex("Barbell Curl", "biceps"),
            _ex("Pushdown", "triceps"),
        ]
        result = _filter_exercises_for_session(exercises, "UpperLower", "Upper Body")
        assert len(result) == 5

    def test_upper_removes_quads(self):
        exercises = [
            _ex("Bench Press", "chest"),
            _ex("Squat", "quads"),
        ]
        result = _filter_exercises_for_session(exercises, "UpperLower", "Upper Body")
        assert len(result) == 1
        assert result[0]["name"] == "Bench Press"

    def test_lower_removes_chest(self):
        exercises = [
            _ex("Squat", "quads"),
            _ex("Bench Press", "chest"),
        ]
        result = _filter_exercises_for_session(exercises, "UpperLower", "Lower Body")
        assert len(result) == 1
        assert result[0]["name"] == "Squat"


# ── Coverage: every SPLIT_SESSIONS entry has a SESSION_MUSCLE_GROUPS entry

class TestMappingCoverage:
    def test_all_sessions_have_muscle_group_mapping(self):
        for split, sessions in SPLIT_SESSIONS.items():
            for session in sessions:
                assert (split, session) in SESSION_MUSCLE_GROUPS, (
                    f"Missing SESSION_MUSCLE_GROUPS entry for ({split!r}, {session!r})"
                )

    def test_all_session_muscle_groups_are_valid(self):
        for key, groups in SESSION_MUSCLE_GROUPS.items():
            for g in groups:
                assert g in _ALL_MUSCLE_GROUPS, (
                    f"Invalid muscle group {g!r} in SESSION_MUSCLE_GROUPS[{key!r}]"
                )


# ── Edge cases ───────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_unknown_session_skips_filtering(self):
        exercises = [_ex("Bench Press", "chest"), _ex("Squat", "quads")]
        result = _filter_exercises_for_session(exercises, "PPL", "Unknown Session")
        assert len(result) == 2  # no filtering

    def test_empty_exercise_list(self):
        result = _filter_exercises_for_session([], "PPL", "Push Day")
        assert result == []
