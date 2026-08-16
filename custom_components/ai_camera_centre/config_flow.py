"""Config flow for AI Camera Centre.

Initial setup collects the global settings. After that the integration
page offers native "Add camera" and "Add alert target" buttons (config
subentries), and the Configure button opens the global settings — no YAML
required and no nested options menu.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TimeSelector,
)
from homeassistant.util import slugify

from .const import (
    ARMED_ALWAYS,
    ARMED_ONLY_ARMED,
    ARMED_ONLY_DISARMED,
    CONF_AI_TASK_ENTITY,
    CONF_ALARM_PANEL_ENTITY,
    CONF_ALARMO_ENABLED,
    CONF_ALARMO_TRIGGER_SCORE,
    CONF_CAMERA_ENTITY,
    CONF_CAMERA_ID,
    CONF_CAMERA_MOTION_POLICY,
    CONF_CAMERA_NAME,
    CONF_COOLDOWN_SECONDS,
    CONF_DASHBOARD_PATH,
    CONF_LOG_ACTIVITY,
    CONF_LOG_WINDOW_END,
    CONF_LOG_WINDOW_START,
    CONF_MIN_LOG_SCORE,
    CONF_MOTION_ENTITIES,
    CONF_PRESENCE_ENTITIES,
    CONF_PROCESS_ARMED,
    CONF_PROCESS_PRESENCE,
    CONF_PROCESS_RULES,
    CONF_PROCESS_TIME_END,
    CONF_PROCESS_TIME_MODE,
    CONF_PROCESS_TIME_START,
    CONF_REPEAT_CONTEXT_MINUTES,
    CONF_RESPONSE_STYLE,
    CONF_RETENTION_DAYS,
    CONF_SCENE_CONTEXT,
    CONF_RULE_ENABLED,
    CONF_SNAPSHOT_COUNT,
    CONF_SNAPSHOT_INTERVAL_MS,
    CONF_SUN_ENTITY,
    CONF_TARGET_CAMERAS,
    CONF_TARGET_CONDITION,
    CONF_TARGET_MIN_SCORE,
    CONF_TARGET_NAME,
    CONF_TARGET_SERVICE,
    CONF_VISITOR_DESCRIPTION,
    CONF_VISITOR_ID,
    CONF_VISITOR_NAME,
    DEFAULT_ALARMO_TRIGGER_SCORE,
    DEFAULT_CAMERA_MOTION_POLICY,
    DEFAULT_COOLDOWN_SECONDS,
    DEFAULT_DASHBOARD_PATH,
    DEFAULT_LOG_ACTIVITY,
    DEFAULT_MIN_LOG_SCORE,
    DEFAULT_PROCESS_ARMED,
    DEFAULT_PROCESS_PRESENCE,
    DEFAULT_PROCESS_TIME_MODE,
    DEFAULT_REPEAT_CONTEXT_MINUTES,
    DEFAULT_RETENTION_DAYS,
    DEFAULT_SNAPSHOT_COUNT,
    DEFAULT_SNAPSHOT_INTERVAL_MS,
    DEFAULT_SUN_ENTITY,
    DEFAULT_TARGET_CONDITION,
    DOMAIN,
    MAX_PROCESS_RULES,
    NOTIFY_ALWAYS,
    NOTIFY_ARMED,
    NOTIFY_AWAY,
    NOTIFY_AWAY_OR_ARMED,
    POLICY_CUSTOM,
    POLICY_FOLLOW_HOUSE,
    PRESENCE_ALWAYS,
    PRESENCE_ONLY_AWAY,
    PRESENCE_ONLY_HOME,
    SUBENTRY_CAMERA,
    SUBENTRY_KNOWN_VISITOR,
    SUBENTRY_TARGET,
    TIME_ALWAYS,
    TIME_BETWEEN,
    TIME_DAY,
    TIME_NIGHT,
    TIME_NOT_BETWEEN,
)

MOTION_DOMAINS = ["binary_sensor", "input_boolean", "switch"]

# -- form sections -------------------------------------------------------
# The forms group their fields into collapsible UI sections. Sections nest
# their fields under the section key in the returned user_input; we flatten
# that back to the flat option/subentry keys the rest of the integration
# reads, so the storage shape is unchanged.
SECTION_CAPTURE = "capture"
SECTION_ALERTS = "alerts"
SECTION_ALARM = "alarm"
SECTION_PROCESSING = "processing"
SECTION_AI = "ai"

# One collapsible section per rule group (rule_1 .. rule_N). Kept separate
# from the flat sections above because every rule section reuses the SAME
# inner field keys, so they are collected into the CONF_PROCESS_RULES list
# rather than flattened (which would collide).
RULE_SECTIONS = tuple(f"rule_{i}" for i in range(1, MAX_PROCESS_RULES + 1))

# Flat sections whose fields flatten straight back to option/subentry keys.
SETTINGS_SECTIONS = (
    SECTION_CAPTURE,
    SECTION_ALERTS,
    SECTION_ALARM,
    SECTION_PROCESSING,
    SECTION_AI,
)
CAMERA_SECTIONS = (SECTION_PROCESSING,)


def _flatten_sections(
    user_input: dict[str, Any], section_keys: tuple[str, ...]
) -> dict[str, Any]:
    """Merge sectioned form output back into a flat dict.

    Idempotent: input that is already flat (no section keys present) is
    returned unchanged, so callers and tests can pass either shape.
    """
    flat = {k: v for k, v in user_input.items() if k not in section_keys}
    for key in section_keys:
        value = user_input.get(key)
        if isinstance(value, dict):
            flat.update(value)
    return flat

INT_SETTINGS = (
    CONF_RETENTION_DAYS,
    CONF_SNAPSHOT_COUNT,
    CONF_SNAPSHOT_INTERVAL_MS,
    CONF_COOLDOWN_SECONDS,
    CONF_ALARMO_TRIGGER_SCORE,
    CONF_MIN_LOG_SCORE,
    CONF_REPEAT_CONTEXT_MINUTES,
)

# Optional settings that must be cleared when the user empties them.
OPTIONAL_SETTINGS = (
    CONF_AI_TASK_ENTITY,
    CONF_ALARM_PANEL_ENTITY,
    CONF_LOG_WINDOW_START,
    CONF_LOG_WINDOW_END,
    CONF_SUN_ENTITY,
    CONF_RESPONSE_STYLE,
    CONF_PRESENCE_ENTITIES,
    CONF_PROCESS_TIME_START,
    CONF_PROCESS_TIME_END,
)

# person / device_tracker are the entity kinds that carry a "home" state.
PRESENCE_DOMAINS = ["person", "device_tracker"]

NOTIFY_CONDITIONS = [
    {"value": NOTIFY_ALWAYS, "label": "Always"},
    {"value": NOTIFY_AWAY, "label": "Only when nobody is home"},
    {"value": NOTIFY_ARMED, "label": "Only when the alarm is armed"},
    {"value": NOTIFY_AWAY_OR_ARMED, "label": "When away or armed"},
]

# -- motion-ignore processing gate option lists --------------------------

PRESENCE_OPTIONS = [
    {"value": PRESENCE_ALWAYS, "label": "Always process"},
    {"value": PRESENCE_ONLY_AWAY, "label": "Only when nobody is home"},
    {"value": PRESENCE_ONLY_HOME, "label": "Only when someone is home"},
]

ARMED_OPTIONS = [
    {"value": ARMED_ALWAYS, "label": "Always process"},
    {"value": ARMED_ONLY_ARMED, "label": "Only when the alarm is armed"},
    {"value": ARMED_ONLY_DISARMED, "label": "Only when the alarm is disarmed"},
]

TIME_OPTIONS = [
    {"value": TIME_ALWAYS, "label": "Any time"},
    {"value": TIME_BETWEEN, "label": "Between two times"},
    {"value": TIME_NOT_BETWEEN, "label": "Except between two times"},
    {"value": TIME_DAY, "label": "Daytime only (sun above horizon)"},
    {"value": TIME_NIGHT, "label": "Nighttime only (sun below horizon)"},
]

POLICY_OPTIONS = [
    {"value": POLICY_FOLLOW_HOUSE, "label": "Follow the house settings"},
    {"value": POLICY_CUSTOM, "label": "Custom for this camera"},
]


def _rule_fields(rule: dict[str, Any], *, enabled_default: bool) -> dict[Any, Any]:
    """The fields for one rule group: enable toggle + presence/alarm/time.

    All conditions in a rule are ANDed; the camera processes when ANY enabled
    rule matches. Shared by the house settings form and a camera's custom
    override so both read and write the same inner keys.
    """
    return {
        vol.Required(
            CONF_RULE_ENABLED,
            default=bool(rule.get(CONF_RULE_ENABLED, enabled_default)),
        ): BooleanSelector(),
        vol.Required(
            CONF_PROCESS_PRESENCE,
            default=rule.get(CONF_PROCESS_PRESENCE, DEFAULT_PROCESS_PRESENCE),
        ): SelectSelector(
            SelectSelectorConfig(
                options=PRESENCE_OPTIONS, mode=SelectSelectorMode.DROPDOWN
            )
        ),
        vol.Required(
            CONF_PROCESS_ARMED,
            default=rule.get(CONF_PROCESS_ARMED, DEFAULT_PROCESS_ARMED),
        ): SelectSelector(
            SelectSelectorConfig(
                options=ARMED_OPTIONS, mode=SelectSelectorMode.DROPDOWN
            )
        ),
        vol.Required(
            CONF_PROCESS_TIME_MODE,
            default=rule.get(CONF_PROCESS_TIME_MODE, DEFAULT_PROCESS_TIME_MODE),
        ): SelectSelector(
            SelectSelectorConfig(
                options=TIME_OPTIONS, mode=SelectSelectorMode.DROPDOWN
            )
        ),
        vol.Optional(
            CONF_PROCESS_TIME_START,
            description={"suggested_value": rule.get(CONF_PROCESS_TIME_START)},
        ): TimeSelector(),
        vol.Optional(
            CONF_PROCESS_TIME_END,
            description={"suggested_value": rule.get(CONF_PROCESS_TIME_END)},
        ): TimeSelector(),
    }


def _rules_for_form(src: dict[str, Any]) -> list[dict[str, Any]]:
    """Rules to prefill the rule sections, one entry per section slot.

    Reads the stored CONF_PROCESS_RULES list, or synthesises a single rule
    from legacy flat keys so pre-rule-group configs still populate the form.
    Padded to MAX_PROCESS_RULES so every section has a source dict.
    """
    raw = src.get(CONF_PROCESS_RULES)
    if isinstance(raw, list) and raw:
        rules = [dict(r) for r in raw[:MAX_PROCESS_RULES]]
    else:
        legacy = {
            CONF_PROCESS_PRESENCE: src.get(CONF_PROCESS_PRESENCE),
            CONF_PROCESS_ARMED: src.get(CONF_PROCESS_ARMED),
            CONF_PROCESS_TIME_MODE: src.get(CONF_PROCESS_TIME_MODE),
            CONF_PROCESS_TIME_START: src.get(CONF_PROCESS_TIME_START),
            CONF_PROCESS_TIME_END: src.get(CONF_PROCESS_TIME_END),
        }
        rules = [{k: v for k, v in legacy.items() if v is not None}]
    # Stored rules are all "enabled" (disabled ones aren't persisted).
    for rule in rules:
        rule.setdefault(CONF_RULE_ENABLED, True)
    rules += [{} for _ in range(MAX_PROCESS_RULES - len(rules))]
    return rules


def _rule_sections(src: dict[str, Any]) -> dict[Any, Any]:
    """The rule_1 .. rule_N collapsible sections, prefilled from ``src``."""
    rules = _rules_for_form(src)
    schema: dict[Any, Any] = {}
    for i, key in enumerate(RULE_SECTIONS):
        rule = rules[i]
        # First rule expanded and enabled by default; the rest collapsed/off,
        # so an unconfigured house simply "processes always" via rule 1.
        first = i == 0
        schema[vol.Required(key)] = section(
            vol.Schema(_rule_fields(rule, enabled_default=first)),
            {"collapsed": not (first or rule.get(CONF_RULE_ENABLED))},
        )
    return schema


def _collect_process_rules(user_input: dict[str, Any]) -> list[dict[str, Any]]:
    """Assemble CONF_PROCESS_RULES from the rule_1 .. rule_N sections.

    Only enabled rules are kept, and the ``enabled`` marker is dropped from the
    stored rule. Empty/blank time windows are omitted so they don't linger.
    """
    rules: list[dict[str, Any]] = []
    for key in RULE_SECTIONS:
        raw = user_input.get(key)
        if not isinstance(raw, dict) or not raw.get(CONF_RULE_ENABLED):
            continue
        rule = {
            CONF_PROCESS_PRESENCE: raw.get(
                CONF_PROCESS_PRESENCE, DEFAULT_PROCESS_PRESENCE
            ),
            CONF_PROCESS_ARMED: raw.get(
                CONF_PROCESS_ARMED, DEFAULT_PROCESS_ARMED
            ),
            CONF_PROCESS_TIME_MODE: raw.get(
                CONF_PROCESS_TIME_MODE, DEFAULT_PROCESS_TIME_MODE
            ),
        }
        for tkey in (CONF_PROCESS_TIME_START, CONF_PROCESS_TIME_END):
            if raw.get(tkey):
                rule[tkey] = raw[tkey]
        rules.append(rule)
    return rules


# Legacy flat gate keys retired once a config saves the rule-group form.
_LEGACY_GATE_KEYS = (
    CONF_PROCESS_PRESENCE,
    CONF_PROCESS_ARMED,
    CONF_PROCESS_TIME_MODE,
    CONF_PROCESS_TIME_START,
    CONF_PROCESS_TIME_END,
)


def _settings_options(
    user_input: dict[str, Any], base: dict[str, Any]
) -> dict[str, Any]:
    """Build the stored options dict from a submitted settings form.

    Merges the flat sections over ``base``, assembles the rule list from the
    rule_N sections, retires the legacy flat gate keys, and clears optional
    settings the user emptied. Shared by initial setup and the options flow.
    """
    rules = _collect_process_rules(user_input)
    settings = _flatten_sections(user_input, SETTINGS_SECTIONS)
    for key in RULE_SECTIONS:
        settings.pop(key, None)
    options = dict(base)
    options.update(_clean_settings(settings))
    options[CONF_PROCESS_RULES] = rules
    for key in _LEGACY_GATE_KEYS:
        options.pop(key, None)
    for key in OPTIONAL_SETTINGS:
        if key not in settings:
            options.pop(key, None)
    return options


# -- schema builders -----------------------------------------------------


def _settings_schema(options: dict[str, Any]) -> vol.Schema:
    """Global settings form, grouped into collapsible sections.

    Prefilled from current options. Fields are grouped by purpose; on submit
    the sectioned output is flattened back to the flat option keys via
    ``_flatten_sections``.
    """

    def _get(key: str, default: Any) -> Any:
        return options.get(key, default)

    capture = {
        vol.Required(
            CONF_SNAPSHOT_COUNT,
            default=_get(CONF_SNAPSHOT_COUNT, DEFAULT_SNAPSHOT_COUNT),
        ): NumberSelector(
            NumberSelectorConfig(min=2, max=10, mode=NumberSelectorMode.BOX)
        ),
        vol.Required(
            CONF_SNAPSHOT_INTERVAL_MS,
            default=_get(CONF_SNAPSHOT_INTERVAL_MS, DEFAULT_SNAPSHOT_INTERVAL_MS),
        ): NumberSelector(
            NumberSelectorConfig(
                min=100, max=5000, step=100, mode=NumberSelectorMode.BOX
            )
        ),
        vol.Required(
            CONF_COOLDOWN_SECONDS,
            default=_get(CONF_COOLDOWN_SECONDS, DEFAULT_COOLDOWN_SECONDS),
        ): NumberSelector(
            NumberSelectorConfig(min=0, max=3600, mode=NumberSelectorMode.BOX)
        ),
        vol.Optional(
            CONF_AI_TASK_ENTITY,
            description={"suggested_value": _get(CONF_AI_TASK_ENTITY, None)},
        ): EntitySelector(EntitySelectorConfig(domain="ai_task")),
    }

    alerts = {
        vol.Required(
            CONF_MIN_LOG_SCORE,
            default=_get(CONF_MIN_LOG_SCORE, DEFAULT_MIN_LOG_SCORE),
        ): NumberSelector(
            NumberSelectorConfig(min=1, max=10, mode=NumberSelectorMode.SLIDER)
        ),
        vol.Required(
            CONF_RETENTION_DAYS,
            default=_get(CONF_RETENTION_DAYS, DEFAULT_RETENTION_DAYS),
        ): NumberSelector(
            NumberSelectorConfig(min=1, max=90, mode=NumberSelectorMode.BOX)
        ),
        vol.Required(
            CONF_REPEAT_CONTEXT_MINUTES,
            default=_get(
                CONF_REPEAT_CONTEXT_MINUTES, DEFAULT_REPEAT_CONTEXT_MINUTES
            ),
        ): NumberSelector(
            NumberSelectorConfig(min=0, max=120, mode=NumberSelectorMode.BOX)
        ),
        vol.Optional(
            CONF_LOG_WINDOW_START,
            description={"suggested_value": _get(CONF_LOG_WINDOW_START, None)},
        ): TimeSelector(),
        vol.Optional(
            CONF_LOG_WINDOW_END,
            description={"suggested_value": _get(CONF_LOG_WINDOW_END, None)},
        ): TimeSelector(),
        vol.Required(
            CONF_DASHBOARD_PATH,
            default=_get(CONF_DASHBOARD_PATH, DEFAULT_DASHBOARD_PATH),
        ): TextSelector(),
        vol.Required(
            CONF_LOG_ACTIVITY,
            default=_get(CONF_LOG_ACTIVITY, DEFAULT_LOG_ACTIVITY),
        ): BooleanSelector(),
    }

    alarm = {
        vol.Optional(
            CONF_ALARM_PANEL_ENTITY,
            description={"suggested_value": _get(CONF_ALARM_PANEL_ENTITY, None)},
        ): EntitySelector(EntitySelectorConfig(domain="alarm_control_panel")),
        vol.Required(
            CONF_ALARMO_ENABLED,
            default=_get(CONF_ALARMO_ENABLED, False),
        ): BooleanSelector(),
        vol.Required(
            CONF_ALARMO_TRIGGER_SCORE,
            default=_get(CONF_ALARMO_TRIGGER_SCORE, DEFAULT_ALARMO_TRIGGER_SCORE),
        ): NumberSelector(
            NumberSelectorConfig(min=1, max=10, mode=NumberSelectorMode.SLIDER)
        ),
    }

    processing = {
        # -- motion-ignore processing gate: shared inputs ----------------
        # The rules themselves live in the rule_1..N sections below; these
        # two feed every rule (who counts as "home", and the day/night sun).
        vol.Optional(
            CONF_PRESENCE_ENTITIES,
            description={"suggested_value": _get(CONF_PRESENCE_ENTITIES, [])},
        ): EntitySelector(
            EntitySelectorConfig(domain=PRESENCE_DOMAINS, multiple=True)
        ),
        vol.Optional(
            CONF_SUN_ENTITY,
            description={
                "suggested_value": _get(CONF_SUN_ENTITY, DEFAULT_SUN_ENTITY)
            },
        ): EntitySelector(EntitySelectorConfig(domain="sun")),
    }

    ai = {
        vol.Optional(
            CONF_RESPONSE_STYLE,
            description={"suggested_value": _get(CONF_RESPONSE_STYLE, None)},
        ): TextSelector(TextSelectorConfig(multiline=True)),
    }

    return vol.Schema(
        {
            vol.Required(SECTION_CAPTURE): section(
                vol.Schema(capture), {"collapsed": False}
            ),
            vol.Required(SECTION_ALERTS): section(
                vol.Schema(alerts), {"collapsed": False}
            ),
            vol.Required(SECTION_ALARM): section(
                vol.Schema(alarm), {"collapsed": True}
            ),
            vol.Required(SECTION_PROCESSING): section(
                vol.Schema(processing), {"collapsed": True}
            ),
            **_rule_sections(options),
            vol.Required(SECTION_AI): section(
                vol.Schema(ai), {"collapsed": True}
            ),
        }
    )


def _camera_schema(camera: dict[str, Any] | None = None) -> vol.Schema:
    """Add/edit camera form, prefilled when editing.

    The essentials (name, stream, motion triggers, scene context) sit at the
    top; the motion-processing policy and its custom gate live in a collapsed
    section, since most cameras just follow the house default.
    """
    camera = camera or {}
    motion_entities = camera.get(CONF_MOTION_ENTITIES) or []
    processing = {
        # Processing policy: follow the house rules, or override with the
        # camera's own rule groups below. The rules only apply when "Custom
        # for this camera" is selected.
        vol.Required(
            CONF_CAMERA_MOTION_POLICY,
            default=camera.get(
                CONF_CAMERA_MOTION_POLICY, DEFAULT_CAMERA_MOTION_POLICY
            ),
        ): SelectSelector(
            SelectSelectorConfig(
                options=POLICY_OPTIONS, mode=SelectSelectorMode.DROPDOWN
            )
        ),
    }
    return vol.Schema(
        {
            vol.Required(
                CONF_CAMERA_NAME,
                default=camera.get(CONF_CAMERA_NAME, ""),
            ): TextSelector(),
            vol.Required(
                CONF_CAMERA_ENTITY,
                description={"suggested_value": camera.get(CONF_CAMERA_ENTITY)},
            ): EntitySelector(EntitySelectorConfig(domain="camera")),
            vol.Optional(
                CONF_MOTION_ENTITIES,
                description={"suggested_value": motion_entities},
            ): EntitySelector(
                EntitySelectorConfig(domain=MOTION_DOMAINS, multiple=True)
            ),
            vol.Optional(
                CONF_SCENE_CONTEXT,
                description={"suggested_value": camera.get(CONF_SCENE_CONTEXT, "")},
            ): TextSelector(TextSelectorConfig(multiline=True)),
            vol.Required(SECTION_PROCESSING): section(
                vol.Schema(processing), {"collapsed": True}
            ),
            # Custom rule groups (used only when the policy is "Custom").
            # Sections can't nest, so these sit at the form's top level.
            **_rule_sections(camera),
        }
    )


def _notify_service_selector(hass: HomeAssistant) -> SelectSelector:
    """Dropdown of the notify services registered right now."""
    services = sorted(
        f"notify.{name}" for name in hass.services.async_services().get("notify", {})
    )
    return SelectSelector(
        SelectSelectorConfig(
            options=services,
            custom_value=True,
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


def _friendly_service_name(service: str) -> str:
    """Turn notify.mobile_app_ben_s_note15_pro into 'Ben S Note15 Pro'."""
    name = service.removeprefix("notify.").removeprefix("mobile_app_")
    return name.replace("_", " ").strip().title() or service


def _target_title(target: dict[str, Any]) -> str:
    return target.get(CONF_TARGET_NAME) or _friendly_service_name(
        target.get(CONF_TARGET_SERVICE, "")
    )


def _target_schema(
    hass: HomeAssistant,
    cameras: dict[str, Any],
    target: dict[str, Any] | None = None,
) -> vol.Schema:
    """Add/edit alert target form, prefilled when editing."""
    target = target or {}
    return vol.Schema(
        {
            vol.Optional(
                CONF_TARGET_NAME,
                description={"suggested_value": target.get(CONF_TARGET_NAME)},
            ): TextSelector(),
            vol.Required(
                CONF_TARGET_SERVICE,
                description={"suggested_value": target.get(CONF_TARGET_SERVICE)},
            ): _notify_service_selector(hass),
            vol.Required(
                CONF_TARGET_MIN_SCORE,
                default=target.get(CONF_TARGET_MIN_SCORE, 1),
            ): NumberSelector(
                NumberSelectorConfig(min=1, max=10, mode=NumberSelectorMode.SLIDER)
            ),
            vol.Required(
                CONF_TARGET_CONDITION,
                default=target.get(CONF_TARGET_CONDITION, DEFAULT_TARGET_CONDITION),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=NOTIFY_CONDITIONS,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_TARGET_CAMERAS,
                description={"suggested_value": target.get(CONF_TARGET_CAMERAS, [])},
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        {
                            "value": camera_id,
                            "label": conf.get(CONF_CAMERA_NAME) or camera_id,
                        }
                        for camera_id, conf in cameras.items()
                    ],
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                )
            ),
        }
    )


# -- cleaners ------------------------------------------------------------


def _clean_settings(user_input: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(user_input)
    for key in INT_SETTINGS:
        if key in cleaned:
            cleaned[key] = int(cleaned[key])
    # Drop a blanked free-text style so OPTIONAL_SETTINGS can clear it.
    if not str(cleaned.get(CONF_RESPONSE_STYLE, "")).strip():
        cleaned.pop(CONF_RESPONSE_STYLE, None)
    else:
        cleaned[CONF_RESPONSE_STYLE] = cleaned[CONF_RESPONSE_STYLE].strip()
    return cleaned


def _clean_camera(user_input: dict[str, Any], camera_id: str) -> dict[str, Any]:
    # Rule sections are collected from the raw (pre-flatten) input, so pull
    # them before the processing section is flattened over the top.
    rules = _collect_process_rules(user_input)
    flat = _flatten_sections(user_input, CAMERA_SECTIONS)
    data: dict[str, Any] = {
        CONF_CAMERA_ID: camera_id,
        CONF_CAMERA_NAME: flat[CONF_CAMERA_NAME],
        CONF_CAMERA_ENTITY: flat[CONF_CAMERA_ENTITY],
        CONF_MOTION_ENTITIES: flat.get(CONF_MOTION_ENTITIES, []),
        CONF_CAMERA_MOTION_POLICY: flat.get(
            CONF_CAMERA_MOTION_POLICY, DEFAULT_CAMERA_MOTION_POLICY
        ),
        CONF_PROCESS_RULES: rules,
    }
    if scene := flat.get(CONF_SCENE_CONTEXT):
        data[CONF_SCENE_CONTEXT] = scene
    return data


def _clean_target(user_input: dict[str, Any]) -> dict[str, Any]:
    return {
        CONF_TARGET_NAME: (user_input.get(CONF_TARGET_NAME) or "").strip(),
        CONF_TARGET_SERVICE: str(user_input[CONF_TARGET_SERVICE]).strip(),
        CONF_TARGET_MIN_SCORE: int(user_input[CONF_TARGET_MIN_SCORE]),
        CONF_TARGET_CONDITION: user_input.get(
            CONF_TARGET_CONDITION, DEFAULT_TARGET_CONDITION
        ),
        CONF_TARGET_CAMERAS: user_input.get(CONF_TARGET_CAMERAS, []),
    }


def _visitor_schema(visitor: dict[str, Any] | None = None) -> vol.Schema:
    """Add/edit known-visitor form, prefilled when editing."""
    visitor = visitor or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_VISITOR_NAME,
                default=visitor.get(CONF_VISITOR_NAME, ""),
            ): TextSelector(),
            vol.Required(
                CONF_VISITOR_DESCRIPTION,
                description={
                    "suggested_value": visitor.get(CONF_VISITOR_DESCRIPTION, "")
                },
            ): TextSelector(TextSelectorConfig(multiline=True)),
        }
    )


def _clean_visitor(user_input: dict[str, Any], visitor_id: str) -> dict[str, Any]:
    return {
        CONF_VISITOR_ID: visitor_id,
        CONF_VISITOR_NAME: user_input[CONF_VISITOR_NAME].strip(),
        CONF_VISITOR_DESCRIPTION: user_input[CONF_VISITOR_DESCRIPTION].strip(),
    }


# -- flows ---------------------------------------------------------------


class AICameraCentreConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup and expose the camera/target subentries."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            return self.async_create_entry(
                title="AI Camera Centre",
                data={},
                options=_settings_options(user_input, {}),
            )
        return self.async_show_form(
            step_id="user", data_schema=_settings_schema({})
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return AICameraCentreOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        return {
            SUBENTRY_CAMERA: CameraSubentryFlow,
            SUBENTRY_TARGET: AlertTargetSubentryFlow,
            SUBENTRY_KNOWN_VISITOR: KnownVisitorSubentryFlow,
        }


class AICameraCentreOptionsFlow(OptionsFlow):
    """Global settings only — cameras and targets are subentries now."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            options = _settings_options(
                user_input, dict(self.config_entry.options)
            )
            return self.async_create_entry(data=options)
        return self.async_show_form(
            step_id="init",
            data_schema=_settings_schema(dict(self.config_entry.options)),
        )


class CameraSubentryFlow(ConfigSubentryFlow):
    """Add or edit a camera."""

    def _camera_ids(self) -> set[str]:
        return {
            sub.data.get(CONF_CAMERA_ID)
            for sub in self._get_entry().subentries.values()
            if sub.subentry_type == SUBENTRY_CAMERA
        }

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input = _flatten_sections(user_input, CAMERA_SECTIONS)
            camera_id = slugify(user_input[CONF_CAMERA_NAME])
            if not camera_id:
                errors[CONF_CAMERA_NAME] = "invalid_name"
            elif camera_id in self._camera_ids():
                errors[CONF_CAMERA_NAME] = "duplicate_camera"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_CAMERA_NAME],
                    data=_clean_camera(user_input, camera_id),
                    unique_id=camera_id,
                )
        return self.async_show_form(
            step_id="user", data_schema=_camera_schema(), errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        if user_input is not None:
            user_input = _flatten_sections(user_input, CAMERA_SECTIONS)
            # Keep the original camera_id (and its alert history) on rename.
            camera_id = subentry.data.get(CONF_CAMERA_ID) or subentry.subentry_id
            return self.async_update_and_abort(
                self._get_entry(),
                subentry,
                title=user_input[CONF_CAMERA_NAME],
                data=_clean_camera(user_input, camera_id),
            )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_camera_schema(dict(subentry.data)),
        )


class AlertTargetSubentryFlow(ConfigSubentryFlow):
    """Add or edit an alert target."""

    def _cameras(self) -> dict[str, Any]:
        return {
            sub.data.get(CONF_CAMERA_ID): sub.data
            for sub in self._get_entry().subentries.values()
            if sub.subentry_type == SUBENTRY_CAMERA
        }

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            target = _clean_target(user_input)
            if not target[CONF_TARGET_SERVICE]:
                errors[CONF_TARGET_SERVICE] = "invalid_service"
            else:
                return self.async_create_entry(
                    title=_target_title(target), data=target
                )
        return self.async_show_form(
            step_id="user",
            data_schema=_target_schema(self.hass, self._cameras()),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        if user_input is not None:
            target = _clean_target(user_input)
            return self.async_update_and_abort(
                self._get_entry(),
                subentry,
                title=_target_title(target),
                data=target,
            )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_target_schema(
                self.hass, self._cameras(), dict(subentry.data)
            ),
        )


class KnownVisitorSubentryFlow(ConfigSubentryFlow):
    """Add or edit a known visitor (household member / regular)."""

    def _visitor_ids(self) -> set[str]:
        return {
            sub.data.get(CONF_VISITOR_ID)
            for sub in self._get_entry().subentries.values()
            if sub.subentry_type == SUBENTRY_KNOWN_VISITOR
        }

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            visitor_id = slugify(user_input.get(CONF_VISITOR_NAME, ""))
            if not visitor_id:
                errors[CONF_VISITOR_NAME] = "invalid_name"
            elif visitor_id in self._visitor_ids():
                errors[CONF_VISITOR_NAME] = "duplicate_visitor"
            else:
                visitor = _clean_visitor(user_input, visitor_id)
                return self.async_create_entry(
                    title=visitor[CONF_VISITOR_NAME],
                    data=visitor,
                    unique_id=visitor_id,
                )
        return self.async_show_form(
            step_id="user", data_schema=_visitor_schema(), errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        if user_input is not None:
            # Keep the original visitor_id (and its uploaded photos) on rename.
            visitor_id = (
                subentry.data.get(CONF_VISITOR_ID)
                or slugify(subentry.data.get(CONF_VISITOR_NAME, ""))
                or subentry.subentry_id
            )
            visitor = _clean_visitor(user_input, visitor_id)
            return self.async_update_and_abort(
                self._get_entry(),
                subentry,
                title=visitor[CONF_VISITOR_NAME],
                data=visitor,
            )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_visitor_schema(dict(subentry.data)),
        )
