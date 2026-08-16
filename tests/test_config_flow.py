"""Tests for the config and options flows."""
from __future__ import annotations

from unittest.mock import patch

from homeassistant import config_entries, data_entry_flow
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

# Finishing a flow triggers entry setup, which processes our manifest
# dependencies (ai_task -> conversation -> hassil). Mark those present so the
# heavy tree isn't required, and patch async_setup_entry so the flow tests
# stay focused on flow logic rather than full integration setup.
STUB_COMPONENTS = ("camera", "ai_task", "conversation", "media_source")
SETUP_ENTRY = "custom_components.ai_camera_centre.async_setup_entry"


def _stub_deps(hass: HomeAssistant) -> None:
    for comp in STUB_COMPONENTS:
        hass.config.components.add(comp)

from custom_components.ai_camera_centre.const import (
    CONF_PROCESS_ARMED,
    CONF_PROCESS_PRESENCE,
    CONF_PROCESS_RULES,
    CONF_PROCESS_TIME_MODE,
    CONF_RESPONSE_STYLE,
    CONF_RETENTION_DAYS,
    DEFAULT_PROCESS_PRESENCE,
    DOMAIN,
    PRESENCE_ONLY_AWAY,
    TIME_NIGHT,
)

# The form groups fields into UI sections, so a submission is nested by
# section key. Flat sections flatten back to option keys; the rule_N sections
# are assembled into the process_rules list on submit.
FORM_INPUT = {
    "capture": {
        "snapshot_count": 5,
        "snapshot_interval_ms": 500,
        "cooldown_seconds": 30,
    },
    "alerts": {
        "min_log_score": 1,
        "retention_days": 7,
        "repeat_context_minutes": 15,
        "dashboard_path": "/lovelace/alerts",
    },
    "alarm": {
        "alarmo_enabled": False,
        "alarmo_trigger_score": 9,
    },
    "processing": {},
    "rule_1": {
        "enabled": True,
        "process_presence": PRESENCE_ONLY_AWAY,
        "process_armed": "always",
        "process_time_mode": "always",
    },
    "rule_2": {
        "enabled": True,
        "process_presence": "always",
        "process_armed": "always",
        "process_time_mode": TIME_NIGHT,
    },
    "rule_3": {
        "enabled": False,
        "process_presence": "always",
        "process_armed": "always",
        "process_time_mode": "always",
    },
    "ai": {},
}

# What those settings look like once flattened and stored in entry.options.
STORED_OPTIONS = {
    "retention_days": 7,
    "snapshot_count": 5,
    "snapshot_interval_ms": 500,
    "cooldown_seconds": 30,
    "dashboard_path": "/lovelace/alerts",
    "min_log_score": 1,
    "repeat_context_minutes": 15,
    "alarmo_enabled": False,
    "alarmo_trigger_score": 9,
    CONF_PROCESS_RULES: [
        {
            CONF_PROCESS_PRESENCE: DEFAULT_PROCESS_PRESENCE,
            CONF_PROCESS_ARMED: "always",
            CONF_PROCESS_TIME_MODE: "always",
        }
    ],
}


async def test_user_flow_creates_entry(hass: HomeAssistant):
    _stub_deps(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM

    with patch(SETUP_ENTRY, return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {**FORM_INPUT, "ai": {CONF_RESPONSE_STYLE: "like a noir detective"}},
        )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    opts = result["options"]
    assert opts[CONF_RETENTION_DAYS] == 7
    # Two enabled rules become an OR of AND-groups; the disabled rule_3 is
    # dropped, and the legacy flat gate keys are not written.
    assert opts[CONF_PROCESS_RULES] == [
        {
            CONF_PROCESS_PRESENCE: PRESENCE_ONLY_AWAY,
            CONF_PROCESS_ARMED: "always",
            CONF_PROCESS_TIME_MODE: "always",
        },
        {
            CONF_PROCESS_PRESENCE: "always",
            CONF_PROCESS_ARMED: "always",
            CONF_PROCESS_TIME_MODE: TIME_NIGHT,
        },
    ]
    assert CONF_PROCESS_PRESENCE not in opts
    assert opts[CONF_RESPONSE_STYLE] == "like a noir detective"


async def test_single_instance_only(hass: HomeAssistant):
    MockConfigEntry(domain=DOMAIN, data={}, options=STORED_OPTIONS).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_options_flow_clears_blanked_style(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={**STORED_OPTIONS, CONF_RESPONSE_STYLE: "old style"},
    )
    entry.add_to_hass(hass)
    _stub_deps(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == data_entry_flow.FlowResultType.FORM

    # resubmit without a style -> it should be cleared from options
    with patch(SETUP_ENTRY, return_value=True):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], FORM_INPUT
        )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert CONF_RESPONSE_STYLE not in result["data"]
