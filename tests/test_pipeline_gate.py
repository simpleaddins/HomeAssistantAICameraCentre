"""Tests for the CameraPipeline motion-ignore processing gate."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from freezegun import freeze_time

from custom_components.ai_camera_centre import AlertStore
from custom_components.ai_camera_centre.analyzer import CameraPipeline
from custom_components.ai_camera_centre.const import (
    ARMED_ONLY_ARMED,
    ARMED_ONLY_DISARMED,
    CONF_ALARM_PANEL_ENTITY,
    CONF_CAMERA_ENTITY,
    CONF_CAMERA_MOTION_POLICY,
    CONF_PRESENCE_ENTITIES,
    CONF_PROCESS_ARMED,
    CONF_PROCESS_PRESENCE,
    CONF_PROCESS_RULES,
    CONF_PROCESS_TIME_END,
    CONF_PROCESS_TIME_MODE,
    CONF_PROCESS_TIME_START,
    CONF_SUN_ENTITY,
    POLICY_CUSTOM,
    PRESENCE_ONLY_AWAY,
    PRESENCE_ONLY_HOME,
    TIME_BETWEEN,
    TIME_DAY,
    TIME_NIGHT,
    TIME_NOT_BETWEEN,
)

ALARM = "alarm_control_panel.home"


def _pipeline(hass, tmp_path, global_options=None, camera_conf=None):
    store = AlertStore(hass, str(tmp_path / "acc"), 7)
    camera_conf = {CONF_CAMERA_ENTITY: "camera.side", **(camera_conf or {})}
    return CameraPipeline(
        hass, store, global_options or {}, "side_gate", camera_conf, targets=[]
    )


# -- presence gate -------------------------------------------------------


@pytest.mark.parametrize(
    ("person_state", "expected"),
    [("home", False), ("not_home", True)],
)
async def test_presence_only_away(hass, tmp_path, person_state, expected):
    hass.states.async_set("person.ben", person_state)
    p = _pipeline(hass, tmp_path, {CONF_PROCESS_PRESENCE: PRESENCE_ONLY_AWAY})
    assert p._should_process() is expected


async def test_presence_only_home(hass, tmp_path):
    hass.states.async_set("person.ben", "home")
    p = _pipeline(hass, tmp_path, {CONF_PROCESS_PRESENCE: PRESENCE_ONLY_HOME})
    assert p._should_process() is True
    hass.states.async_set("person.ben", "not_home")
    assert p._should_process() is False


async def test_presence_no_person_entities_treated_as_away(hass, tmp_path):
    p = _pipeline(hass, tmp_path, {CONF_PROCESS_PRESENCE: PRESENCE_ONLY_AWAY})
    assert p._should_process() is True


# -- alarm gate ----------------------------------------------------------


async def test_armed_only_armed(hass, tmp_path):
    opts = {CONF_PROCESS_ARMED: ARMED_ONLY_ARMED, CONF_ALARM_PANEL_ENTITY: ALARM}
    p = _pipeline(hass, tmp_path, opts)
    hass.states.async_set(ALARM, "armed_away")
    assert p._should_process() is True
    hass.states.async_set(ALARM, "disarmed")
    assert p._should_process() is False


async def test_armed_only_disarmed(hass, tmp_path):
    opts = {CONF_PROCESS_ARMED: ARMED_ONLY_DISARMED, CONF_ALARM_PANEL_ENTITY: ALARM}
    p = _pipeline(hass, tmp_path, opts)
    hass.states.async_set(ALARM, "disarmed")
    assert p._should_process() is True
    hass.states.async_set(ALARM, "armed_home")
    assert p._should_process() is False


async def test_armed_gate_fails_open_without_panel(hass, tmp_path):
    # only_armed but no alarm panel configured -> process anyway (fail open)
    p = _pipeline(hass, tmp_path, {CONF_PROCESS_ARMED: ARMED_ONLY_ARMED})
    assert p._should_process() is True


# -- time gate (sun-based) ----------------------------------------------


@pytest.mark.parametrize(
    ("mode", "sun", "expected"),
    [
        (TIME_DAY, "above_horizon", True),
        (TIME_DAY, "below_horizon", False),
        (TIME_NIGHT, "below_horizon", True),
        (TIME_NIGHT, "above_horizon", False),
    ],
)
async def test_time_day_night(hass, tmp_path, mode, sun, expected):
    hass.states.async_set("sun.sun", sun)
    p = _pipeline(
        hass, tmp_path, {CONF_PROCESS_TIME_MODE: mode, CONF_SUN_ENTITY: "sun.sun"}
    )
    assert p._should_process() is expected


async def test_time_gate_fails_open_when_sun_unknown(hass, tmp_path):
    hass.states.async_set("sun.sun", "unavailable")
    for mode in (TIME_DAY, TIME_NIGHT):
        p = _pipeline(hass, tmp_path, {CONF_PROCESS_TIME_MODE: mode})
        assert p._should_process() is True
    assert p._is_daytime() is None


# -- factors combine with AND -------------------------------------------


async def test_factors_combine_with_and(hass, tmp_path):
    hass.states.async_set("person.ben", "home")
    hass.states.async_set("sun.sun", "below_horizon")
    opts = {
        CONF_PROCESS_PRESENCE: PRESENCE_ONLY_AWAY,
        CONF_PROCESS_TIME_MODE: TIME_NIGHT,
    }
    p = _pipeline(hass, tmp_path, opts)
    # night passes but presence fails -> overall skip
    assert p._should_process() is False
    hass.states.async_set("person.ben", "not_home")
    assert p._should_process() is True


# -- per-camera custom policy overrides the house -----------------------


async def test_camera_custom_policy_overrides_house(hass, tmp_path):
    hass.states.async_set("person.ben", "home")
    global_opts = {CONF_PROCESS_PRESENCE: PRESENCE_ONLY_AWAY}
    camera_conf = {
        CONF_CAMERA_MOTION_POLICY: POLICY_CUSTOM,
        CONF_PROCESS_PRESENCE: PRESENCE_ONLY_HOME,
    }
    p = _pipeline(hass, tmp_path, global_opts, camera_conf)
    # house would skip (someone home), but camera custom = only_home -> process
    assert p._should_process() is True


# -- async_analyze honours the gate and the force bypass ----------------


async def test_async_analyze_skips_when_gate_blocks(hass, tmp_path):
    hass.states.async_set("person.ben", "home")
    p = _pipeline(hass, tmp_path, {CONF_PROCESS_PRESENCE: PRESENCE_ONLY_AWAY})
    p._run = AsyncMock()
    await p.async_analyze(force=False)
    p._run.assert_not_awaited()
    # a manual/forced run bypasses the gate
    await p.async_analyze(force=True)
    p._run.assert_awaited_once()


async def test_async_analyze_runs_when_gate_allows(hass, tmp_path):
    hass.states.async_set("person.ben", "not_home")
    p = _pipeline(hass, tmp_path, {CONF_PROCESS_PRESENCE: PRESENCE_ONLY_AWAY})
    p._run = AsyncMock()
    await p.async_analyze(force=False)
    p._run.assert_awaited_once()


# -- rule groups combine with OR (DNF) ----------------------------------


async def test_no_rules_processes_always(hass, tmp_path):
    # An explicit empty rule list means "no restriction".
    p = _pipeline(hass, tmp_path, {CONF_PROCESS_RULES: []})
    assert p._should_process() is True


async def test_two_rules_or_together(hass, tmp_path):
    # Rule A: only when away. Rule B: only at night. Process if EITHER holds.
    hass.states.async_set("sun.sun", "above_horizon")  # day
    rules = [
        {CONF_PROCESS_PRESENCE: PRESENCE_ONLY_AWAY},
        {CONF_PROCESS_TIME_MODE: TIME_NIGHT},
    ]
    p = _pipeline(hass, tmp_path, {CONF_PROCESS_RULES: rules})

    # daytime + someone home -> neither rule matches -> skip
    hass.states.async_set("person.ben", "home")
    assert p._should_process() is False
    # nobody home -> rule A matches -> process (even though still daytime)
    hass.states.async_set("person.ben", "not_home")
    assert p._should_process() is True
    # someone home but now night -> rule B matches -> process
    hass.states.async_set("person.ben", "home")
    hass.states.async_set("sun.sun", "below_horizon")
    assert p._should_process() is True


async def test_within_rule_conditions_and_together(hass, tmp_path):
    # Single rule: home AND night -> both must hold.
    rules = [
        {
            CONF_PROCESS_PRESENCE: PRESENCE_ONLY_HOME,
            CONF_PROCESS_TIME_MODE: TIME_NIGHT,
        }
    ]
    p = _pipeline(hass, tmp_path, {CONF_PROCESS_RULES: rules})
    hass.states.async_set("person.ben", "home")
    hass.states.async_set("sun.sun", "above_horizon")  # day -> time fails
    assert p._should_process() is False
    hass.states.async_set("sun.sun", "below_horizon")  # night -> both hold
    assert p._should_process() is True


# -- not_between time condition (negated window) -------------------------


@freeze_time("2026-08-16 08:30:00")
async def test_not_between_blocks_inside_window(hass, tmp_path):
    await hass.config.async_set_time_zone("UTC")
    rules = [
        {
            CONF_PROCESS_TIME_MODE: TIME_NOT_BETWEEN,
            CONF_PROCESS_TIME_START: "08:00:00",
            CONF_PROCESS_TIME_END: "09:00:00",
        }
    ]
    p = _pipeline(hass, tmp_path, {CONF_PROCESS_RULES: rules})
    # 08:30 is inside 08:00-09:00, so "not between" excludes it -> skip
    assert p._should_process() is False


@freeze_time("2026-08-16 10:30:00")
async def test_not_between_allows_outside_window(hass, tmp_path):
    await hass.config.async_set_time_zone("UTC")
    rules = [
        {
            CONF_PROCESS_TIME_MODE: TIME_NOT_BETWEEN,
            CONF_PROCESS_TIME_START: "08:00:00",
            CONF_PROCESS_TIME_END: "09:00:00",
        }
    ]
    p = _pipeline(hass, tmp_path, {CONF_PROCESS_RULES: rules})
    assert p._should_process() is True


@freeze_time("2026-08-16 08:30:00")
async def test_between_allows_inside_window(hass, tmp_path):
    await hass.config.async_set_time_zone("UTC")
    rules = [
        {
            CONF_PROCESS_TIME_MODE: TIME_BETWEEN,
            CONF_PROCESS_TIME_START: "08:00:00",
            CONF_PROCESS_TIME_END: "09:00:00",
        }
    ]
    p = _pipeline(hass, tmp_path, {CONF_PROCESS_RULES: rules})
    assert p._should_process() is True


async def test_not_between_without_window_fails_open(hass, tmp_path):
    # not_between with no window configured must not block forever.
    rules = [{CONF_PROCESS_TIME_MODE: TIME_NOT_BETWEEN}]
    p = _pipeline(hass, tmp_path, {CONF_PROCESS_RULES: rules})
    assert p._should_process() is True


# -- the user's worked example ------------------------------------------


@freeze_time("2026-08-16 08:30:00")
async def test_user_example_combined_dnf(hass, tmp_path):
    # "process when away OR at night, OR when home but not between 08:00-09:00"
    await hass.config.async_set_time_zone("UTC")
    rules = [
        {CONF_PROCESS_PRESENCE: PRESENCE_ONLY_AWAY},
        {CONF_PROCESS_TIME_MODE: TIME_NIGHT},
        {
            CONF_PROCESS_PRESENCE: PRESENCE_ONLY_HOME,
            CONF_PROCESS_TIME_MODE: TIME_NOT_BETWEEN,
            CONF_PROCESS_TIME_START: "08:00:00",
            CONF_PROCESS_TIME_END: "09:00:00",
        },
    ]
    p = _pipeline(hass, tmp_path, {CONF_PROCESS_RULES: rules})
    # home, daytime, and 08:30 (inside the excluded window) -> all rules fail
    hass.states.async_set("person.ben", "home")
    hass.states.async_set("sun.sun", "above_horizon")
    assert p._should_process() is False


@freeze_time("2026-08-16 10:30:00")
async def test_user_example_home_outside_quiet_hour(hass, tmp_path):
    await hass.config.async_set_time_zone("UTC")
    rules = [
        {CONF_PROCESS_PRESENCE: PRESENCE_ONLY_AWAY},
        {CONF_PROCESS_TIME_MODE: TIME_NIGHT},
        {
            CONF_PROCESS_PRESENCE: PRESENCE_ONLY_HOME,
            CONF_PROCESS_TIME_MODE: TIME_NOT_BETWEEN,
            CONF_PROCESS_TIME_START: "08:00:00",
            CONF_PROCESS_TIME_END: "09:00:00",
        },
    ]
    p = _pipeline(hass, tmp_path, {CONF_PROCESS_RULES: rules})
    # home, daytime, 10:30 (outside the excluded window) -> rule 3 matches
    hass.states.async_set("person.ben", "home")
    hass.states.async_set("sun.sun", "above_horizon")
    assert p._should_process() is True


# -- per-entity presence scoping ----------------------------------------


async def test_presence_entities_scopes_who_counts(hass, tmp_path):
    # Only ben counts; anna being home is irrelevant.
    hass.states.async_set("person.ben", "not_home")
    hass.states.async_set("person.anna", "home")
    opts = {
        CONF_PRESENCE_ENTITIES: ["person.ben"],
        CONF_PROCESS_RULES: [{CONF_PROCESS_PRESENCE: PRESENCE_ONLY_AWAY}],
    }
    p = _pipeline(hass, tmp_path, opts)
    # ben is away (anna ignored) -> only_away holds -> process
    assert p._should_process() is True
    hass.states.async_set("person.ben", "home")
    assert p._should_process() is False


async def test_presence_entities_supports_device_tracker(hass, tmp_path):
    hass.states.async_set("device_tracker.ben_phone", "home")
    opts = {
        CONF_PRESENCE_ENTITIES: ["device_tracker.ben_phone"],
        CONF_PROCESS_RULES: [{CONF_PROCESS_PRESENCE: PRESENCE_ONLY_HOME}],
    }
    p = _pipeline(hass, tmp_path, opts)
    assert p._should_process() is True
    hass.states.async_set("device_tracker.ben_phone", "not_home")
    assert p._should_process() is False


async def test_presence_entities_come_from_house_not_camera(hass, tmp_path):
    # A camera custom policy overrides the rules, but presence entities are
    # always house-wide (read from global options).
    hass.states.async_set("person.ben", "home")
    hass.states.async_set("person.anna", "not_home")
    global_opts = {CONF_PRESENCE_ENTITIES: ["person.anna"]}
    camera_conf = {
        CONF_CAMERA_MOTION_POLICY: POLICY_CUSTOM,
        CONF_PROCESS_RULES: [{CONF_PROCESS_PRESENCE: PRESENCE_ONLY_AWAY}],
    }
    p = _pipeline(hass, tmp_path, global_opts, camera_conf)
    # anna (the only tracked person) is away -> only_away holds -> process
    assert p._should_process() is True
