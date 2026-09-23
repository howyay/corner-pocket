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
