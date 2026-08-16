"""Pure-logic unit tests (no running Home Assistant instance required)."""
from __future__ import annotations

import pytest

from custom_components.ai_camera_centre import config_flow
from custom_components.ai_camera_centre.analyzer import (
    CameraPipeline,
    _parse_ai_result,
)
from custom_components.ai_camera_centre.const import (
    ARMED_ONLY_ARMED,
    CONF_CAMERA_ENTITY,
    CONF_CAMERA_ID,
    CONF_CAMERA_MOTION_POLICY,
    CONF_CAMERA_NAME,
    CONF_PROCESS_ARMED,
    CONF_PROCESS_PRESENCE,
    CONF_PROCESS_RULES,
    CONF_PROCESS_TIME_MODE,
    CONF_RESPONSE_STYLE,
    CONF_RULE_ENABLED,
    CONF_VISITOR_DESCRIPTION,
    CONF_VISITOR_ID,
    CONF_VISITOR_NAME,
    POLICY_CUSTOM,
    POLICY_FOLLOW_HOUSE,
    PRESENCE_ONLY_AWAY,
    PRESENCE_ONLY_HOME,
    TIME_NIGHT,
)


# -- config_flow cleaners ------------------------------------------------


def test_clean_settings_coerces_ints_and_trims_style():
    out = config_flow._clean_settings(
        {
            "retention_days": "7",
            "snapshot_count": "5",
            CONF_RESPONSE_STYLE: "  like a pirate  ",
        }
    )
    assert out["retention_days"] == 7 and isinstance(out["retention_days"], int)
    assert out[CONF_RESPONSE_STYLE] == "like a pirate"


def test_clean_settings_drops_blank_style():
    out = config_flow._clean_settings({"retention_days": 7, CONF_RESPONSE_STYLE: "   "})
    assert CONF_RESPONSE_STYLE not in out


def test_clean_camera_persists_policy_and_rules():
    data = config_flow._clean_camera(
        {
            CONF_CAMERA_NAME: "Side Gate",
            CONF_CAMERA_ENTITY: "camera.side",
            CONF_CAMERA_MOTION_POLICY: POLICY_CUSTOM,
            "rule_1": {
                CONF_RULE_ENABLED: True,
                CONF_PROCESS_PRESENCE: PRESENCE_ONLY_AWAY,
                CONF_PROCESS_ARMED: ARMED_ONLY_ARMED,
                CONF_PROCESS_TIME_MODE: TIME_NIGHT,
            },
            "rule_2": {CONF_RULE_ENABLED: False},
            "rule_3": {CONF_RULE_ENABLED: False},
        },
        "side_gate",
    )
    assert data[CONF_CAMERA_ID] == "side_gate"
    assert data[CONF_CAMERA_MOTION_POLICY] == POLICY_CUSTOM
    # Only the one enabled rule is persisted, without the enabled marker.
    assert data[CONF_PROCESS_RULES] == [
        {
            CONF_PROCESS_PRESENCE: PRESENCE_ONLY_AWAY,
            CONF_PROCESS_ARMED: ARMED_ONLY_ARMED,
            CONF_PROCESS_TIME_MODE: TIME_NIGHT,
        }
    ]


def test_clean_camera_defaults_when_missing():
    data = config_flow._clean_camera(
        {CONF_CAMERA_NAME: "Front", CONF_CAMERA_ENTITY: "camera.front"}, "front"
    )
    assert data[CONF_CAMERA_MOTION_POLICY] == POLICY_FOLLOW_HOUSE
    # No rule sections submitted -> no rules stored (fail open: process always).
    assert data[CONF_PROCESS_RULES] == []


def test_clean_visitor_assigns_id_and_trims():
    data = config_flow._clean_visitor(
        {CONF_VISITOR_NAME: "  Ben  ", CONF_VISITOR_DESCRIPTION: "  tall  "},
        "ben",
    )
    assert data == {
        CONF_VISITOR_ID: "ben",
        CONF_VISITOR_NAME: "Ben",
        CONF_VISITOR_DESCRIPTION: "tall",
    }


# -- processing-policy resolution ---------------------------------------


def test_resolve_policy_follows_house_by_default():
    # Legacy flat keys are read as a single rule; the camera's are ignored.
    global_opts = {CONF_PROCESS_PRESENCE: PRESENCE_ONLY_AWAY}
    camera = {CONF_PROCESS_PRESENCE: PRESENCE_ONLY_HOME}  # ignored (follow_house)
    policy = CameraPipeline._resolve_process_policy(global_opts, camera)
    assert policy["rules"][0][CONF_PROCESS_PRESENCE] == PRESENCE_ONLY_AWAY


def test_resolve_policy_uses_camera_when_custom():
    global_opts = {CONF_PROCESS_PRESENCE: PRESENCE_ONLY_AWAY}
    camera = {
        CONF_CAMERA_MOTION_POLICY: POLICY_CUSTOM,
        CONF_PROCESS_RULES: [{CONF_PROCESS_PRESENCE: PRESENCE_ONLY_HOME}],
    }
    policy = CameraPipeline._resolve_process_policy(global_opts, camera)
    assert policy["rules"][0][CONF_PROCESS_PRESENCE] == PRESENCE_ONLY_HOME


# -- time-window helper --------------------------------------------------


def test_time_in_window_no_window_is_true():
    assert CameraPipeline._time_in_window(None, None) is True
    assert CameraPipeline._time_in_window("08:00", None) is True


@pytest.mark.parametrize(
    ("start", "end", "now", "expected"),
    [
        ("08:00", "18:00", "12:00", True),
        ("08:00", "18:00", "20:00", False),
        ("22:00", "06:00", "23:30", True),  # wraps midnight
        ("22:00", "06:00", "05:00", True),
        ("22:00", "06:00", "12:00", False),
    ],
)
def test_time_in_window_ranges(monkeypatch, start, end, now, expected):
    import datetime

    from custom_components.ai_camera_centre import analyzer

    class _FakeNow:
        @staticmethod
        def time():
            h, m = (int(x) for x in now.split(":"))
            return datetime.time(h, m)

    monkeypatch.setattr(analyzer.dt_util, "now", lambda: _FakeNow())
    assert CameraPipeline._time_in_window(start, end) is expected


# -- AI result parsing ---------------------------------------------------


def test_parse_ai_result_clamps_and_defaults():
    out = _parse_ai_result({"suspicious_index": 42, "short": "hi"})
    assert out["score"] == 10
    assert out["short"] == "hi"
    assert out["known_person"] == "none"


def test_parse_ai_result_strips_json_fence():
    raw = '```json\n{"suspicious_index": 3, "known_person": "Ben"}\n```'
    out = _parse_ai_result(raw)
    assert out["score"] == 3
    assert out["known_person"] == "Ben"
