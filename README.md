<img src="https://raw.githubusercontent.com/simpleaddins/HomeAssistantAICameraCentre/main/assets/logo-wide.png" alt="AI Camera Centre" width="490">

A self-contained Home Assistant custom integration (HACS-compatible) that
turns your cameras into an AI-powered alerting system — no YAML scripts or
automations required.

Point it at a camera stream and a motion sensor, and AI Camera Centre does
the rest: on motion it captures a burst of snapshots, sends them to your AI
provider for analysis (what caused the motion, direction of travel, what
they're carrying, a 1–10 suspicion score), archives the alert with its image,
notifies your phone, and shows everything on a bundled Lovelace timeline
card.

## Features

- **A device per camera** — each camera you add appears as its own device
  in Home Assistant with its own entities (see below), added straight from
  the integration page with a native **Add camera** button.
- **Built-in analysis pipeline** — configure cameras entirely in the UI:
  camera entity, one or more motion triggers, and an optional per-camera
  scene description that is injected into the AI prompt (e.g. "a gate is
  visible; subjects behind the gate are likely arriving").
- **Alert targets** — add notify services the same way you add cameras
  (their own **Add alert target** button). Each target has its own minimum
  suspicion score, an optional camera filter, and a **notify condition**
  (always / only when nobody's home / only when the alarm is armed /
  away-or-armed), so one phone can get every event while another is only
  woken for high-risk alerts when you're out.
- **Alarmo integration** — optionally trip
  [Alarmo](https://github.com/nielsfaber/alarmo) when a high-risk alert
  lands while the alarm is already armed, so the AI can sound the siren,
  not just ping a phone.
- **Selective logging** — keep the history clean: only archive alerts at or
  above a minimum score, and/or only during a chosen time window (e.g.
  nighttime only).
- **AI-powered reports** via Home Assistant's `ai_task` — works with any
  configured AI provider (Google Generative AI, OpenAI, Ollama, ...).
  Each alert includes a short notification line, detailed description,
  direction of travel, activity, carried items, gate state/risk, and a
  1–10 suspicion score.
- **Known visitors** — add household members and regulars (a name and a
  description) so the AI recognises them and scores them low; the recognised
  name is recorded on the alert (and, being low-scoring, they won't wake
  targets whose minimum score is higher). You can also **upload reference
  photos** for each known person (via the bundled *AI Camera Centre People*
  card); the photos are attached to the AI prompt so it can match faces
  visually, not just by description.
- **Motion-ignore processing rules** — skip AI analysis entirely (no snapshot,
  no AI call, no notification — saving cost) unless the moment matches one of
  your rules. Each rule combines **presence** (e.g. only when nobody's home),
  **alarm state** (e.g. only when armed) and **time** (inside or outside a fixed
  window, or daytime/nighttime by your sun entity). Conditions within a rule are
  **AND**ed; up to three rules are **OR**ed together, so you can express things
  like *"process when nobody's home **or** at night, **or** when someone's home
  but **not** between 08:00–09:00"*. Choose which `person`/`device_tracker`
  entities count as "home". Set house-wide rules, and let each camera either
  follow them or define its own. The *Analyze now* button and the service
  always bypass these rules.
- **AI response style** — give the alerts a personality (e.g. "in the style of
  Samuel L. Jackson"). It shapes the wording only; the suspicion score and the
  factual fields are unaffected.
- **Repeat-visitor awareness** — a camera's recent alerts are fed back into
  the prompt so the AI can spot the same person returning or loitering and
  raise the score accordingly.
- **Mobile notifications** with the alert image and a tap-through to your
  dashboard. High-scoring alerts (7+) use a separate high-importance
  notification channel so you can let them ring through Do Not Disturb, and
  get the iOS time-sensitive level; when an alarm panel is configured the
  notification carries a **Sound alarm** action button that trips Alarmo.
- **Per-camera devices** placed automatically in the same **area** as your
  source camera entity (you can move them afterwards).
- **Bundled timeline card** — rolling history grouped by day, camera filter
  chips, score badges, tap to expand the full image and report. New alerts
  appear live over a websocket subscription (no polling). Served by the
  integration and auto-registered as a dashboard resource. Archived alert
  images are delivered as signed, expiring URLs rather than public links.
- **Automatic retention** — alerts and images older than N days (default 7)
  are pruned automatically.
- **Per-camera entities** — every camera device carries: an *Alerts (24h)*
  count sensor, a *Last score* sensor, a *Recent alert* binary sensor, a
  *Latest alert* image, an *Analysis* switch to pause/resume that camera,
  and an *Analyze now* button. Use them on dashboards and in your own
  automations.
- **Services** — `ai_camera_centre.analyze` triggers the pipeline on demand;
  `ai_camera_centre.log_alert` lets advanced users log alerts from their own
  scripts into the same history.

## Requirements

- Home Assistant 2025.8 or newer
- An AI provider configured for **AI Tasks** (Settings → Devices & Services,
  e.g. Google Generative AI or OpenAI, then set it as the default AI Task
  entity or pick one in this integration's settings)
- A camera entity per camera, and ideally a motion `binary_sensor` per
  camera to trigger analysis

## Installation

### HACS (custom repository)

1. HACS → ⋮ → Custom repositories
2. Repository: `https://github.com/simpleaddins/HomeAssistantAICameraCentre`,
   type: **Integration**
3. Install **AI Camera Centre**, restart Home Assistant

### Manual

Copy `custom_components/ai_camera_centre/` into your
`config/custom_components/` folder and restart.

## Setup

1. Settings → Devices & Services → Add Integration → **AI Camera Centre**
   and fill in the global settings.
2. On the integration page, click **Add camera** (a native "+" button, not
   the Configure menu):
   - **Camera name** — e.g. "Side Gate"
   - **Camera stream entity** — the `camera.*` entity to snapshot
   - **Motion triggers** — one or more entities (`binary_sensor`,
     `input_boolean` or `switch`); any of them turning on starts the
     analysis (optional; leave blank to trigger only via the `analyze`
     service or the camera's *Analyze now* button)
   - **Scene context** — optional but recommended: describe what the camera
     sees and state explicitly whether a gate is visible

   Each camera you add becomes its own **device** with its entities.
3. On the same page, click **Add alert target**:
   - **Notify service** — pick from the dropdown
     (e.g. `notify.mobile_app_your_phone`)
   - **Minimum suspicion score** — 1 sends every alert; 6+ only wakes this
     target for genuinely suspicious events
   - **When to notify** — always, or only when nobody's home / the alarm is
     armed / either (the armed options need an alarm panel set in Settings)
   - **Cameras** — optionally restrict this target to specific cameras
4. Optional, on the integration page click **Add known visitor** for each
   household member or regular — a **name** and a **description** of
   distinguishing features (build, typical clothing, a pet, a wheelchair,
   etc.). The description is added to every camera's prompt so the AI can
   recognise them and score them low.

   **Reference photos live on a dashboard card**, so the AI can match faces
   visually rather than only by description:

   1. Open any dashboard → **Edit** → **+ Add Card** → search
      **"AI Camera Centre People"** (or add
      `type: custom:ai-camera-centre-people-card` in YAML).
   2. Use **+ Add person** on the card to create people (name + description) —
      the same thing the *Add known visitor* button does, so you can stay on
      the dashboard.
   3. Each person then gets a **+ Add photo** button; uploaded photos appear as
      thumbnails with a **×** to remove them.

   Uploading is **admin-only**. Photos are stored under
   `<config>/ai_camera_centre/known/<visitor_id>/` and attached to the AI
   prompt. If the card doesn't appear in the picker, the bundled resource
   hasn't loaded — hard-refresh the browser (Ctrl+F5) or reset the companion
   app's frontend cache.
5. Optional, in the integration's **Configure** button (global **Settings**).
   The settings are grouped into collapsible sections, each with inline help:
   - **Capture & analysis** — snapshots per analysis, the delay between them,
     the per-camera cooldown, and which **AI Task entity** analyses the frames
   - **Alerts & history** — **minimum score to log**, retention, the
     recent-activity context window (repeat-visitor/loitering awareness), an
     optional **log time window**, and the dashboard notifications open
   - **Alarm & Alarmo** — pick your `alarm_control_panel.*` to enable the
     armed notify conditions and the alarm-based processing rule, and
     optionally **trigger Alarmo** on high-risk alerts while armed
   - **Motion processing (house default)** — the house-wide rules for when to
     run AI analysis at all. Define up to three **rule groups**; the camera
     processes when **any** rule matches (OR), and a rule matches when **all**
     its conditions hold (AND). Each rule combines **presence**, **alarm state**
     and **time** (inside/outside a fixed window, or **daytime/nighttime** via
     the **sun entity**, default `sun.sun`). Pick which `person`/`device_tracker`
     entities count as "home". Each camera can follow these defaults or set its
     own rules under the **Motion processing** section when you add/edit it
   - **AI response style** — optional wording overlay for the alert text
     (never changes the score)
6. Repeat for each camera and target. That's it — walk in front of a camera
   to test, use its *Analyze now* button, or call the service manually:

```yaml
action: ai_camera_centre.analyze
data:
  camera_id: side_gate
```

### Card

```yaml
type: custom:ai-camera-centre-card
title: Camera Alerts
days: 7
```

Tap a row to expand the full report; tap the expanded image for a
full-screen lightbox (click or × to close).

A second card manages reference photos for known people (same bundled
resource, so no extra install):

```yaml
type: custom:ai-camera-centre-people-card
title: Known People
```

It lists the known visitors you added on the integration page; upload or
remove each person's photos here (admin only).

If auto-registration of the resource fails (e.g. YAML-mode dashboards), add
it manually: Settings → Dashboards → Resources → Add →
URL `/ai_camera_centre/ai-camera-centre-card.js`, type **JavaScript module**.

### Entities per camera

Each camera device exposes:

| Entity | What it does |
| --- | --- |
| `sensor.<camera>_alerts_24h` | Alert count in the last 24 h; attributes `last_alert`, `last_score`, `last_short`, `last_image`, `max_score_24h` |
| `sensor.<camera>_last_score` | Suspicion score (1–10) of the most recent alert |
| `binary_sensor.<camera>_recent_alert` | On for a few minutes after each alert |
| `image.<camera>_latest_alert` | The latest alert snapshot (drop onto a dashboard) |
| `switch.<camera>_analysis` | Turn a camera's automatic analysis off/on (holiday mode, gardener day). The *Analyze now* button and service still work while off |
| `button.<camera>_analyze` | Run an analysis on demand |
| `sensor.<camera>_analysis_failures` | Cumulative count of failed analyses (provider error, blocked/degraded response, missing score). A `total_increasing` statistics counter — chart it per day/week/month to see how often events go unassessed. Diagnostic |

### Events

Every alert fires an `ai_camera_centre_alert` event on the bus (whether or
not it was archived), so you can build your own automations:

```yaml
trigger:
  - trigger: event
    event_type: ai_camera_centre_alert
condition:
  - "{{ trigger.event.data.score >= 7 }}"
action:
  - action: light.turn_on
    target:
      entity_id: light.porch
```

Event data: `camera_id`, `camera_label`, `score` (1–10), `short`, `detail`,
`direction`, `carrying`, `activity`, `gate_state`, `gate_risk`,
`known_person` (recognised household member, or `none`), `image` (URL), and
`logged` (whether it was archived to the history).

## How the pipeline works

1. Any of the camera's motion triggers turns `on` (per-camera cooldown
   prevents alert storms)
2. A burst of snapshots is captured from the camera stream (count and
   interval configurable; default 5 shots, 500 ms apart)
3. The frames go to `ai_task.generate_data` with your per-camera scene
   context; the AI compares frames to determine what moved, in which
   direction, and how suspicious it looks (1–10). Responses use
   schema-enforced structured output where the provider supports it, and
   fall back to prompt-and-parse JSON otherwise
4. "No obvious motion" results are dropped. Remaining alerts are checked
   against the logging rules (minimum score + optional time window); alerts
   that pass are archived (image + full report) and shown on the card
5. If Alarmo triggering is enabled and the score meets the threshold while
   the panel is armed, Alarmo is tripped
6. Every alert target whose minimum score, camera filter and notify
   condition (presence / armed state) all match gets the summary, the
   image, and a tap-through to your dashboard

Notes on the filters — the logging rules and the notification rules are
independent, by design:

- The **logging rules** (minimum score to log, time window) decide only
  what enters the **history and the card**. An alert filtered out here is
  *not* archived, but it can still notify and trigger Alarmo — so a genuine
  threat is never silently dropped just because it fell outside your
  "nighttime only" logging window. Its notification simply uses the
  temporary snapshot image rather than an archived one.
- The **notification rules** (each target's minimum score, camera filter
  and notify condition) decide who gets pushed. So you can, for example,
  keep your history to nighttime events only while still being notified of
  daytime threats when you're away.
- "Nobody home" is true when no `person.*` entity is in the `home` zone; if
  you have no person entities at all it is treated as away (fail open).

Storage lives in `<config>/ai_camera_centre/` (a JSONL log plus images).

## Advanced: bring your own pipeline

If you want full control of the prompt or flow, you can keep running your
own script/automation and log results into the same history and card with
`ai_camera_centre.log_alert` — see
[`examples/camera_alert_script.yaml`](examples/camera_alert_script.yaml).

## Troubleshooting

**"Custom element doesn't exist: ai-camera-centre-card"** — the card's
JavaScript isn't reaching your browser. Check, in order:

1. *Is the integration serving it?* Open
   `http://<ha-address>:8123/ai_camera_centre/ai-camera-centre-card.js` —
   you should see JavaScript. A 404 means the integration isn't set up or
   an old version is installed (HACS → Redownload, restart, and make sure
   the integration entry exists under Devices & Services).
2. *Is the resource registered, and on the current version?* Settings →
   Dashboards → ⋮ → Resources (requires "Advanced mode" on your profile).
   There should be an entry for
   `/ai_camera_centre/ai-camera-centre-card.js?v=<version>`; add it manually
   as a **JavaScript module** if missing, and delete any stale
   `/alert_history/...` entry.

   **Check the `?v=` matches your installed version.** That query is the
   cache-buster, and before 2.8.3 it was only ever written on first install —
   so an instance upgraded over time could still be requesting (and your
   browser still serving from cache) the JavaScript from the version you
   originally installed. The visible symptom is cards added in later releases
   going missing: the **AI Camera Centre People** card absent from the card
   picker, and a *configuration error* when added by hand. 2.8.3 rewrites the
   version on upgrade; to fix an affected instance immediately, edit the `?v=`
   to the current version (or delete the row and restart), then hard-refresh.
3. *Clear the frontend cache* — this is the usual culprit. Hard-refresh the
   browser (Ctrl+F5); in the companion app: Settings → Companion App →
   Debugging → **Reset frontend cache**.

**No alerts are generated** — check Settings → System → Logs for
`ai_camera_centre` errors. The most common cause is no AI Task provider:
you need one configured (e.g. Google Generative AI or OpenAI) and either
set as the default AI Task entity or selected in this integration's
Settings.

**One camera triggers, another (with identical settings) doesn't** — the
usual cause is a **motion-trigger entity id that no longer exists**. A camera
is wired to its trigger by exact entity id, so if that id changes — the source
camera integration was updated, the device was re-added, or the entity was
renamed — the source integration still shows motion but this integration never
runs, and the two cameras diverge even though their AI Camera Centre config
looks the same. Since 2.8.0 this is logged at startup:
*"Camera '…': motion trigger … not found in Home Assistant …"* — check
Settings → System → Logs. The fix is to **edit the camera and re-select its
Motion triggers** so they point at the current entity. You can confirm which
entity is actually flipping under Developer Tools → States, and cross-check the
ids each camera is configured with in the integration's **Download
diagnostics** (⋮ menu).

**A camera only fires sometimes, for the wrong kind of event** — check which
trigger entities it's actually subscribed to. Cameras of the same model share
a device name, so Home Assistant disambiguates their entity ids with numeric
suffixes (`..._motion_2`, `..._person_3`), and it's easy to pick sensors
belonging to a *different* camera — or to pick only some event types (e.g.
*vehicle* and *animal* but not *motion* or *person*, so the camera never fires
for a person). Everything resolves and nothing errors; the camera just stays
quiet. Since 2.8.2 a warning is logged at startup when a trigger belongs to a
different device than the camera entity. To check by hand: Settings → Devices &
Services → **Entities**, search the entity id, and look at its **Device**
column. Renaming each camera device (Settings → Devices → rename, and accept
the entity-rename prompt) turns `reolink_trackmix_poe_person_3` into
`front_garden_person` and makes this mistake much harder.

**A camera is triggering but nothing appears in its history** — this is
usually working as intended: the timeline card and alert history only show
*archived* alerts, and an alert is archived only if its score is at or above
**Minimum score to log** (and within the log time window, if set). A camera
seeing only low-suspicion motion analyses every event but archives none. Since
2.10.0 you can see those sub-threshold analyses (and any failures) in the
camera **device's Logbook / Activity** timeline — "Analysed (score 1) — below
the log threshold, not logged" — with a **Record analyses to the logbook**
toggle in *Alerts & history* to turn it off. If you *expected* higher scores,
check Settings → System → Logs for `ai_camera_centre`: a failing AI provider
(e.g. a Google Generative AI `503`) is scored as low/benign, so a provider
outage looks like a run of quiet events.

**A camera doesn't react to motion** — turn on debug logging and trigger it;
every step of the trigger path reports what it did:

```yaml
logger:
  logs:
    custom_components.ai_camera_centre: debug
```

Then check Settings → System → Logs for that camera. You'll see one of:
`changed off -> on, starting analysis` (the trigger fired — look further down
the pipeline); `re-asserted 'on' (no off->on edge)` (the source integration
never cleared the sensor to `off`, so there was no edge to fire on);
`analysis paused, skipping` (the camera's **Analysis** switch is off);
`motion ignored by processing rule, skipping` (the presence / alarm / time
gate blocked it — check the camera's **Motion processing** section);
`within cooldown, skipping`; or **nothing at all**, which means the configured
motion entity never fired and the id is likely stale (see above).

**Notifications don't arrive** — verify the alert target's minimum score
isn't filtering the alert out, and that its camera filter (if any) includes
the camera. Each delivery failure is logged.

**No integration icon** — the icon ships inside the integration
(`custom_components/ai_camera_centre/brand/`) and is picked up
automatically on Home Assistant **2026.3 or newer**; older versions show
the default placeholder. If you're on 2026.3+ and still see the
placeholder, hard-refresh the browser / reset the companion app's
frontend cache. Details in [docs/BRANDING.md](docs/BRANDING.md).

*Known issue in HACS* https://github.com/hacs/integration/issues/5171


## Roadmap

Shipped and planned features are tracked in [TODO.md](TODO.md); a
version-by-version history is in [CHANGELOG.md](CHANGELOG.md).
