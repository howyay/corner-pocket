# Corner Pocket verification ledger

This records observed checks, not full feature completion. The authoritative acceptance scope is `corner-pocket-functional-inventory.md`, amended by the confirmed native Vision hierarchy in `corner-pocket-operations.md`.

## Verified before native Vision integration

- Full regression command: `PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -q` — 38 tests passed.
- `node tests/test_app_timeline.js` — 11 passed.
- `node --test --test-reporter=tap tests/test_ops.js` — 5 passed.
- Browser using temporary operations store: tournament setup, two guest entrants, draw start, table assignment, score save 7–4, signed championship persisted.
- Found and fixed form `name=id` shadowing `form.id`; regression verifies score-save then completion ordering.
- Browser: appearance settings and literal HTML-like note persist after reload; player registration succeeds; Twitch VOD source produces `player.twitch.tv` URL with the actual hostname in `parent`.
- Browser: Chinese navigation and light theme persist; no page horizontal overflow at 390px on checked screens.
- Twitch embed URL correctness is not evidence of successful playback of an accessible real stream.

## Native Vision integration evidence

- Browser verified six top-level tabs with Vision fourth and six native subsections; every review mode loaded real fixture data without review iframe.
- Browser confirmed no duplicate DOM IDs and no horizontal page overflow at 390px in native timeline.
- Browser confirmed dirty event notes persist through theme/language changes; cancelling top-level navigation stays in Vision with edits intact.
- Regression suites after native integration: 14 review tests and 11 operations UI tests passed. Subsequent additions require a fresh final run.
- Backend suite reported 47 passing tests, including table release, absence propagation, and separation of roster records from video identity files.
- Doubles fixture: registration, draw with absent team, delayed status, attendance recovery, table assignment and release were exercised; release preserved scores in persistent state.
- Independent source audit withdrew stale table-release/archive/picker findings after current-file recheck. Full Vision editor localization remains in progress. Operations validation now has Chinese primary messages with exact technical detail retained separately; its 16-test frontend suite passes.
- Added player-note form coverage and a truthful nine-area Back room roadmap, distinguishing actual local functionality from deferred services.
- Operations backend suite now passes 23 tests, including a complete doubles lifecycle with two parallel tables, score-preserving release/reschedule, final result, and archive persistence.
- Browser detected sticky-header control occlusion. After restoring document scroll padding, independent browser verification measured the Here now control at top 308.3px below a header ending at 123.1px; center hit-testing reached the control and a real click restored attendance. Operations UI regression suite then passed 14 tests, including mixed live/delayed selection.

## Latest regression checkpoint

After dynamic Vision localization: `node tests/test_app_timeline.js` passed 15 tests, `node --test --test-reporter=dot tests/test_ops.js` passed 16 tests, and the full Python discovery suite passed 49 tests. Browser confirmed language changes preserve unsaved user notes and option API values, with nested review navigation hidden and no JavaScript errors. Final dynamic-caption browser checks and coverage audit remain outstanding.

## Final implementation verification

Final frontend suites passed 16 review tests and 16 operations UI tests. The combined command timed out during Python startup; an independent Python rerun passed all 49 tests in 46.676 seconds. Final browser recheck confirmed all six numbered calibration anchors, timeline ball-type captions, and the complete correction hint in Chinese, with no JavaScript errors. Earlier browser runs covered all five native modes, dirty-state preservation, roster/settings/notes/source registration, and tournament operations as recorded above.

Implementation is ready for owner review, not externally deployed. Real Twitch playback/authentication, browser-native video-control language, and the explicitly deferred live/automatic CV roadmap are not represented as verified functionality.

## Deployed fix: Vision dead space and fidelity pass

User-visible bug: `main { min-height: 65vh }` inflated the Vision screen's main area (~390px) while review content lived in the sibling host, leaving a large empty block; the embedded review also mounted a duplicate brand/chips header. Fixed with a `short` class toggle on `#main` for review subtabs, compact embedded header (dataset selector row kept), and tightened page headings. Screenshot-verified on the deployed origin: queue and candidate content now start within the first viewport.

Pixel-fidelity pass (four screenshot-compare rounds against the design mockup at 1280px and 390px) aligned header, nav balls, chip groups, strip, scoreboard, forms, tiles, scrollbars, selection, toasts, and mobile overflow. Remaining differences are functional data or explicit adaptations, recorded in the subagent handoff.

## Body re-ID calibration verdict (2026-09-15)

Measured on real footage (401 frames, 1183 OSNet embeddings, IoU-chain pseudo-ground-truth): same-person p05 0.755 vs cross-person p95 0.882 — the distributions overlap and no threshold separates players at this resolution (same person dropped to 0.678; different people reached 0.983). Body-only clustering is therefore **disabled by default** (`BODY_MATCH_DISABLED`); each tracked person holds an independent cluster, and cross-exit identity comes from face binding to enrolled regulars plus explicit A/B/ignore seeds. Spot check: the previous single mega-cluster became 7 distinct tracks with no unenrolled bindings. Re-enabling body merging requires explicit constants and better evidence.

## Deployed fix: stale-cache Vision breakage

After removing the standalone review page, browsers holding pre-integration cached `ops.js`/`app.js` fetched `/app.html`, received the new 308 redirect, and every review subtab failed while Stream still worked. Root fix: the server now sends `Cache-Control: no-store` for all application responses (HTML/JS/CSS/API); only `/media/` byte-range responses remain cacheable, and `ops.html` references versioned asset URLs as a one-time cache-buster. Regression covers these headers. Deployed and browser-verified: all six Vision subtabs mount real data with no JavaScript errors.

## Acceptance coverage

- Exactly six top-level tabs; Vision fourth, with six native subtabs.
- All five existing review modes operate without iframe or separate-page navigation.
- Operations rerenders (theme/language/action refresh) do not discard mounted review state.
- Unsaved-edit and in-flight-save guards cover top-level and subtab navigation.
- Hidden review does not consume keyboard shortcuts or mutate unrelated operation forms.
- No duplicate IDs or CSS leakage between club screens and review editors.
- Dataset changes and frame/inference asynchronous responses remain correctly scoped.
- Existing operations and review regression suites remain green.
- Browser workflows exercise doubles, byes, multi-table focus, absences, archives, promotion, settings and notes.

Use `tests/serve_workbench_fixture.py` at loopback port 8131 for integrated browser work. It uses copied annotation JSON and read-only source video access, not production writes. Use `tests/serve_operations_fixture.py` for a temporary empty club. Stop managed fixtures after verification.

Production service restart and external deployment remain excluded without explicit confirmation.
