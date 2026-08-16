# Changelog

All notable changes to AI Camera Centre. Versions follow the
`custom_components/ai_camera_centre/manifest.json` `version`.

## [2.12.0]

### Added
- **Motion-processing rules now support AND / OR / groups.** The old gate was a
  single presence **AND** alarm **AND** time test. You can now define up to
  three **rule groups** (house-wide and per-camera): a camera processes motion
  when **any** enabled rule matches (OR), and a rule matches when **all** of its
  conditions hold (AND). This is disjunctive normal form, so combinations that
  were impossible before now work, e.g. *"process when nobody's home **or** at
  night, **or** when someone's home but **not** between 08:00–09:00"*.
- **"Except between two times" time condition.** A negated window
  (`not_between`), so a rule can exclude a quiet hour rather than only include
  one.
- **Choose which people count for presence.** A new *People to track for
  presence* setting takes specific `person` and/or `device_tracker` entities.
  Leave it blank to keep the previous behaviour (every `person` entity counts as
  someone home).

### Changed
- Existing configurations are read unchanged: a saved single gate is treated as
  a single rule, so upgrades keep their current behaviour until you edit the
  rules. Saving the settings migrates the stored shape to the new rule list.

## [2.11.0]

### Fixed
- **A degraded AI response no longer scores as "benign".** When a response was
  missing its score (a blocked, truncated or errored reply), the score silently
  defaulted to 1 — manufacturing a fake "all clear" and, during a provider
  outage, hiding a genuine threat. A missing or non-numeric score is now treated
  as a **failed analysis** (counted and surfaced) rather than a real verdict.
- **A transient provider error no longer degrades the whole session.** A single
  temporary failure of the structured-output call (503 / overloaded / rate
  limit / timeout) used to latch the pipeline into the weaker text parser until
  the next restart. Transient errors now fail just that event and retry
  structured output next time; only a genuine "structure unsupported" error
  falls back for the session.

### Added
- **Per-camera "Analysis failures" statistics sensor.** A new
  `sensor.<camera>_analysis_failures` counts failed analyses as a
  `total_increasing` counter, so Home Assistant keeps long-term statistics and
  the failure rate can be charted per hour/day/week/month from the History /
  Statistics UI — a direct read on how often, and when, events are going
  unassessed (e.g. during an AI-provider outage). The count persists across
  restarts. Failures also appear in the logbook (2.10.0) and fire the
  `ai_camera_centre_analysis_failed` dispatcher signal.

## [2.10.0]

### Added
- **Analysis activity in the logbook.** Only *archived* alerts appeared
  anywhere in the UI, so a camera that was triggering and analysing normally
  but scoring below the log threshold looked completely dead — the
  trigger → analysis → "below threshold, not logged" trace lived only in the
  debug log. Each analysis outcome is now written to the camera device's
  Home Assistant **logbook** (its Activity timeline): sub-threshold results
  ("Analysed (score 1) — below the log threshold (min 2), not logged"),
  "no significant motion", logged alerts, and **failures** ("Analysis failed:
  …"), so an outage or a flaky AI provider is visible instead of silent. A new
  **Record analyses to the logbook** toggle (Alerts & history, on by default)
  turns it off for anyone who finds it noisy.

## [2.9.0]

### Added
- **Add known people directly from the People card.** The card now has an
  **+ Add person** button with name and description fields, so a person can be
  created in the same place their photos are managed. Previously the only route
  was Settings → Devices & Services → AI Camera Centre → *Add known visitor*,
  then back to a dashboard to upload the photos — which was not discoverable
  from the card at all. Backed by a new admin-only
  `ai_camera_centre/add_visitor` websocket command that creates the same
  `known_visitor` subentry the config flow does, so both routes are equivalent
  and names still de-duplicate.

### Fixed
- **Websocket handlers failed during a config-entry reload.** Adding or editing
  a subentry reloads the entry, which clears the cached runtime data those
  handlers read the config entry from. Anything arriving in that window failed:
  adding two people in quick succession returned "integration not ready", and
  the card's refresh straight after an add listed no people at all. Handlers
  that only need the config entry now read it from the config-entry registry,
  which survives the reload, and the visitor list degrades to omitting photos
  rather than returning nothing while the store is rebuilding.

## [2.8.3]

### Fixed
- **The bundled card was pinned to the version you first installed.** The
  Lovelace resource is registered as
  `/ai_camera_centre/ai-camera-centre-card.js?v=<version>`, where the query is
  the cache-buster for a file served with long-lived cache headers. Auto-
  registration only ran when no resource existed yet: on every later upgrade it
  found the URL, ignored the query and returned, so dashboards kept requesting
  the *original* `?v=` and browsers kept serving that cached JS forever. Anyone
  who installed before 2.6.0 therefore never received the **AI Camera Centre
  People** card — it was missing from the card picker, and adding it by hand
  failed because the element was never defined. The resource URL is now updated
  to the running version on upgrade, busting the cache.
  - If you hit this, the fix applies on the next restart; a browser hard-refresh
    (or *Reset frontend cache* in the companion app) may still be needed once.

## [2.8.2]

### Added
- **Warning when a camera's motion trigger belongs to a different device.**
  Cameras of the same model share a device name, so Home Assistant
  disambiguates their entity ids with numeric suffixes (`..._motion_2`,
  `..._person_3`) — and picking the wrong one is silent: every entity
  resolves, nothing errors, and the camera only ever wakes for whatever the
  mis-picked sensor reports (e.g. subscribed to *vehicle* and *animal* but not
  *motion* or *person*, so it never fires for a person). Setup now logs an
  advisory warning naming the trigger and the device it actually belongs to.
  Cross-device triggers stay supported (a separate PIR covering the same view)
  — the warning just makes the mismatch visible.

### Documentation
- README: document that reference photos for known people are managed from the
  bundled **AI Camera Centre People** dashboard card, not from the integration
  settings — with the steps to add it.

## [2.8.1]

### Fixed
- **Analysis switch could silently pause a camera forever.** The per-camera
  *Analysis* switch restores its state on startup, but any restored value that
  wasn't literally `"on"` was treated as off — including `unavailable` and
  `unknown`, which is what gets saved when the config entry is reloaded (every
  settings/camera edit) or Home Assistant shuts down uncleanly. The affected
  camera's pipeline was then left paused: motion triggers were dropped before
  any snapshot, AI call or notification, with only a debug-level line to show
  for it, while *Analyze now* kept working (it bypasses the pause). Only a
  genuine `on`/`off` restore is honoured now; anything else falls back to the
  default (on).

### Added
- **Debug logging on every motion-trigger path.** `handle_motion_event`
  previously returned silently, so a camera that never fired was
  indistinguishable in the log from one that was never subscribed. Each exit
  now logs at debug, naming the triggering entity and its state transition —
  including the "re-asserted `on` without an intervening `off`" case, where a
  source integration that misses the clear leaves no edge to trigger on.

## [2.8.0]

### Added
- **Warning when a motion trigger entity is missing** — on setup the
  integration now checks each camera's configured motion-trigger entity ids
  against Home Assistant and logs a clear warning naming any that don't exist
  (checking both the live state machine and the entity registry, so a
  source integration that is merely slow to load isn't misreported). A stale
  or renamed trigger id — e.g. after the source camera integration is updated
  or a device is renamed — no longer fails silently: previously the source
  integration would show motion while this integration never ran, with nothing
  in the log to explain it.

### Changed
- **Grouped, better-labelled settings UI** — the global settings form and the
  per-camera form are now organised into collapsible sections with headings,
  section descriptions and per-field help text:
  - Global settings: *Capture & analysis*, *Alerts & history*,
    *Alarm & Alarmo*, *Motion processing (house default)* and
    *AI response style*.
  - Camera form: the essentials (name, stream, motion triggers, scene context)
    stay up top, with the motion-processing policy and its custom gate moved
    into a collapsed *Motion processing* section.
  - Alert-target and known-visitor forms gained clearer field titles and help
    text. No settings changed meaning and nothing needs reconfiguring — stored
    options and camera data keep the same flat shape.

## [2.7.0]

### Added
- **Live card updates** — the timeline card now receives new alerts over a
  websocket subscription and shows them instantly, instead of polling every
  five minutes.

### Changed
- **Signed, expiring URLs for alert images** — archived alert images are no
  longer served on an unauthenticated static path. They now go through an
  authenticated endpoint and are handed out as **signed URLs that expire with
  the retention window**, tied to Home Assistant's content-user token. The
  card `<img>`, the mobile notification, and the `ai_camera_centre_alert`
  event image all use signed URLs, so they still load without a bearer token,
  but the links can no longer be fetched by anyone who happens to obtain them
  after they expire. Burst snapshots and known-visitor photos keep the
  existing capability-URL scheme.
  - **Breaking:** any dashboard or automation that hard-coded a raw
    `/ai_camera_centre/images/…` URL must instead use the signed URL from the
    card feed or the `ai_camera_centre_alert` event. Unsigned requests to that
    path now return 401.

## [2.6.2]

### Changed
- Quality/hardening release. Added an automated test suite
  (`pytest-homeassistant-custom-component`) covering the alert store, the
  motion-ignore processing gate, the config/options flows, and the
  known-photo upload endpoint plus the `visitors` / `delete_visitor_photo`
  websocket commands — the last of which exercise the live HTTP/websocket
  stack (view registration, auth, and the 2.6.1 upload-error hardening). A
  `pytest` job now runs the suite in CI (`validate.yml`, Python 3.13) on
  every push and pull request. No runtime behaviour changes.

## [2.6.1]

### Security
- The known-photo upload endpoint no longer echoes internal exception detail
  in its HTTP error response; failures return a generic message and the detail
  is logged server-side instead (CodeQL: information exposure through an
  exception).
- The `validate` GitHub workflow now declares an explicit least-privilege
  `permissions: contents: read` (CodeQL: workflow does not contain
  permissions).

## [2.6.0]

### Added
- **Motion-ignore processing rules** — skip AI analysis entirely (no snapshot
  burst, no AI call, no notification) based on three factors that must all
  agree: **presence** (process always / only when nobody home / only when
  someone home), **alarm state** (always / only armed / only disarmed) and
  **time** (any time / between two times / daytime only / nighttime only,
  where day/night follows a sun entity, default `sun.sun`). Configured as a
  house-wide default in Settings, with a per-camera **motion processing
  policy** that either follows the house or sets its own rules. The manual
  *Analyze now* button and the `analyze` service always bypass these rules.
  This is separate from the existing notify conditions (who gets pushed) and
  log window (what gets archived); it gates whether the pipeline runs at all,
  to save AI cost.
- **Reference photos for known people** — upload one or more photos per known
  visitor via the new **AI Camera Centre People** card
  (`custom:ai-camera-centre-people-card`). Photos are attached to the AI
  prompt so the model can visually recognise household members and regulars
  (in addition to the existing text description) and record the matched name.
  Uploads go through an authenticated, admin-only endpoint and are normalised
  to a bounded JPEG; they are stored under
  `<config>/ai_camera_centre/known/<visitor_id>/` and are not age-pruned.
- **AI response style / personality** — an optional global free-text override
  (e.g. "in the style of Samuel L. Jackson") that shapes the wording of the
  short and detailed alert text. It is explicitly constrained to wording only
  and never changes the suspicion score or any factual field.

## [2.5.1]

### Security
- Burst snapshots used fixed, predictable filenames on an unauthenticated
  static path, allowing anyone who could reach the Home Assistant port to
  poll near-live camera frames without logging in. Snapshot and archived
  image filenames now carry a cryptographically random token (capability
  URLs), and each run's snapshots replace the previous run's.
- `log_alert`'s `image_path` is now restricted to the integration's storage
  directory or `allowlist_external_dirs`, so arbitrary host files can no
  longer be copied into the publicly served images directory.

### Added
- A real [SECURITY.md](SECURITY.md): private vulnerability reporting,
  supported versions, and the integration's security model.

## [2.5.0]

### Added
- **Known visitors** — add household members and regulars (name +
  description) as a new *Known visitor* entry on the integration page. Their
  descriptions are added to every camera's AI prompt so recognised people
  are scored low; the recognised name is stored on the alert (`known_person`),
  the `ai_camera_centre_alert` event, and the card.
- **Repeat-visitor context** — a *Recent-activity context window* setting
  (default 15 min, 0 disables). The camera's recent alerts are summarised
  into the prompt so the AI can flag the same subject returning or loitering
  and raise the score.

## [2.4.0]

### Added
- **Card lightbox** — tap the expanded alert image for a full-screen view.
- **Notification channels** — alerts scoring 7+ use a separate
  high-importance Android channel (can ring through Do Not Disturb) and the
  iOS time-sensitive level; a **Sound alarm** action button (when an alarm
  panel is set) trips Alarmo.
- **Camera area auto-inherit** — camera devices are placed in their source
  camera entity's area on setup (only when unset).
- **`ai_camera_centre_alert` event** — fired for every alert for use in
  automations.
- **Diagnostics** — downloadable config-entry diagnostics.
- **Structured AI output** — `ai_task` is called with a schema; falls back
  to prompt-and-parse JSON where structured output isn't supported.
- **CI** — hassfest + HACS validation on push/PR.

## [2.3.1]

### Changed
- Each camera is now a config **subentry** and its own **device** with six
  entities (24h count, last score, recent-alert binary sensor, latest-alert
  image, analysis switch, analyze button). Cameras and alert targets are
  added from the integration page.
- Alert targets show a friendly name.

### Fixed
- `DeviceInfo` import path (broke platform setup on 2.3.0).

## [2.2.0]

### Added
- Per-target **notify condition** (always / away / armed / away-or-armed).
- Optional **Alarmo** trigger on high-risk alerts while armed.
- **Selective logging** — minimum score and time-window filters.

## [2.1.x]

### Added
- **Alert targets** and multiple **motion triggers** per camera.
- Brand images bundled in the integration (HA 2026.3 brands proxy).

## [2.0.0]

### Changed
- Renamed from *Alert History* to **AI Camera Centre** with a self-contained
  analysis pipeline (snapshot burst → AI → log → notify) and bundled
  timeline card.
