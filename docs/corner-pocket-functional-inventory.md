# Corner Pocket functional inventory and acceptance checklist

## Evidence and scope

Primary source: [`../design/corner-pocket/Corner Pocket Ops standalone-src.dc.html`](../design/corner-pocket/Corner%20Pocket%20Ops%20standalone-src.dc.html), 2,144 lines / 141,756 bytes. Read in full through `read` tool chunks, including rereading truncated boundaries. Coverage: lead agent 1–434 and 1501–2144; delegated readers 435–850 and 851–1500. Line references below refer to that source, not the new implementation. This is an implementation specification, **not a claim these checks currently pass**.

The standalone document is a DC/React prototype: custom `x-dc`, `sc-if`, `sc-for`, bindings, editor metadata and `./support.js`. Six actual application screens exist: **Floor, Set up, Matches, Stream (internal `vision`), Regulars (`players`), Back room (`status`)**. A placeholder count of five does not limit the navigation. Dictionary strings and unbound methods are not evidence of reachable screens.

Legend: **Intended** = meaningful product behavior to implement using real state/services; **Prototype** = actual source behavior, including incomplete or unsafe behavior; **Deferred** = service/roadmap capability described but not implemented. Never disguise sample data, placeholders or simulations as connected production behavior.

## 1. Global shell and preferences (1–135, 713, 1000–1050, 1791–1798, 1874–1945)

- [ ] Render all six tabs and preserve the same tournament, selection, timer and preferences across navigation. Navigation metadata shows actual entry/player/open-match counts.
- [ ] Support complete English and Simplified Chinese copy, including validation, empty states, status chips, accessible control names, toasts and external-service notices. EN/中 buttons update document language and all displayed strings.
- [ ] Support dark/light themes with selected-state buttons. Original defaults: EN and dark; configurable editor overrides. Tokens/fonts: Zilla Slab, Barlow, DM Mono, Noto Sans SC and Noto Serif SC; Google Fonts CSS/fonts are external dependencies, so fallback fonts must work offline.
- [ ] Keep the header sticky. Every non-Floor screen includes the same shot clock controls and a current-score button returning to Floor.
- [ ] Provide keyboard-focus states, accessible +/- labels, labeled form inputs, canvas/iframe accessible names, reduced-motion support, horizontal bracket scrolling, responsive layouts and `role=status`/`aria-live=polite` feedback.
- [ ] Persist preferences explicitly. Prototype theme/lang and business state only live in memory; “v{v} saved locally” is not persistence.
- [ ] Never use hardcoded “Live”, “Table 3”, event names or frame counts as health/status evidence.

Editor-only configuration (713): clothColor default `#1d5c44`, options `#1d5c44/#1f4a70/#6a2130/#2f3a3f`; lampGlow default .22, 0–.5 step .02; showDiamonds true; raceTo default7, range1–11; shotClock default45, range10–120 seconds; startLang en/zh; startTheme dark/light. These were not six extra settings screens.

## 2. Floor: scorekeeping, clock, table queue (137–309, 1092–1103, 1132–1158, 1200–1382, 1732–1765, 1903–1983)

### Scoreboard and match focus

- [ ] Show actual focused match id, assigned table, state, race, both entrant labels, rating/member/guest metadata, score and leading/trailing/level styling. Doubles compact labels use surnames joined `/`; full labels retain both complete names.
- [ ] Handle no match/open slots without pretending a match is live. Pending participants must not be scoreable.
- [ ] Race options are 1,3,5,7,9,11. Multi-rack matches have +/- and one pip per target rack. Single-frame mode has an explicit winner action instead of numeric controls.
- [ ] Clamp scores to valid nonnegative integers and race maximum; reject ties as completed results and two simultaneous race winners. Require an actual scheduled/live eligible match and present participants before score mutation.
- [ ] Explicit result signing persists winner, immutable result/audit entry and bracket advancement atomically. Corrections require a deliberate supported correction/undo policy, not silent overwrites.
- [ ] Clear-score action resets only an editable match and does not corrupt completed results/downstream participants.
- [ ] Display delayed/away banner with names and “Here now” actions. Clear each absent participant independently.
- [ ] Summary tiles derive matches completed/total, next ready pair, registered entrants and guests from persisted state.
- [ ] Floor table visualization must be a real observation/review or explicitly unavailable/sample; never render synthetic balls as a real live table.

**Prototype differences:** focus can select any noncomplete match including pending/scheduled/delayed (1139–1146). `adjust` auto-signs at race, resets clock and propagates; lower edits can mark a match live even with no free table (1212–1235). `signFocus` accepts any unequal score, even below race or absent (1237–1250). `clearScore` can leave completed state/downstream winners inconsistent (1252–1259). Real implementation must not copy those integrity bugs. Source has one focused scorecard, not a fully designed multi-table focus picker; additional tables need an explicit selection mechanism.

### Shot clock

- [ ] Offer 20/30/45/60 seconds and shared controls on Floor/setup/header. Use wall-clock deadlines rather than counting interval ticks; display ceil seconds `m:ss`, progress, amber/red thresholds and final-five-second emphasis.
- [ ] Start/pause/resume/reset behavior is explicit. At zero stop and notify without silently assigning a foul or score.
- [ ] Hold clock during absent/delayed matches; score change/completion/reset behavior is consistent and tested.
- [ ] State survives tab changes. State its scope accurately: device-local persisted deadline, or implement server-synchronized shared timer. Do not imply synchronization unless present.
- [ ] Cancel timers on teardown; refreshing/backgrounding must not create extra time.

Prototype: start blocks absent focus; running Start pauses; Reset uses `restartClock` and starts full-duration countdown (1357–1371), unlike passive `resetClock`; shot duration change stops/reset/logs. Countdown interval180ms; no auto foul, auto shot detection or per-shot automatic start. Default45 seconds may differ from rendered options.

### Queue / absence / scheduling

- [ ] List unsatisfied matches with round, both entrants, assigned/unassigned table and pending/ready/live/delayed/completed status. Empty queue is intentional.
- [ ] “Not here” marks selected side absent, delays match, holds clock and records audit. “Here now” removes absence; when all return, make match schedulable rather than inventing an occupied table.
- [ ] “Send to table” requires both entrants present and an available valid table; prevent collisions, out-of-range tables and restarting completed matches.
- [ ] Track simultaneous table usage correctly; choose lowest free or explicitly selected table. Table release on delay/completion must be coherent.
- [ ] Explicit manual forfeit, if added to replace the acknowledged missing forfeit policy, requires confirmation and recorded reason/outcome.

Prototype only counts live tables as occupied, retains delayed table ids, can resume to live on a now-occupied table and lacks complete-status guards (1092–1099, 1300–1334). Queue excludes focus; status sorting lacks a defined live ordering. Do not reproduce.

## 3. Set up: event and registration (311–418, 1384–1459, 1984–2033)

- [ ] Editable event name, singles/doubles format, race and shot duration feed the same event shown elsewhere.
- [ ] Define and enforce a safe lock boundary: registration/rules may change before draw starts; after start use explicit archive/new-event or a supported audited edit. Prototype says changes apply live, and “Rack the night” clears the sheet, but does not safely repair results.
- [ ] Member registration selects an existing player and excludes already registered member ids. Guest registration accepts a trimmed required name without auto-creating a permanent roster entry.
- [ ] Prevent duplicate members/names, including pending doubles partners; define case-insensitive duplicate policy and validate server-side.
- [ ] Singles form one-member entries. Doubles require exactly two distinct participants, show waiting-for-partner state if using sequential entry, and create mixed guest/member teams correctly.
- [ ] List numbered entrants with full names, metadata, member/guest badges, registered-team count and distinct guest-person count.
- [ ] Remove entries only when safe; do not retain invalid bracket sides, winners, scores, absences or clock focus.
- [ ] Generate single-elimination bracket in sign-up order; require at least two entries, allocate next power of two and resolve byes in every round, including empty trailing branches and odd counts.
- [ ] Propagate winner to exact next-round slot, make fully populated matches schedulable, mark tournament finished at final result, and never advance twice.
- [ ] Preserve history across new events and confirm destructive replacement. Decide whether first match is automatically put on table or requires explicit scheduling; source automatically starts first ready match on table1.

Prototype: guest duplicate check is exact case-sensitive name; first doubles entrant stored only in `pendingPerson`; changing format clears pending but does not regroup existing entrants; removing entry nulls every matching side without repair. `rackNight` replaces matches, preserves old timeline despite “clears sheet” copy, and only handles first-round left-only byes. All state is mutable in-memory, no rollback/version conflict handling (1384–1459).

## 4. Matches: result form, bracket, rankings and log (420–529, 1261–1298, 1473, 1800–1852, 2038–2071)

- [ ] Summary card shows event, format, race, signed/total, live and delayed counts.
- [ ] Scorekeeper form chooses match and a participant winner, accepts winner-first `n-m` score if reproducing original input, and gives visible success/error guidance. If using side-A/side-B numeric inputs instead, name the sides clearly and derive winner rather than trusting an independent contradictory selector.
- [ ] Validate match eligibility, participant membership, score bounds, unequal race-winning score, presence and immutable completion on server. Save and sign semantics must be clear.
- [ ] Bracket groups rounds with final/semis/quarters labels, complete/total metadata and id/table/status/name/score cards. Pending sides show waiting, winners highlighted, live cards distinct.
- [ ] House ladder sorts real players by rating, displays rank/status/rating and top-three distinction. Do not imply seeded ratings were computed by a rating engine.
- [ ] Rail notes/timeline renders chronologically meaningful persisted events with timestamps and localized descriptions (registration/removal, draw, absence/return, table assignment, scoring/signing, clock or operator notes as applicable).
- [ ] “Log a rail check” creates an operator attestation/note, not evidence that a sensor inspected the cloth.
- [ ] Remove or explicitly segregate “Run out a match” as a demo-only action. It must never fabricate a production match result.
- [ ] Archive/history is inspectable enough to retrieve completed event results, not just a count.

Prototype `saveCard` only regex-validates digits-dash-digits, accepts arbitrary winner ids/ties/impossible scores, overwrites complete cards and does not stop clock. `advance` randomly selects winner and losing score and marks complete. These are simulations/bugs, not intended validation (1261–1298).

## 5. Stream and review (531–600, 1504–1517, 1768–1776, 2067–2086)

### Actual rendered stream screen

- [ ] Display Twitch player, external channel link, optional chat, current tournament match/score/race/next-up summary, channel/source form and table-view section.
- [ ] Use `https://player.twitch.tv/?channel=...&parent=<actual hostname>&muted=true`, with fullscreen permission. Chat uses `https://www.twitch.tv/embed/<channel>/chat?parent=<hostname>` and dark styling when appropriate.
- [ ] Validate canonical Twitch HTTPS channel/video URLs. Video replay must be labeled VOD/recorded, not live. An embed alone cannot verify live status, camera connectivity or frame freshness.
- [ ] Channel switching sanitizes/validates input, persists configured source if intended, updates player/chat/link consistently and supports empty/unavailable/error states.
- [ ] Chat toggle hides/shows the real chat; handles VOD (no false live chat) and external Twitch cookie/embed restrictions.
- [ ] Show current event name dynamically, not hardcoded `Friday 8-Ball Open · Table 3`.
- [ ] “Refresh” table view must fetch/analyze a real available frame, or explain unavailable analysis. Source `runFrame` instead advances synthetic frame counter.
- [ ] Keep VOD review/calibration/inference independent of live stream playback. Existing `/app.html` workbench may be embedded/linked explicitly as **local VOD**, not presented as a Twitch frame extractor.

Prototype real external integration: Twitch player/chat/link only. Default channel `examplechannel`. Channel submit strips twitch.tv prefix and all non-alphanumeric/underscore characters; this incorrectly converts unsupported paths into channel identifiers. Source registry `addSource` only checks `new URL`, prepends local metadata and announces success; it never connects/captures/decodes anything. Default registry URL `https://www.twitch.tv/examplechannel/videos` is a channel videos listing, not a specific VOD. No fetch, detector or streaming ingestion connects to it.

### Dictionary-only / latent vision functionality (821–841, 924–950, 1475–1502)

These strings and handlers exist but are **not rendered as a separate reachable panel** in the final template. Inventory them for full product planning without claiming existing UI:

- [ ] Source modes: recorded session (`offline`), phone tripod (`realtime`), local clip (`file`); URL/type, register source and ready/error feedback. Production requires actual camera/file/stream ingestion, supported-protocol policy and authorization, not an arbitrary-URL success toast.
- [ ] Observation controls: read latest, read six, looping feed pause/play, busy state, processed-frame count and JSON contract show/hide.
- [ ] Layers: balls, paths, people, events, heat. Defaults balls/paths/people on, events/heat off.
- [ ] Observation contract: frame/timecode, normalized table confidence, ball id/label/x/y/z/confidence/velocity, people id/role/confidence/pose, event type/confidence/ball.
- [ ] Pipeline status: Feed; Frame grab; Table calibration; Ball find; Track; Shot events. Report actual readiness; dictionary `ready` does not prove implemented inference.
- [ ] Trust labels “Runs local / Feed attached / Contract v0.1 / Model pending” must be derived or explicitly annotated as prototype text.

## 6. Vision simulation and renderer (760–761, 1106–1129, 1475–1502, 1519–1730)

**All observation data is synthetic.** `obs(frame)` animates fixed base balls using sine/cosine, not video. Frame timecode assumes30fps; table confidence .91. Cue moves .035/.025, others .01/.008; normalized clamps x .06–.94, y .08–.92; cue z .015 for frame%24<5. Confidence formula .86 + (i%4)*.025 − (frame%7)*.003. Velocity equals positional displacement ×.42. People are person-a/shooter/.9/down and person-b/opponent/.84/standing. Every fifth frame emits `shot candidate` confidence .74, otherwise `tracking update` .92. None is detection, tracking, pot/foul judgment or human recognition.

- `runFrame`: increment frame and regenerate one sample.
- `runBatch`: wait220ms and increment frame by6, generate only final sample; not six actual reads.
- `toggleLoop`: regenerate sample every900ms; no stream/video playback.
- Canvas: compact Floor980×440 and Stream1180×640. Procedural wood rails, felt, head line, foot spot, six pockets, optional diamonds/lamp. Balls use gradients, numeric labels, solids/stripes; cue no number. Positions normalized to bed; z visually offsets y. Paths are dashed velocity projection; compact view always draws paths/balls independent of layer switches.
- Noncompact heat is one fixed radial glow, people are fixed decorative rings, event badge displays first synthetic event. It is 2.5D illustration, not calibrated reconstruction.
- `draw()` repaints on component updates and resize; theme changes recolor scene. Lifecycle clears loop/clock/toast but batch timeout is not retained/cancelled.

Acceptance: real normalized observations must come from documented analysis output, preserve source/frame provenance, show stale/loading/error/empty states and confidence honestly. Detected people need a privacy-safe role policy. Never automatically score a pot/foul from these samples.

## 7. Regulars / player profiles (602–673, 1461–1470, 1847–1859, 2088–2125)

- [ ] Show active-member count, average rating, logged-match count, searchable/filterable rating-ranked roster and selectable player profile. Empty roster/filter state must not divide by zero or render NaN.
- [ ] Search name/status case-insensitively; filter Everyone/Active/Visitor/Prospect (production may add Inactive). Selection remains coherent when filter excludes previously selected player.
- [ ] Row shows rank, name, status, join date, rating. Profile shows status, recorded matches, join date and six original metric slots: rating, win rate, break-and-run%, safety play, attendance%, average innings.
- [ ] Compute metrics only from actual records or label unavailable/not measured. Source seeded metrics are not updated by signing results; counts may double-count player participations versus unique matches.
- [ ] Guest list derives distinct current-event guests. “Add to regulars” creates a permanent profile and relinks matching current-event guest membership without duplicating a name or losing identity/history.
- [ ] Guest conversion source defaults: rating520, Prospect, today, all metrics0. Win rate must display unavailable/0 safely rather than 0/0 NaN.
- [ ] Production player CRUD/status/notes requires persisted backend actions and validation; original template only offers roster selection and guest conversion, not full create/edit/delete forms.

Prototype promotion matches exact name; if a player with same name exists it silently returns without relinking. IDs based on array length can collide after deletion. Permanent ids and explicit outcomes are required.

## 8. Back room, readiness and dependencies (675–703, 851–854, 961–963, 988–998, 2126–2132)

- [ ] Render actual current/target/gap/priority readiness, distinguish implemented local persistence from absent services, and never use static roadmap labels as live monitoring.
- [ ] Preserve original nine roadmap areas, updated truthfully: house ledger server write P1; online signups P1; scotch-doubles turn order P2; result undo trail P1; trained ball detector P1; safe people detector P2; calibrated replay beyond2.5D P1; per-shot auto clock start P2; automatic reseeding/forfeit timer P1.
- [ ] Manual operator notes/rail-check attestations persist and can be audited. No fabricated hardware checks.
- [ ] Prototype footer explicitly says: “Local prototype. Wire the house ledger and vision service before the room runs on it.” Preserve equivalent honesty until those dependencies are real.

## 9. Exact sample fixtures (717–761, 1000–1018)

Fixtures are for explicit demo/test data only. Do not silently seed production with fake people, scores, metrics or events.

| ID | Name | Rating | Status | Wins | Losses | Break/run | Safety | Attendance | Innings |
|---|---|---:|---|---:|---:|---:|---:|---:|---:|
| p1 | Maya Chen | 681 | Active | 42 | 12 | 18 | 76 | 94 | 5.2 |
| p2 | Owen Park | 664 | Active | 38 | 17 | 15 | 71 | 90 | 5.9 |
| p3 | Noah Singh | 632 | Active | 31 | 19 | 11 | 69 | 88 | 6.4 |
| p4 | Iris Novak | 621 | Active | 28 | 21 | 9 | 74 | 96 | 6.8 |
| p5 | Leo Martin | 604 | Visitor | 23 | 23 | 7 | 62 | 72 | 7.4 |
| p6 | Ava Brooks | 598 | Active | 24 | 25 | 8 | 66 | 84 | 7.0 |
| p7 | Mateo Rossi | 577 | Active | 19 | 26 | 5 | 61 | 79 | 7.9 |
| p8 | Zoe Kim | 552 | Prospect | 13 | 18 | 3 | 57 | 68 | 8.6 |

All join dates `2026-01-14`. Tournament version3, singles, tables1, name empty, seq8. Entries e1–e6 are p1–p6; e7 Ray Ortiz and e8 Jun Watanabe are guests.

| Match | Round | Table | Sides | Score | Status / winner |
|---|---:|---:|---|---|---|
| m1 | 1 | 1 | e1/e2 | 7–4 | complete/e1 |
| m2 | 1 | 2 | e3/e4 | 5–7 | complete/e4 |
| m3 | 1 | 3 | e5/e6 | 4–3 | live |
| m4 | 1 | — | e7/e8 | 0–0 | delayed, absent e8 |
| m5 | 2 | — | e1/e4 | 0–0 | scheduled |
| m6 | 2 | — | unresolved | 0–0 | pending |
| m7 | 3 | — | unresolved | 0–0 | pending |

Historical timeline:17:40 nightRacked n4;18:42 Maya ran out7–4;18:58 Iris ran out7–5;19:07 Jun delayed M4. Seed inconsistency: tables1 while matches use tables2/3. Match-form winnerId `p2` does not belong to focused m3 entrant ids. Race default7, clock45, focus m3, registration member p7, player selection p1, frame0, layers balls/paths/people on, looping/batch/JSON off, Twitch `examplechannel`, chat on.

Base balls (id / label / normalized x,y), line760: cue / empty / .28,.55; 1 / 1 / .66,.47; 2 / 2 / .70,.51; 3 / 3 / .74,.45; 4 / 4 / .77,.55; 5 / 5 / .62,.61; 8 / 8 / .72,.58; 11 / 11 / .82,.36; 14 / 14 / .58,.38. Color map (761): cue `#f4efe4`;1/9 `#e3b52a`;2/10 `#23527c`;3/11 `#b23a2f`;4/12 `#5d4083`;5/13 `#cf7326`;6/14 `#1f6b48`;7/15 `#7b2f2a`;8 `#1b1614`. These are illustration fixtures, not calibrated observations.

## 10. Cross-cutting real implementation acceptance

- [ ] Durable store for players, event settings, entrants/teams, matches, absence, sources, notes/history and results; load failures do not silently replace data with fixtures.
- [ ] Server-authoritative validation, unique ids, atomic result+advancement, revision checks and explicit409 conflict recovery. Do not retry stale writes silently.
- [ ] No table collisions, duplicate participant slots, completed-match mutation, invalid promotion, phantom scores or unresolved legal byes. Test 2/3/5/6/7/8 entries, singles/doubles, absence/return, all tables full and final completion.
- [ ] Browser refresh/restart retains persisted operations; timer scope and offline/network status are honest.
- [ ] Escape user-controlled names, notes, URLs and API errors; validate external source origin/path/protocol on server. Do not SSRF arbitrary pasted URLs.
- [ ] Externally connected Twitch playback requires network access and valid `parent`; live frame ingestion/decoding/calibration/detector/tracker/event service are separate dependencies. Existing local VOD review cannot be relabeled live.
- [ ] Production deployment needs explicit operator access/concurrency policy, backups and audit/correction rules. Authentication/authorization/payment/booking interfaces are not implemented or designed in this prototype; do not invent them as completed scope.
- [ ] Test all controls in EN/中文 and dark/light, no-data/zero-match/zero-player states, invalid inputs,409, server unavailable, stream absent and narrow viewport.

### Known source discrepancies not to reproduce

Duplicate `noMatch` keys: English849 overwrites819; Chinese960 overwrites930, so stream-empty text becomes roster-search text. Seed player winner ids mismatch entrant ids. Rating statistics are fixed, not calculated from match outcomes. “Locally saved” is an in-memory counter. “Read six” generates one final sample. “Feed attached/ready” is not a connection. “Run out” is random. Bracket regeneration and removals are unsafe. “Live” Twitch badge is unconditional. Each should become real behavior, an explicitly labeled unavailable capability, or a clearly segregated demo—not a polished lie.
