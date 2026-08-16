"""Camera analysis pipeline for AI Camera Centre.

One CameraPipeline per configured camera. On a motion trigger (or the
ai_camera_centre.analyze service) it captures a burst of snapshots,
sends them to an AI Task entity for analysis, archives the alert and
fires the configured mobile notifications. This is the built-in
replacement for the shared YAML script earlier versions required.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import secrets as py_secrets
import time
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components import camera
from homeassistant.components.http.auth import async_sign_path
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from .const import (
    ARMED_ONLY_ARMED,
    ARMED_ONLY_DISARMED,
    ARMED_STATES,
    CONF_AI_TASK_ENTITY,
    CONF_ALARM_PANEL_ENTITY,
    CONF_ALARMO_ENABLED,
    CONF_ALARMO_TRIGGER_SCORE,
    CONF_CAMERA_ENTITY,
    CONF_CAMERA_MOTION_POLICY,
    CONF_CAMERA_NAME,
    CONF_COOLDOWN_SECONDS,
    CONF_DASHBOARD_PATH,
    CONF_LOG_ACTIVITY,
    CONF_LOG_WINDOW_END,
    CONF_LOG_WINDOW_START,
    CONF_MIN_LOG_SCORE,
    CONF_PRESENCE_ENTITIES,
    CONF_PROCESS_ARMED,
    CONF_PROCESS_PRESENCE,
    CONF_PROCESS_RULES,
    CONF_PROCESS_TIME_END,
    CONF_PROCESS_TIME_MODE,
    CONF_PROCESS_TIME_START,
    CONF_REPEAT_CONTEXT_MINUTES,
    CONF_RESPONSE_STYLE,
    CONF_SCENE_CONTEXT,
    CONF_SNAPSHOT_COUNT,
    CONF_SNAPSHOT_INTERVAL_MS,
    CONF_SUN_ENTITY,
    CONF_TARGET_CAMERAS,
    CONF_TARGET_CONDITION,
    CONF_TARGET_MIN_SCORE,
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
    DEFAULT_SNAPSHOT_COUNT,
    DEFAULT_SNAPSHOT_INTERVAL_MS,
    DEFAULT_SUN_ENTITY,
    ACTION_SOUND_ALARM,
    DEFAULT_TARGET_CONDITION,
    DOMAIN,
    EVENT_ALERT,
    IMAGES_URL,
    MAX_PHOTOS_PER_VISITOR,
    MAX_REFERENCE_PHOTOS,
    NOTIFY_ARMED,
    NOTIFY_AWAY,
    NOTIFY_AWAY_OR_ARMED,
    NOTIFY_HIGH_SCORE,
    POLICY_CUSTOM,
    PRESENCE_ONLY_AWAY,
    PRESENCE_ONLY_HOME,
    SIGNAL_ANALYSIS_FAILED,
    SIGNAL_NEW_ALERT,
    SNAPSHOTS_URL,
    SUN_ABOVE_HORIZON,
    TIME_BETWEEN,
    TIME_DAY,
    TIME_NIGHT,
    TIME_NOT_BETWEEN,
)

if TYPE_CHECKING:
    from . import AlertStore

_LOGGER = logging.getLogger(__name__)

NO_MOTION_MARKER = "no obvious motion detected"

DEFAULT_SCENE_CONTEXT = (
    "No additional scene context was provided for this camera. If no gate "
    'is visible in the images, use "n/a" for gate_state and gate_risk.'
)

# Shared analysis guidance. Field formats are enforced by ALERT_STRUCTURE
# (structured mode) or by JSON_OUTPUT_SUFFIX (text-parsing fallback).
ANALYSIS_INSTRUCTIONS = """\
Motion has been detected by a camera at a residential property. You are being
shown {count} images taken {interval} apart, in chronological order. Compare
the images and describe what caused the motion.

SCENE CONTEXT: {scene_context}

Determine direction of travel using ONLY the apparent size change of the
subject across the frames: subject appears LARGER in later frames = moving
TOWARD the camera = "towards house" (approaching); SMALLER = moving AWAY =
"away from house" (leaving); cannot determine = "unknown".

Score suspicion from 1 to 10: 1 = completely benign (e.g. a cat walking
past); 10 = highly suspicious (e.g. a person in dark clothing with tools
approaching the house at night). Consider direction, activity, what is being
carried, time of day and gate state. If the score is 6 or above, begin the
short summary with "⚠️ ALERT: ".

If you see no obvious cause of motion, set both the short summary and the
detailed description to "No obvious motion detected" and the score to 1."""

# Appended only in the text-parsing fallback (providers without structured
# output). Structured mode gets the same field spec via ALERT_STRUCTURE.
JSON_OUTPUT_SUFFIX = """

Respond ONLY with a valid JSON object with these fields: "short" (string, max
80 characters), "detail" (string), "direction" (one of "towards house", "away
from house", "stationary", "unknown"), "carrying" (string), "activity"
(string), "gate_state" (one of "open", "closed", "unknown", "n/a" — use "n/a"
when the scene has no gate and "unknown" only when a gate exists but is not
visible), "gate_risk" (string, or "n/a"), "suspicious_index" (integer 1-10),
"known_person" (name of a listed known person the subject matches, or
"none"). Do not include any text outside the JSON object."""

# Schema passed to ai_task.generate_data's `structure` parameter so the
# provider returns validated fields directly (no prompt-and-parse).
ALERT_STRUCTURE = {
    "short": {
        "description": "One sentence, max 80 characters, for a notification.",
        "selector": {"text": {}},
    },
    "detail": {
        "description": (
            "2-3 sentences: appearance, direction of movement, what is being "
            "carried or done, and any notable behaviour."
        ),
        "selector": {"text": {"multiline": True}},
    },
    "direction": {
        "description": "Direction of travel relative to the house.",
        "selector": {
            "select": {
                "options": [
                    "towards house",
                    "away from house",
                    "stationary",
                    "unknown",
                ]
            }
        },
    },
    "carrying": {
        "description": "Anything being carried or held, or 'nothing visible'.",
        "selector": {"text": {}},
    },
    "activity": {
        "description": (
            "What the subject appears to be doing, e.g. 'walking towards the "
            "house', 'standing at the gate', 'loitering'."
        ),
        "selector": {"text": {}},
    },
    "gate_state": {
        "description": (
            "Gate state. Use 'n/a' if the scene has no gate; 'unknown' only "
            "if a gate exists but is not visible in the images."
        ),
        "selector": {
            "select": {"options": ["open", "closed", "unknown", "n/a"]}
        },
    },
    "gate_risk": {
        "description": (
            "One sentence assessing risk from the gate state combined with "
            "the motion, or 'n/a' if there is no gate."
        ),
        "selector": {"text": {}},
    },
    "suspicious_index": {
        "description": "Suspicion score, 1 (benign) to 10 (highly suspicious).",
        "selector": {"number": {"min": 1, "max": 10}},
    },
    "known_person": {
        "description": (
            "Name of the known person the subject clearly matches (from the "
            "KNOWN PEOPLE list, if provided), otherwise 'none'."
        ),
        "selector": {"text": {}},
    },
}


def _write_file(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


# Markers of a temporary, retryable provider problem (as opposed to the
# provider genuinely not supporting structured output). Matched case-
# insensitively against the error text.
_TRANSIENT_ERROR_MARKERS = (
    "503",
    "500",
    "429",
    "unavailable",
    "overload",
    "high demand",
    "try again",
    "rate limit",
    "ratelimit",
    "timeout",
    "timed out",
    "deadline",
    "internal error",
    "temporarily",
)


def _is_transient_error(err: Exception) -> bool:
    """True if the error looks temporary and worth retrying, not a capability
    limit. Errs toward "not transient" so a real structure-unsupported error
    still falls back to text parsing."""
    message = str(err).lower()
    return any(marker in message for marker in _TRANSIENT_ERROR_MARKERS)


def _parse_ai_result(raw: Any) -> dict[str, Any]:
    """Normalise an ai_task response into the alert field dict."""
    if isinstance(raw, str):
        cleaned = re.sub(r"```(?:json)?", "", raw).strip()
        raw = json.loads(cleaned)
    if not isinstance(raw, dict):
        raise HomeAssistantError(f"Unexpected AI response type: {type(raw).__name__}")
    # A missing/non-numeric score means a degraded, blocked or truncated
    # response — not a genuine "all clear". Treating it as score 1 would
    # manufacture a benign alert and, during a provider outage, hide a real
    # threat. Raise so it is counted and surfaced as a failed analysis.
    raw_score = raw.get("suspicious_index")
    if raw_score is None:
        raise HomeAssistantError(
            "AI response missing suspicious_index (degraded/blocked response)"
        )
    try:
        score = int(float(raw_score))
    except (TypeError, ValueError) as err:
        raise HomeAssistantError(
            f"AI response has non-numeric suspicious_index: {raw_score!r}"
        ) from err
    return {
        "score": min(10, max(1, score)),
        "short": str(raw.get("short", "")),
        "detail": str(raw.get("detail", "")),
        "direction": str(raw.get("direction", "unknown")),
        "carrying": str(raw.get("carrying", "unknown")),
        "activity": str(raw.get("activity", "unknown")),
        "gate_state": str(raw.get("gate_state", "n/a")),
        "gate_risk": str(raw.get("gate_risk", "n/a")),
        "known_person": str(raw.get("known_person", "none") or "none"),
    }


class CameraPipeline:
    """Snapshot burst -> AI analysis -> alert log -> notification."""

    def __init__(
        self,
        hass: HomeAssistant,
        store: "AlertStore",
        global_options: dict[str, Any],
        camera_id: str,
        camera_conf: dict[str, Any],
        targets: list[dict[str, Any]],
        known_visitors: list[dict[str, Any]] | None = None,
    ) -> None:
        self.hass = hass
        self.store = store
        self.camera_id = camera_id
        self.label = camera_conf.get(CONF_CAMERA_NAME) or camera_id.replace(
            "_", " "
        ).title()
        self.camera_entity = camera_conf[CONF_CAMERA_ENTITY]
        self.scene_context = (
            camera_conf.get(CONF_SCENE_CONTEXT) or DEFAULT_SCENE_CONTEXT
        )
        self.snapshot_count = int(
            global_options.get(CONF_SNAPSHOT_COUNT, DEFAULT_SNAPSHOT_COUNT)
        )
        self.snapshot_interval = (
            int(
                global_options.get(
                    CONF_SNAPSHOT_INTERVAL_MS, DEFAULT_SNAPSHOT_INTERVAL_MS
                )
            )
            / 1000
        )
        self.cooldown = int(
            global_options.get(CONF_COOLDOWN_SECONDS, DEFAULT_COOLDOWN_SECONDS)
        )
        self.targets = targets
        self.dashboard_path = global_options.get(
            CONF_DASHBOARD_PATH, DEFAULT_DASHBOARD_PATH
        )
        self.ai_task_entity = global_options.get(CONF_AI_TASK_ENTITY)
        # presence / alarm
        self.alarm_panel_entity = global_options.get(CONF_ALARM_PANEL_ENTITY)
        self.alarmo_enabled = bool(global_options.get(CONF_ALARMO_ENABLED, False))
        self.alarmo_trigger_score = int(
            global_options.get(
                CONF_ALARMO_TRIGGER_SCORE, DEFAULT_ALARMO_TRIGGER_SCORE
            )
        )
        # selective logging
        self.min_log_score = int(
            global_options.get(CONF_MIN_LOG_SCORE, DEFAULT_MIN_LOG_SCORE)
        )
        self.log_window_start = global_options.get(CONF_LOG_WINDOW_START)
        self.log_window_end = global_options.get(CONF_LOG_WINDOW_END)
        self.log_activity = bool(
            global_options.get(CONF_LOG_ACTIVITY, DEFAULT_LOG_ACTIVITY)
        )
        # context injected into the prompt
        self.known_visitors = known_visitors or []
        self.repeat_context_minutes = int(
            global_options.get(
                CONF_REPEAT_CONTEXT_MINUTES, DEFAULT_REPEAT_CONTEXT_MINUTES
            )
        )
        # AI personality / response-style override (applied to wording only)
        self.response_style = (global_options.get(CONF_RESPONSE_STYLE) or "").strip()
        # sun entity driving the day/night processing gate
        self.sun_entity = global_options.get(CONF_SUN_ENTITY) or DEFAULT_SUN_ENTITY
        # effective motion-ignore gate: this camera's own override, else house
        self.process = self._resolve_process_policy(global_options, camera_conf)
        # runtime state (survives pipeline rebuilds via the switch entity)
        self.paused = False
        # set False after the first structured-output failure so we don't
        # retry (and re-bill) it every analysis this session
        self._structured_ok = True
        self._lock = asyncio.Lock()
        self._last_run = 0.0

    @staticmethod
    def _resolve_process_policy(
        global_options: dict[str, Any], camera_conf: dict[str, Any]
    ) -> dict[str, Any]:
        """Effective processing policy: the camera's rules, or the house's.

        The rules (which presence/alarm/time groups gate processing) come from
        the camera when it opts into a custom policy, else from the house.
        Presence *entities* are always house-wide infrastructure, so they are
        read from the global options regardless.
        """
        use_camera = (
            camera_conf.get(
                CONF_CAMERA_MOTION_POLICY, DEFAULT_CAMERA_MOTION_POLICY
            )
            == POLICY_CUSTOM
        )
        src = camera_conf if use_camera else global_options
        return {
            "rules": CameraPipeline._rules_from_source(src),
            "presence_entities": list(
                global_options.get(CONF_PRESENCE_ENTITIES) or []
            ),
        }

    @staticmethod
    def _rules_from_source(src: dict[str, Any]) -> list[dict[str, Any]]:
        """Normalise a config source into a list of processing rules.

        Prefers the modern ``process_rules`` list. Falls back to the legacy
        flat ``process_*`` keys (the original single-gate model) so configs
        saved before rule groups existed keep working unchanged.
        """
        raw = src.get(CONF_PROCESS_RULES)
        if isinstance(raw, list) and raw:
            return [CameraPipeline._normalize_rule(r) for r in raw]
        return [CameraPipeline._normalize_rule(src)]

    @staticmethod
    def _normalize_rule(rule: dict[str, Any]) -> dict[str, Any]:
        """A rule dict with every condition key present and defaulted."""
        return {
            CONF_PROCESS_PRESENCE: rule.get(
                CONF_PROCESS_PRESENCE, DEFAULT_PROCESS_PRESENCE
            ),
            CONF_PROCESS_ARMED: rule.get(
                CONF_PROCESS_ARMED, DEFAULT_PROCESS_ARMED
            ),
            CONF_PROCESS_TIME_MODE: rule.get(
                CONF_PROCESS_TIME_MODE, DEFAULT_PROCESS_TIME_MODE
            ),
            CONF_PROCESS_TIME_START: rule.get(CONF_PROCESS_TIME_START),
            CONF_PROCESS_TIME_END: rule.get(CONF_PROCESS_TIME_END),
        }

    # -- triggering ------------------------------------------------------

    @callback
    def handle_motion_event(self, event: Event) -> None:
        """State-change listener for the configured motion entity.

        Every exit path logs at debug. Without this the trigger is a black
        box: a camera that never fires looks identical to one that was never
        subscribed, with nothing in the log to tell them apart.
        """
        entity_id = event.data.get("entity_id")
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        old = None if old_state is None else old_state.state
        new = None if new_state is None else new_state.state
        if new_state is None or new_state.state != "on":
            _LOGGER.debug(
                "%s: %s changed %s -> %s; not a motion start, ignoring",
                self.camera_id, entity_id, old, new,
            )
            return
        if old_state is not None and old_state.state == "on":
            # The source integration re-asserted "on" without ever clearing
            # to "off", so there is no edge to trigger on.
            _LOGGER.debug(
                "%s: %s re-asserted 'on' (no off->on edge), ignoring",
                self.camera_id, entity_id,
            )
            return
        _LOGGER.debug(
            "%s: %s changed %s -> on, starting analysis",
            self.camera_id, entity_id, old,
        )
        self.hass.async_create_task(self.async_analyze())

    async def async_analyze(self, force: bool = False) -> None:
        """Run the pipeline, respecting pause state and the per-camera cooldown."""
        if self.paused and not force:
            _LOGGER.debug("%s: analysis paused, skipping", self.camera_id)
            return
        # Motion-ignore gate: skip the whole pipeline (no snapshot, no AI, no
        # notify) when the presence/alarm/time rules say so. A manual run
        # (force) always bypasses it, like pause and cooldown.
        if not force and not self._should_process():
            _LOGGER.debug(
                "%s: motion ignored by processing rule, skipping", self.camera_id
            )
            return
        if self._lock.locked():
            _LOGGER.debug("%s: analysis already running, skipping", self.camera_id)
            return
        async with self._lock:
            if not force and time.monotonic() - self._last_run < self.cooldown:
                _LOGGER.debug("%s: within cooldown, skipping", self.camera_id)
                return
            self._last_run = time.monotonic()
            try:
                await self._run(force=force)
            except Exception as err:  # noqa: BLE001 - never break the listener
                _LOGGER.exception("%s: camera analysis failed", self.camera_id)
                self._record_activity(f"Analysis failed: {err}")
                async_dispatcher_send(
                    self.hass, SIGNAL_ANALYSIS_FAILED, self.camera_id
                )

    @callback
    def _record_activity(self, message: str) -> None:
        """Write one analysis-outcome line to the Home Assistant logbook.

        Sub-threshold and failed analyses never reach the alert history, so
        without this a working-but-quiet camera looks dead in its Activity
        timeline. Attaching the entry to the camera's recent-alert entity
        places it in that device's logbook, alongside its switch/button events.
        """
        if not self.log_activity:
            return
        try:
            from homeassistant.components.logbook import (  # noqa: PLC0415
                async_log_entry,
            )
        except ImportError:  # logbook component unavailable
            return
        entity_id = er.async_get(self.hass).async_get_entity_id(
            "binary_sensor", DOMAIN, f"{self.camera_id}_recent_alert"
        )
        if entity_id is None:
            return
        async_log_entry(self.hass, self.label, message, DOMAIN, entity_id)

    # -- pipeline steps ---------------------------------------------------

    async def _run(self, force: bool = False) -> None:
        paths = await self._capture_frames()
        report = await self._analyze_frames(paths)
        if NO_MOTION_MARKER in report["short"].lower():
            _LOGGER.debug("%s: AI saw no significant motion", self.camera_id)
            self._record_activity("Analysed — no significant motion")
            return
        mid_path = paths[len(paths) // 2]

        # Logging rules gate only what enters the history / the card. A
        # filtered-out alert can still notify and trip Alarmo (using the
        # transient snapshot image), so a real threat is never silently
        # dropped just because it fell outside the logging window.
        if force or self._should_log(report):
            record = await self.store.async_log(
                {
                    "camera_id": self.camera_id,
                    "camera_label": self.label,
                    "image_path": mid_path,
                    **report,
                }
            )
            async_dispatcher_send(self.hass, SIGNAL_NEW_ALERT, record)
            image_url = record["image"]
            logged = True
            self._record_activity(
                f"Logged alert (score {report['score']}): "
                f"{report['short'] or 'motion detected'}"
            )
        else:
            _LOGGER.debug(
                "%s: alert (score %s) not archived (logging rules)",
                self.camera_id,
                report["score"],
            )
            reason = (
                f"below the log threshold (min {self.min_log_score})"
                if report["score"] < self.min_log_score
                else "outside the log time window"
            )
            self._record_activity(
                f"Analysed (score {report['score']}) — {reason}, not logged"
            )
            image_url = f"{SNAPSHOTS_URL}/{os.path.basename(mid_path)}"
            logged = False

        # Archived images are served behind auth, so hand out a signed URL the
        # card <img>, the companion app and user automations can load without a
        # bearer. Transient snapshot URLs pass through unsigned.
        image_url = self._sign(image_url)
        self._fire_alert_event(report, image_url, logged)
        await self._maybe_trigger_alarmo(report)
        await self._notify(report, image_url)

    def _sign(self, url: str) -> str:
        """Sign an archived alert-image URL (retention-length, content-user)."""
        if not url.startswith(IMAGES_URL + "/"):
            return url
        return async_sign_path(
            self.hass,
            url,
            timedelta(days=max(1, int(self.store.retention_days))),
            use_content_user=True,
        )

    @callback
    def _fire_alert_event(
        self, report: dict[str, Any], image_url: str, logged: bool
    ) -> None:
        """Fire ai_camera_centre_alert so users can build automations."""
        self.hass.bus.async_fire(
            EVENT_ALERT,
            {
                "camera_id": self.camera_id,
                "camera_label": self.label,
                "image": image_url,
                "logged": logged,
                **report,
            },
        )

    # -- selective logging (min score + time window) ---------------------

    def _should_log(self, report: dict[str, Any]) -> bool:
        if report["score"] < self.min_log_score:
            return False
        return self._within_log_window()

    def _within_log_window(self) -> bool:
        return self._time_in_window(self.log_window_start, self.log_window_end)

    @staticmethod
    def _window_contains(start_s: Any, end_s: Any) -> bool | None:
        """True if now is within [start, end); wraps past midnight.

        None when no usable window is configured (blank, unparseable, or
        zero-length) so callers can decide what "no constraint" means for
        their mode — ``between`` treats it as always-on, ``not_between`` as
        never-off.
        """
        if not (start_s and end_s):
            return None
        start = dt_util.parse_time(start_s)
        end = dt_util.parse_time(end_s)
        if start is None or end is None or start == end:
            return None
        now_t = dt_util.now().time()
        if start < end:
            return start <= now_t < end
        # window wraps past midnight (e.g. 22:00 -> 06:00)
        return now_t >= start or now_t < end

    @classmethod
    def _time_in_window(cls, start_s: Any, end_s: Any) -> bool:
        """True if now is within [start, end); no usable window = True."""
        contains = cls._window_contains(start_s, end_s)
        return True if contains is None else contains

    # -- motion-ignore processing gate (OR of AND-groups; see const.py) --

    def _should_process(self) -> bool:
        """Process when ANY rule matches (OR). No rules = no restriction."""
        rules = self.process["rules"]
        if not rules:
            return True
        return any(self._rule_ok(rule) for rule in rules)

    def _rule_ok(self, rule: dict[str, Any]) -> bool:
        """One rule matches only when ALL its conditions hold (AND)."""
        return (
            self._presence_ok(rule)
            and self._armed_ok(rule)
            and self._time_ok(rule)
        )

    def _presence_ok(self, rule: dict[str, Any]) -> bool:
        mode = rule[CONF_PROCESS_PRESENCE]
        if mode == PRESENCE_ONLY_AWAY:
            return not self._anyone_home()
        if mode == PRESENCE_ONLY_HOME:
            return self._anyone_home()
        return True

    def _armed_ok(self, rule: dict[str, Any]) -> bool:
        mode = rule[CONF_PROCESS_ARMED]
        # Armed-based conditions need an alarm panel; without one, fail open so
        # the pipeline is never permanently disabled by a half-configured rule.
        if not self.alarm_panel_entity:
            return True
        if mode == ARMED_ONLY_ARMED:
            return self._is_armed()
        if mode == ARMED_ONLY_DISARMED:
            return not self._is_armed()
        return True

    def _time_ok(self, rule: dict[str, Any]) -> bool:
        mode = rule[CONF_PROCESS_TIME_MODE]
        if mode in (TIME_BETWEEN, TIME_NOT_BETWEEN):
            contains = self._window_contains(
                rule.get(CONF_PROCESS_TIME_START),
                rule.get(CONF_PROCESS_TIME_END),
            )
            if contains is None:
                return True  # no usable window -> no constraint (fail open)
            return contains if mode == TIME_BETWEEN else not contains
        if mode in (TIME_DAY, TIME_NIGHT):
            daytime = self._is_daytime()
            if daytime is None:
                return True  # sun entity unavailable -> fail open
            return daytime if mode == TIME_DAY else not daytime
        return True

    def _is_daytime(self) -> bool | None:
        """True if the sun entity is above the horizon, None if unknown."""
        state = self.hass.states.get(self.sun_entity)
        if state is None or state.state in ("unknown", "unavailable", ""):
            return None
        return state.state == SUN_ABOVE_HORIZON

    # -- prompt context (known people + recent activity) -----------------

    def _context_sections(self) -> str:
        parts = [
            s
            for s in (
                self._known_people_section(),
                self._recent_activity(),
                self._response_style_section(),
            )
            if s
        ]
        return ("\n\n" + "\n\n".join(parts)) if parts else ""

    def _response_style_section(self) -> str:
        """Personality/response-style overlay — wording only, never the score."""
        if not self.response_style:
            return ""
        return (
            f"RESPONSE STYLE: Write the 'short' and 'detail' text {self.response_style}. "
            "This styling applies to WORDING ONLY — it must NOT change the "
            "suspicion score, direction, gate assessment or any other factual "
            "field, and you must still follow every rule above (including using "
            '"No obvious motion detected" when nothing has actually moved).'
        )

    # -- known-visitor reference photos (visual recognition) -------------

    def _reference_photos(
        self, photos_by_id: dict[str, list[str]]
    ) -> list[tuple[str, str]]:
        """(name, media_content_id) for each attachable reference photo, capped."""
        refs: list[tuple[str, str]] = []
        for v in self.known_visitors:
            vid = v.get(CONF_VISITOR_ID)
            name = v.get(CONF_VISITOR_NAME)
            photos = photos_by_id.get(vid) or []
            if not (vid and name and photos):
                continue
            for fname in photos[:MAX_PHOTOS_PER_VISITOR]:
                refs.append(
                    (name, f"media-source://{DOMAIN}/known/{vid}/{fname}")
                )
                if len(refs) >= MAX_REFERENCE_PHOTOS:
                    _LOGGER.debug(
                        "%s: reference photos capped at %s",
                        self.camera_id,
                        MAX_REFERENCE_PHOTOS,
                    )
                    return refs
        return refs

    @staticmethod
    def _reference_photo_note(
        refs: list[tuple[str, str]], motion_count: int
    ) -> str:
        """Tell the model which leading images are reference photos."""
        if not refs:
            return ""
        n = len(refs)
        lines = "\n".join(
            f"- Image {i + 1}: reference photo of {name}"
            for i, (name, _cid) in enumerate(refs)
        )
        return (
            f"\n\nIMAGE ORDER: The first {n} image{'s' if n != 1 else ''} "
            "are reference photos of known people (NOT the motion event):\n"
            f"{lines}\nThe remaining {motion_count} images are the motion "
            "capture from the camera, in chronological order. Analyse ONLY the "
            "motion-capture images for the event; use the reference photos "
            'solely to decide whether the subject matches a known person (the '
            '"known_person" field).'
        )

    def _known_people_section(self) -> str:
        people = [
            f"- {v[CONF_VISITOR_NAME]}: {v[CONF_VISITOR_DESCRIPTION]}"
            for v in self.known_visitors
            if v.get(CONF_VISITOR_NAME) and v.get(CONF_VISITOR_DESCRIPTION)
        ]
        if not people:
            return ""
        return (
            "KNOWN PEOPLE (household members and regulars — NOT suspicious):\n"
            + "\n".join(people)
            + "\nIf the subject clearly matches one of these people, set "
            '"known_person" to their name and score low (1-2). If the subject '
            'does not clearly match anyone here, set "known_person" to "none" '
            "and score normally."
        )

    def _recent_activity(self) -> str:
        if self.repeat_context_minutes <= 0:
            return ""
        cutoff = time.time() - self.repeat_context_minutes * 60
        recent = [
            r
            for r in self.store.camera_alerts(self.camera_id)
            if float(r.get("ts", 0)) >= cutoff
        ]
        if not recent:
            return ""
        now = time.time()
        lines = []
        for r in recent[:5]:
            mins = max(0, int((now - float(r.get("ts", now))) / 60))
            who = r.get("known_person") or "none"
            tag = f" [{who}]" if who != "none" else ""
            lines.append(
                f"- {mins} min ago (score {r.get('score')}){tag}: "
                f"{r.get('short', '')}"
            )
        return (
            f"RECENT ACTIVITY AT THIS CAMERA (last {self.repeat_context_minutes} "
            "min, newest first):\n"
            + "\n".join(lines)
            + "\nIf this looks like the same subject as a recent entry, still "
            "present or returning, say so in the detail and consider a higher "
            "score for loitering or repeated approaches."
        )

    # -- presence / alarm state ------------------------------------------

    def _anyone_home(self) -> bool:
        """True if any tracked person is home.

        Uses the configured presence entities (person and/or device_tracker)
        when set, otherwise every ``person.*`` entity. Returns False when no
        tracked entity resolves to a state, matching the original "no people
        configured -> treat as away" fail-open behaviour.
        """
        entities = self.process.get("presence_entities")
        if entities:
            states = [
                s
                for s in (self.hass.states.get(e) for e in entities)
                if s is not None
            ]
        else:
            states = self.hass.states.async_all("person")
        return any(state.state == "home" for state in states)

    def _is_armed(self) -> bool:
        if not self.alarm_panel_entity:
            return False
        state = self.hass.states.get(self.alarm_panel_entity)
        return state is not None and state.state in ARMED_STATES

    def _condition_met(self, condition: str) -> bool:
        if condition == NOTIFY_AWAY:
            return not self._anyone_home()
        if condition == NOTIFY_ARMED:
            return self._is_armed()
        if condition == NOTIFY_AWAY_OR_ARMED:
            return not self._anyone_home() or self._is_armed()
        return True  # NOTIFY_ALWAYS / unknown

    # -- alarmo ----------------------------------------------------------

    async def _maybe_trigger_alarmo(self, report: dict[str, Any]) -> None:
        """Trip Alarmo on a high-risk alert, but only while already armed."""
        if not self.alarmo_enabled or not self.alarm_panel_entity:
            return
        if report["score"] < self.alarmo_trigger_score:
            return
        if not self._is_armed():
            _LOGGER.debug(
                "%s: score %s >= Alarmo threshold but panel not armed; skipping",
                self.camera_id,
                report["score"],
            )
            return
        try:
            await self.hass.services.async_call(
                "alarmo",
                "trigger",
                {"entity_id": self.alarm_panel_entity},
                blocking=False,
            )
            _LOGGER.warning(
                "%s: triggered Alarmo (%s) on score %s",
                self.camera_id,
                self.alarm_panel_entity,
                report["score"],
            )
        except Exception:  # noqa: BLE001 - alarmo missing / API change
            _LOGGER.exception("%s: failed to trigger Alarmo", self.camera_id)

    def _clear_old_snapshots_sync(self) -> None:
        try:
            for name in os.listdir(self.store.snapshots_dir):
                if name.startswith(f"{self.camera_id}_") and name.endswith(".jpg"):
                    os.remove(os.path.join(self.store.snapshots_dir, name))
        except OSError:
            pass

    async def _capture_frames(self) -> list[str]:
        # Snapshots are served on an unauthenticated static path (so they
        # can be shown in notifications), so filenames carry a per-run
        # random token to make the URLs unguessable (capability URLs).
        await self.hass.async_add_executor_job(self._clear_old_snapshots_sync)
        token = py_secrets.token_hex(8)
        paths: list[str] = []
        for i in range(1, self.snapshot_count + 1):
            image = await camera.async_get_image(self.hass, self.camera_entity)
            path = os.path.join(
                self.store.snapshots_dir, f"{self.camera_id}_{token}_{i}.jpg"
            )
            await self.hass.async_add_executor_job(_write_file, path, image.content)
            paths.append(path)
            if i < self.snapshot_count:
                await asyncio.sleep(self.snapshot_interval)
        return paths

    async def _analyze_frames(self, paths: list[str]) -> dict[str, Any]:
        interval = (
            f"{self.snapshot_interval:g} second"
            f"{'s' if self.snapshot_interval != 1 else ''}"
        )
        photos_by_id = await self.hass.async_add_executor_job(
            self.store.known_photos_map
        )
        refs = self._reference_photos(photos_by_id)
        instructions = (
            ANALYSIS_INSTRUCTIONS.format(
                count=len(paths),
                interval=interval,
                scene_context=self.scene_context,
            )
            + self._reference_photo_note(refs, len(paths))
            + self._context_sections()
        )
        # Reference photos first, then the motion frames — the IMAGE ORDER
        # note above tells the model which is which.
        attachments = [
            {"media_content_id": cid, "media_content_type": "image/jpeg"}
            for _name, cid in refs
        ] + [
            {
                "media_content_id": (
                    f"media-source://{DOMAIN}/snapshots/{os.path.basename(p)}"
                ),
                "media_content_type": "image/jpeg",
            }
            for p in paths
        ]
        base: dict[str, Any] = {
            "task_name": f"{self.label} analysis",
            "attachments": attachments,
        }
        if self.ai_task_entity:
            base["entity_id"] = self.ai_task_entity

        # Prefer schema-enforced structured output; fall back to prompt-and-
        # parse for providers/entities that don't support a structure.
        if self._structured_ok:
            try:
                data = await self._call_ai_task(
                    {
                        **base,
                        "instructions": instructions,
                        "structure": ALERT_STRUCTURE,
                    }
                )
            except Exception as err:  # noqa: BLE001 - classify below
                # A transient provider error (503/overloaded/timeout/rate
                # limit) must NOT permanently drop the session to the weaker
                # text parser — that latched off over a single blip before.
                # Fail this event (it is counted) and retry structured next
                # time. Only a genuine "structure unsupported" latches off.
                if _is_transient_error(err):
                    raise
                _LOGGER.info(
                    "%s: structured AI output unsupported (%s); using text "
                    "parsing for the rest of this session",
                    self.camera_id,
                    err,
                )
                self._structured_ok = False
            else:
                # The call succeeded; a parse failure here is a degraded
                # response, counted as a failure, and does not latch off.
                return _parse_ai_result(data)

        data = await self._call_ai_task(
            {**base, "instructions": instructions + JSON_OUTPUT_SUFFIX}
        )
        return _parse_ai_result(data)

    async def _call_ai_task(self, service_data: dict[str, Any]) -> Any:
        result = await self.hass.services.async_call(
            "ai_task",
            "generate_data",
            service_data,
            blocking=True,
            return_response=True,
        )
        if not isinstance(result, dict) or "data" not in result:
            raise HomeAssistantError(f"Unexpected ai_task response: {result!r}")
        return result["data"]

    async def _notify(self, report: dict[str, Any], image_url: str) -> None:
        for target in self.targets:
            if report["score"] < int(target.get(CONF_TARGET_MIN_SCORE, 1)):
                continue
            cameras = target.get(CONF_TARGET_CAMERAS) or []
            if cameras and self.camera_id not in cameras:
                continue
            condition = target.get(CONF_TARGET_CONDITION, DEFAULT_TARGET_CONDITION)
            if not self._condition_met(condition):
                continue
            service = str(target[CONF_TARGET_SERVICE]).removeprefix("notify.")
            try:
                await self.hass.services.async_call(
                    "notify",
                    service,
                    {
                        "title": f"{self.label} Motion [{report['score']}/10]",
                        "message": report["short"],
                        "data": self._notification_data(report, image_url),
                    },
                    blocking=False,
                )
            except Exception:  # noqa: BLE001 - one bad target must not stop others
                _LOGGER.exception("%s: notify.%s failed", self.camera_id, service)

    def _notification_data(
        self, report: dict[str, Any], image_url: str
    ) -> dict[str, Any]:
        """Build the companion-app notification payload.

        High-scoring alerts use a separate high-importance Android channel
        (so they can be allowed to ring through Do Not Disturb) and the iOS
        time-sensitive interruption level. A "Sound alarm" action button is
        added when an alarm panel is configured.
        """
        high = report["score"] >= NOTIFY_HIGH_SCORE
        data: dict[str, Any] = {
            "image": image_url,
            "clickAction": self.dashboard_path,
            # one live notification per camera; a newer alert replaces it
            "tag": f"{DOMAIN}_{self.camera_id}",
            "channel": "AI Camera high alerts" if high else "AI Camera alerts",
            "importance": "high" if high else "default",
            "priority": "high" if high else "normal",
            "ttl": 0,
            # iOS
            "push": {"interruption-level": "time-sensitive" if high else "active"},
        }
        if self.alarm_panel_entity:
            data["actions"] = [
                {"action": ACTION_SOUND_ALARM, "title": "Sound alarm"}
            ]
        return data
