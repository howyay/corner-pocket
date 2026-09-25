# Tiered queue — what was served and what the rail shows (round 3)

Date: 2026-09-23 · worker: census/candidate round (PM directive, owner decision)
Queue artifact: `out/scan30/events.json` (regenerable; `out/` is gitignored)
Report artifact: `out/scan30/eval_regen.json`, sidecar `out/scan30/gate_report.json`
Commits under test: `1817c7c` (queue), `cc7ca24` (rail) — census rounds: `d2ff4ee`, `1b64c2b`, `793ea60`

## What was written

| tier | count | meaning |
|---|---|---|
| `geometry` | 2 | the re-measured motion matches the claim's own geometry (gap ≤ 60 px) |
| `window` | 13 | a ball really moved in the window, but not the one or where the claim said (gaps 141–490 px, calibration 0.31–0.51) |
| pots | 0 | the ball census refuted every pot claim (14) or left it unconfirmed (2) |

Every event keeps the claim's own `from_mm`/`to_mm`/`ball_from`/`ball_to` exactly as
the scan wrote them, plus `tier`, `geometry_check` (claim vs measured displacement,
gap, 60 px tolerance, calibration fraction) and the gate numbers the eval measured.
The 26 rejected and 7 unconfirmed candidates stay out of the queue and in the report
artifact. The two events the queue already carried keep their ids 16 and 28, so no
recorded verdict is orphaned.

**Objection on the record** (the decision is the owner's, implemented anyway): the 13
`window`-tier events carry a geometry mismatch and, for 11 of them, a frame whose
reference quad covers 0.31–0.51 of the cloth; as a served queue their precision is
unmeasured and the previous two-event queue was stricter. The tier label is the
mitigation, not a measurement.

## Measured in the browser (fixture, read-only)

Fixture: `PYTHONPATH=. .venv/bin/python tests/serve_workbench_fixture.py` → `http://127.0.0.1:8131`,
session `census-521027f9b1ad`, viewport 1280×599, cold `LOADING` waited out.

| # | Check | Measured | Verdict |
|---|-------|----------|---------|
| 1 | Rail renders the tiered queue | `#vs-cues` present; `.vs-card` = **15**; `[data-vs-tier]` = **2 geometry, 13 window** | PASS |
| 2 | Both tiers distinguishable in one view | `out/scan30/ui/rail_both_tiers.png`: card #16 dashed `MOTION WINDOW ONLY` badge + dashed left edge, card #28 solid `GEOMETRY-VERIFIED` badge + solid green edge | PASS |
| 3 | Tier filter counts | `GEOMETRY-VERIFIED` → **2** cards; `MOTION WINDOW ONLY` → **13**; `POTS` → **0** | PASS |
| 4 | Tier survives into the inspector verdict block | `.vs-facts` contains `Confirmation tier motion window only` for the selected window-tier cue (`out/scan30/ui/inspector_window_tier.png`) | PASS |
| 5 | Pots empty state names the reason | `.vs-empty[data-vs-empty="pots-measured-none"]`: “No pot candidate in this VOD survived measurement: the ball census refuted every claim (a ball said to be potted was still on the cloth) and 2 stayed unconfirmed, so this list is empty on purpose.” (`out/scan30/ui/pots_empty_state.png`) | PASS |
| 6 | Bilingual | 中 mode badges read `几何已核` / `仅运动窗口` (`out/scan30/ui/rail_zh_tiers.png`); the pot reason and all six new copy keys exist in `zh` | PASS |
| 7 | Console | `agent-browser console --json` → `"messages":[]` = **0 errors** across load, tab switch, 2 tier filters, cue selection and 2 language switches | PASS |
| 8 | Nothing outside the fixture was written | `md5(out/corner-pocket/state.json)` = `77777777777777777777777777777777…` and `md5(out/ui-browser-fixture/out/scan30/annotations.json)` = `77777777777777777777777777777777…`, both **byte-identical** before and after | PASS |

Screenshots: `out/scan30/ui/{rail_both_tiers,rail_zh_tiers,window_tier_filter,geometry_tier_filter,inspector_window_tier,pots_empty_state}.png`.

## Suites

python `311 → 322 tests, 2 skipped` (added `tests/test_candidate_scan.py`, `tests/test_sam3_frame_audit.py`,
`tests/test_sam3_ball_cache.py` and the tier/empty-state pins); `node tests/test_app_timeline.js` **46 passed**
(44 + the two tier pins); `node --test tests/test_ops.js` **21 passed**.

## Round 4 — the queue is empty (owner decision, commit `0e61a4b`)

`out/motion_scan/vod30.summary.md` (commit `7ab1f33`) measured all 15 served events as occlusion-explained
(`occ_dense` 0.45–0.97, every event's largest changed component 9.2–58.4× one ball's area; across the VOD
0 of 55 ball-scale onsets could be a single ball, and a ball's best possible 17×17 mean of ~124 gray sits
under the 125.6 noise threshold). The owner decided to serve nothing rather than ask for reviews of events
that are provably not shots.

| Artifact | State |
|---|---|
| `out/scan30/events.json` | **0 events** (still a JSON array; the 15 removed ids were 16, 28, 1003–1052) |
| `out/scan30/events.tiered.json` | the 15-event queue kept as an artifact |
| `out/scan30/gate_report.json` | 33 not-confirmed rows kept |
| `out/scan30/eval_regen.json` | all 48 measured events kept |
| `out/scan30/annotations.json` | **untouched**, md5 `77777777777777777777777777777777` before and after |

Empty state, EN: “No shot candidate survived measurement: every served event is explained by occlusion — a
person crossing the cloth at that moment — and at 720p one ball's best possible signal sits on the detection
floor (motion measured over the whole VOD: 0 of 55 ball-scale onsets could be a single ball). The events stay
in the report artifacts, not in the queue.” 中: 「没有击球候选通过测量：已服务的每条事件都被遮挡解释——那一刻有人穿过
台面——且 720p 下单球的最强信号正好卡在检测底噪上（全片实测：55 个球尺度突变中 0 个可能来自单颗球）。这些事件保留在
报告产物里，不在队列中。」 The pots filter keeps its own sentence.

Degraded rail: the two tier filter buttons are offered only while an event carries a tier, so an empty queue
cannot present controls that can only return nothing; ALL / SHOTS / POTS / UNREVIEWED stay because each is a
way to read a reason; the reviewed counter is 0 (verdicts count only while their event is in the queue); the
scrub draws no cue marks; the inspector shows the same reason instead of an empty panel.

Measured on the fixture (`:8131`, session `empty-521027f9b1ad`): 0 cards, tier controls 0, the reason present
with marker `shots-measured-none`; the POTS filter switches the marker to `pots-measured-none`; 中 renders the
translated reason; console messages **0** across load, tab switch, filter clicks, viewport change and language
switch; `scrollWidth` = 1280 at 1280×599 and **390 at 390×844** (no horizontal overflow).
Screenshots: `out/scan30/ui/{empty_queue_1280,empty_queue_390,empty_queue_zh_1280,empty_pots_1280}.png`.
`out/corner-pocket/state.json`, `out/pid_seed.json` and `out/scan30/annotations.json` are byte-identical after.


## Round 5 — the dense-track events are served (commit `876e0a0`)

The queue went from empty (round 4) to the four events of
`out/dense-events/segment-1350-1650.after.json`: three motion events and one
pot-shaped disappearance, all machine-produced by the trained ball detector on
dense tracks (`ball@2`, 66.7 ms), copied by `src/dense_queue.py` with the
provenance and the evidence the run measured. Ids 9001-9004; `annotations.json`
md5 `77777777777777777777777777777777` unchanged.

Measured on the fixture (`:8131`, session `dense-521027f9b1ad`):

| # | Check | Measured | Verdict |
|---|-------|----------|---------|
| 1 | Cards + evidence lines | 4 cards; "24:42.3 · #9001 · 2 mm white", "#9002 · 1308 mm blue", "#9003 · 63 mm blue", pot "#9004 · left-middle (148mm) · 148 mm left-side" | PASS |
| 2 | Tier badges | 3 badges, all `window` (`MOTION WINDOW ONLY`); no `geometry` badge invented | PASS |
| 3 | Selecting plays the window | selecting #9002: `currentTime` 1580.62 s → 1579.11 s (wrapped the loop window [1579.1, 1581.1]), `paused: false`, loop counter `↻ 19 · playing`, scrub cue mark present | PASS |
| 4 | Pot candidate is an unknown candidate | POTS tab carries exactly #9004; inspector: "Detection gate **unconfirmed** · occlusion", "Vanished ball 148 mm · left-side", "Gate notes `cloth_occluded_at_disappearance · pocket_test_disagrees_px_vs_mm`" | PASS |
| 5 | Console + overflow | 0 console messages at 1280x599 and 390x844; `scrollWidth` 1280 and 390 (= innerWidth), no horizontal overflow | PASS |
| 6 | Provenance notice | **not rendered**: `provenance.statement` / `provenance.detector` never reach the DOM — see the ask below | GAP |

Screenshots: `out/scan30/ui/{dense_cards_1280,dense_cards_390,dense_pot_inspector_1280,dense_rail_1280}.png`.
`out/corner-pocket/state.json`, `out/pid_seed.json` and `out/scan30/annotations.json` are byte-identical after.

**The UI ask, exactly** (not edited here; the UI worker owns `annotator/`):
`app.js` copies each event into the snapshot, and `provenance` is missing from
that copy — add `provenance: e.provenance && typeof e.provenance === 'object' ? {...e.provenance} : null`
next to `tier`/`geometry_check`, then render one line per card in
`vision-stage.js` (`railHTML`), e.g.
`provenance.detector` + the EN/中 statement `provenance.statement` (中: 「机器产出，未经人工确认」).
The optional evidence numbers (`gate.numbers.dense_peak_speed_px_s`,
`dense_net_displacement_px`, `dense_path_length_px`, `dense_duration_s`,
`dense_frame_range`) ride in the same payload if the inspector wants them.

## Round 6 — the gate changed under the queue, so the queue was rebuilt (commit `f6d99dc`)

The gate stopped accepting oscillation shots and started deciding the pocket test
in millimetres with a propagated localisation error (commits `28a0982`, `da6d5ac`,
`1246000`, `cd0298a`). The same segment re-run through that gate
(`out/dense-events/segment-1350-1650.gate2.json`) leaves **1 shot, 0 pots, 8
unknown disappearances, 701 rejections, 6 unresolved runs**: two of the four
served events are no longer events at all.

| was | ball | now | the number that removed it |
|---|---|---|---|
| `#9001` | `t125-white` t=1482.3 | `oscillation_no_net_travel` rejection | 0.20 px of net travel (**0.015** ball diameters of 13.8 px), 80.56 px of path, peak 303.6 px/s, against the 27.6 px / 2.0-diameter bar |
| `#9003` | `t256-blue` t=1621.5 | `oscillation_no_net_travel` rejection | 19.70 px of net travel (**1.43** diameters), 59.92 px of path, peak 301.7 px/s, 7.90 px short of the same bar |

Neither was silently dropped: both ids are **retired** (never handed to another
ball), both rows sit in `dense_queue_report.json` under
`channels.departed_entries` with the gate's own sentence, and both are counted in
`channels.oscillation_rejections.served_before`.

**Ids are stable by identity.** `#9002` (`t193-blue` shot) and `#9004`
(`t265-blue` unknown) kept their numbers through the rebuild because a verdict may
already point at them; the builder keys on `provenance.ball_id`, starts any new
ball above every id ever issued here, and re-running it on the same gate output
is byte-identical (`md5_before == md5_after` = `77777777777777777777777777777777…`). Served queue:
`out/scan30/events.json` `77777777777777777777777777777777…` → `77777777777777777777777777777777…`; `annotations.json`
`77777777777777777777777777777777…` before and after; `state.json` `77777777777777777777777777777777…`, `pid_seed.json`
`77777777777777777777777777777777…` untouched.

### The two channels that are neither an event nor a rejection

The gate's `pots` channel now carries *unknown* disappearances, not only
pot-shaped ones (`counts.pots` 0, `counts.unknowns` 8), so "everything in the
channel becomes a card" would have turned seven occluded dropouts into new review
cards. The serving rule is now written down in the report
(`serving_rule`): every shot the gate shaped as an event, a pot the gate
*confirmed*, and a pot-shaped unknown **only if the queue already carried it**.

| channel | count | served | why not |
|---|---|---|---|
| `oscillation_unresolved` (net travel inside the error of the bar) | 6 | 0 | the gate cannot tell a shot from an oscillation; five sit 0.4–4.0 px under the 27.6 px bar and one (`t242-red`) is 4.03 px *over* it, all inside the 5.12 px error |
| occluded unknowns (all `cloth_occluded_at_disappearance`) | 8 | 1 — the carried `#9004` | every one is `verdict_mm "ambiguous"`: the millimetre distance ± error straddles the 100 mm radius, so the gate itself will not call it a pot |
| `oscillation_no_net_travel` rejections | 23 | 0 | the gate said no |

All of it is counted with numbers in
`out/scan30/dense_queue_report.json` (`channels.unresolved.rows`,
`channels.occluded_unknowns.rows` incl. `moving_at_last_sighting`,
`not_served.unknowns_not_carded`, `channels.departed_entries`). **Argued, not
added:** three of the eight unknowns were still *moving* when they vanished
(211.3 / 312.8 / 734.2 px/s; the other five move at ≤ 17.4 px/s), which is the
class the served `#9004` belongs to — two of them (`t200-blue` 148.5 ± 54.0 mm
right-middle, `t202-blue` 84.5 ± 30.9 mm left-middle, `inside_mm` true) are the
same shape as `#9004` and are *not* served, because the owner's default is that a
new unknown does not become a card. If the owner wants the class, it is these
three, not eight; `t202-blue` is the closest thing this segment has to a pot the
gate could not call.

The served unknown now carries the gate's millimetre verdict with its error bar
(`vanish_dist_mm` 148.48, `vanish_dist_mm_uncertainty` 54.11, `vanish_dist_mm_lo/hi`
94.37/202.59, `vanish_radius_mm` 100.0, `vanish_verdict_mm` `ambiguous`,
`vanish_inside_px` true vs `vanish_inside_mm` false, `vanish_pocket_test` `mm`,
`vanish_distance_text` EN + 中), and the entry states why it is served while its
seven siblings are not (`provenance.served_because`, `provenance.unknowns_in_channel`).
The projected distance is kept as a cross-check (`vanish_dist_mm_projected`,
delta ≤ 0.13 mm against the gate's own number): both use the verified hand-anchor
geometry.

### Measured on the fixture (`:8131`, session `queuegate2-521027f9b1ad`)

| # | Check | Measured | Verdict |
|---|-------|----------|---------|
| 1 | Rail shows the rebuilt queue | `.vs-card` = **2**: `SHOTS MOTION WINDOW ONLY 26:20.1 #9002 1308 mm blue` and `POTS 27:18.5 #9004 left-middle (148 ± 54mm) 148 mm left-side` | PASS |
| 2 | The unknown's inspector shows the millimetre distance with its error bar, in words | `.vs-facts` = "Detection gate **unconfirmed** · occlusion", "Vanished ball 148 mm · left-side", "Gate notes `cloth_occluded_at_disappearance · pocket_distance_ambiguous_mm · pocket_test_disagrees_px_vs_mm · 148 ± 54 mm from the left-middle pocket -- too uncertain to call -- it straddles the 100 mm radius`" | PASS |
| 3 | Console + overflow | `console --json` → `"messages":[]`, `errors` → `[]` at **1280×800** and **390×844**; `scrollWidth` 1280 and 390 (= innerWidth) | PASS |
| 4 | Nothing outside the fixture was written | `annotations.json` `77777777777777777777777777777777…`, `state.json` `77777777777777777777777777777777…`, `pid_seed.json` `77777777777777777777777777777777…` byte-identical after | PASS |
| 5 | The sentence is reachable without a UI change | rendered by the existing notes row (no `annotator/` edit); it wraps over 4 lines inside the inspector's own scroll area (`.vs-inspector-scroll` 349/741 px) | PASS |

Screenshots: `out/scan30/ui/{dense_queue_2cards_1280,dense_queue_unknown_inspector_1280,dense_queue_2cards_390}.png`.

**The UI ask, exactly** (not edited here; the UI worker owns `annotator/`): the
mm line reaches the DOM only as the last element of `gate.reasons`, so the
operator reads three codes before it and the number wraps mid-figure
(`148` / `± 54 mm`). Give the error bar its own row: render
`gate.numbers.vanish_dist_mm_uncertainty` beside `vanish_dist_mm` in the
`gateVanish` row (`vision-stage.js` line ~374) so it reads `148 ± 54 mm ·
left-side`, and shorten the notes row to the codes
(`gate.codes` now carries them separately, so `gate.reasons` need not hold both).
Second nit: `gateVanish` and the `Pocket` row print the stored key
(`item.pocket_name` / `n.vanish_pocket` = `left-side`) while the card and the
sentence use the display word (`left-middle`); `pocketText()` already does that
mapping, these two rows just do not call it.

Suites after the rebuild: python `932 tests, 3 skipped`, all green
(`tests/test_queue_decision.py` grew from 11 to 19 pins: id stability, id
retirement, the not-carded unknowns, the unresolved runs, the rerun-is-identical
property and the millimetre error bar).
