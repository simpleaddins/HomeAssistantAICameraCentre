"""Constants for the AI Camera Centre integration."""

DOMAIN = "ai_camera_centre"
VERSION = "2.11.0"

# subentry types
SUBENTRY_CAMERA = "camera"
SUBENTRY_TARGET = "alert_target"
SUBENTRY_KNOWN_VISITOR = "known_visitor"

# how recent an alert must be for the per-camera binary sensor to read "on"
RECENT_ALERT_MINUTES = 5

# -- global options ------------------------------------------------------
CONF_RETENTION_DAYS = "retention_days"
CONF_SNAPSHOT_COUNT = "snapshot_count"
CONF_SNAPSHOT_INTERVAL_MS = "snapshot_interval_ms"
CONF_COOLDOWN_SECONDS = "cooldown_seconds"
CONF_DASHBOARD_PATH = "dashboard_path"
CONF_AI_TASK_ENTITY = "ai_task_entity"
CONF_ALARM_PANEL_ENTITY = "alarm_panel_entity"
# alarmo integration
CONF_ALARMO_ENABLED = "alarmo_enabled"
CONF_ALARMO_TRIGGER_SCORE = "alarmo_trigger_score"
# selective logging
CONF_MIN_LOG_SCORE = "min_log_score"
CONF_LOG_WINDOW_START = "log_window_start"
CONF_LOG_WINDOW_END = "log_window_end"
# record every analysis outcome (incl. sub-threshold + failures) to the
# Home Assistant logbook, so a working-but-quiet camera is visible there
CONF_LOG_ACTIVITY = "log_activity"
DEFAULT_LOG_ACTIVITY = True
# repeat-visitor context
CONF_REPEAT_CONTEXT_MINUTES = "repeat_context_minutes"
# AI personality / response-style override (global, wording only)
CONF_RESPONSE_STYLE = "response_style"

# -- motion-ignore processing gate --------------------------------------
# A trigger is only processed (snapshot burst + AI + notify) when at least
# one *rule* permits it. A rule is a group of presence/alarm/time conditions
# that must ALL hold (AND); the camera processes when ANY rule matches (OR).
# This is disjunctive normal form, so any boolean combination the UI can
# express reduces to "OR of AND-groups". Manual runs (force) always bypass.
#
# Rules live under CONF_PROCESS_RULES as a list of dicts, each keyed by the
# per-condition CONF_PROCESS_* keys below. An empty/absent list means "no
# restriction" (always process). For backwards compatibility a config that
# still carries the flat CONF_PROCESS_* keys (the old single-gate model) is
# read as a single rule.
CONF_PROCESS_RULES = "process_rules"
CONF_RULE_ENABLED = "enabled"
MAX_PROCESS_RULES = 3  # rule groups offered per form (house and per-camera)

# per-condition keys (used both as flat legacy keys and inside a rule dict)
CONF_PROCESS_PRESENCE = "process_presence"
CONF_PROCESS_ARMED = "process_armed"
CONF_PROCESS_TIME_MODE = "process_time_mode"
CONF_PROCESS_TIME_START = "process_time_start"
CONF_PROCESS_TIME_END = "process_time_end"
# person / device_tracker entities that count towards "someone is home".
# Empty = fall back to every person.* entity (the original behaviour).
CONF_PRESENCE_ENTITIES = "presence_entities"
# entity whose state drives day/night for the time gate (above_horizon = day)
CONF_SUN_ENTITY = "sun_entity"
DEFAULT_SUN_ENTITY = "sun.sun"
SUN_ABOVE_HORIZON = "above_horizon"

# presence gate values
PRESENCE_ALWAYS = "always"
PRESENCE_ONLY_AWAY = "only_away"  # process only when nobody is home
PRESENCE_ONLY_HOME = "only_home"  # process only when someone is home
DEFAULT_PROCESS_PRESENCE = PRESENCE_ALWAYS

# alarm gate values
ARMED_ALWAYS = "always"
ARMED_ONLY_ARMED = "only_armed"
ARMED_ONLY_DISARMED = "only_disarmed"
DEFAULT_PROCESS_ARMED = ARMED_ALWAYS

# time gate values
TIME_ALWAYS = "always"
TIME_BETWEEN = "between"  # inside process_time_start .. process_time_end
TIME_NOT_BETWEEN = "not_between"  # outside that window (e.g. "not 08:00-09:00")
TIME_DAY = "day"  # sun above horizon
TIME_NIGHT = "night"  # sun below horizon
DEFAULT_PROCESS_TIME_MODE = TIME_ALWAYS

# per-camera processing policy
POLICY_FOLLOW_HOUSE = "follow_house"
POLICY_CUSTOM = "custom"
DEFAULT_CAMERA_MOTION_POLICY = POLICY_FOLLOW_HOUSE
CONF_CAMERA_MOTION_POLICY = "motion_policy"

DEFAULT_RETENTION_DAYS = 7
DEFAULT_SNAPSHOT_COUNT = 5
DEFAULT_SNAPSHOT_INTERVAL_MS = 500
DEFAULT_COOLDOWN_SECONDS = 30
DEFAULT_DASHBOARD_PATH = "/lovelace/alerts"
DEFAULT_REPEAT_CONTEXT_MINUTES = 15  # 0 = disabled
DEFAULT_ALARMO_TRIGGER_SCORE = 9
DEFAULT_MIN_LOG_SCORE = 1

# score at/above which notifications use the high-priority channel
NOTIFY_HIGH_SCORE = 7

# mobile_app notification action id for the "Sound alarm" button
ACTION_SOUND_ALARM = "ACC_SOUND_ALARM"

# alarm_control_panel states treated as "armed"
ARMED_STATES = frozenset(
    {
        "armed_home",
        "armed_away",
        "armed_night",
        "armed_vacation",
        "armed_custom_bypass",
    }
)

# notify_condition values (per alert target)
NOTIFY_ALWAYS = "always"
NOTIFY_AWAY = "away"
NOTIFY_ARMED = "armed"
NOTIFY_AWAY_OR_ARMED = "away_or_armed"
DEFAULT_TARGET_CONDITION = NOTIFY_ALWAYS

# -- per-camera subentry data --------------------------------------------
CONF_CAMERA_ID = "camera_id"  # stable slug; storage/record identity
CONF_CAMERA_NAME = "name"
CONF_CAMERA_ENTITY = "camera_entity"
CONF_MOTION_ENTITIES = "motion_entities"
CONF_SCENE_CONTEXT = "scene_context"

# -- known visitor subentry data -----------------------------------------
CONF_VISITOR_ID = "visitor_id"  # stable slug; keys the reference-photo dir
CONF_VISITOR_NAME = "name"
CONF_VISITOR_DESCRIPTION = "description"

# reference photos per known visitor (visual recognition)
KNOWN_DIR_NAME = "known"  # <config>/ai_camera_centre/known/<visitor_id>/*.jpg
# how many reference photos to attach to the prompt (per person / overall)
MAX_PHOTOS_PER_VISITOR = 2
MAX_REFERENCE_PHOTOS = 6
# upload limits for the photo endpoint
MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # 8 MB

# -- alert target subentry data ------------------------------------------
CONF_TARGET_NAME = "name"  # optional friendly name; derived if blank
CONF_TARGET_SERVICE = "service"
CONF_TARGET_MIN_SCORE = "min_score"
CONF_TARGET_CAMERAS = "cameras"  # camera ids; empty list = all cameras
CONF_TARGET_CONDITION = "notify_condition"

# -- storage / urls ------------------------------------------------------
STORAGE_DIR = "ai_camera_centre"  # created under the HA config directory

IMAGES_URL = f"/{DOMAIN}/images"
SNAPSHOTS_URL = f"/{DOMAIN}/snapshots"
KNOWN_URL = f"/{DOMAIN}/known"
CARD_URL = f"/{DOMAIN}/ai-camera-centre-card.js"

# authenticated HTTP endpoint the people card posts reference photos to
UPLOAD_URL = f"/api/{DOMAIN}/known_photo"

SIGNAL_NEW_ALERT = f"{DOMAIN}_new_alert"
# dispatched with the camera_id whenever an analysis fails (provider error,
# degraded/blocked response, missing score) so the failure-count sensor ticks
SIGNAL_ANALYSIS_FAILED = f"{DOMAIN}_analysis_failed"

# fired on the HA event bus for every alert (logged or not) so users can
# build their own automations
EVENT_ALERT = f"{DOMAIN}_alert"
