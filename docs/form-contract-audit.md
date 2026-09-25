# Form contract audit — what the UI collects vs. what the server requires

Trigger: the owner could not add a regular — "操作失败: 请求未被接受，检查输入或展开技术详情。
技术详情 Rating must be an integer from 0 to 1000". The create form has no rating
field, the client still sent `rating:Number(undefined)` → `NaN` → JSON `null`, and
`player_save` rejected the present-but-null key.

Bug class audited here: (a) the client sends a value the form never collected;
(b) the server requires a field the UI does not ask for; (c) a lossy coercion
(`Number('')`→`0`, `Number(undefined)`→`NaN`→`null`, `.trim()` on `undefined`);
(d) a rejection the user can cause by normal input that is explained only by a raw
technical sentence (in 中 that sentence falls back to the generic
"请求未被接受，请检查输入或展开技术详情。").

Method: every `<form>` and every `action(...)` call in `annotator/ops.js`, every
`_apply` branch in `annotator/operations.py`, and the Vision/identity writes in
`annotator/vision-stage.js` / `annotator/app.js` → `annotator/unified_server.py`.
"Today" was measured against the worktree server in a temp directory (probe
script, no production file touched), not inferred.

Mechanics that apply to every ops form: no form sets `novalidate`, so the
browser's own `required`/`min`/`max` checks run before submit and show a native,
localized bubble next to the field. A defect exists only where those checks
cannot stop an input the server will reject.

## Ops forms (`annotator/ops.js` submit handler → `POST /api/operations`)

| Form → action | Fields collected | Server requires | Edge input | Today | Fix |
|---|---|---|---|---|---|
| New regular (`player-form`, create) → `player_save` | `name` (`required maxlength=120`), hidden `status=Active` | `name` 1–200 chars; `rating` int 0–1000 **if present**; `status` in Active/Visitor/Prospect/Inactive | no rating field at all | **Fixed.** Was: `rating:null` sent → rejected (the owner's bug) | `dea6606` client sends rating only when collected; `e0d72c7` server treats missing/`null`/`''` rating/status as the default (0 / Active) and still rejects a present invalid rating |
| Edit regular (`player-form`, edit) → `player_save` | `id`, `name`, `rating` (`required min=0 max=1000`), `status` select (Active/Visitor/Inactive), `notes` (`maxlength=4000`) | as above; notes ≤4000 | rating cleared / `12.5` / `1001` | Browser blocks empty (`required`), non-integer (default `step=1`) and out-of-range before submit | none needed |
| Regular name (both) | `maxlength=120` | ≤200 | whitespace-only name | Browser `required` accepts `"   "`; server rejects "name must contain 1–200 characters" (untranslated in 中) | **D4a** |
| Event settings (`settings-form`) → `tournament_setup` | `name` (`required maxlength=120`), `format` select, `raceTo` select 1/3/5/7/9/11, `tables` number (`min=1 max=32 required`) | `tables` int 1–32, `raceTo` int 1–99, `name` 1–200, format singles/doubles | whitespace-only name | Rejected "name must contain 1–200 characters"; 中 shows only the generic fallback | **D4a** |
| | | | tables `2.5` | Browser blocks (step=1) | none |
| | | | tables blank / `0` / `33` | Browser blocks (`required`, `min`, `max`) | none — `Number('')` path is unreachable through the UI |
| Registration (`entrant-form`) → `entrant_add` | per member: `pid{i}` select (default "Guest"), `guest{i}` text (`maxlength=120`, **not required**) | `members` list of the format's size; each member either a known `pid` or a guest `name` 1–200 chars that is not a regular's name | "Guest" left selected and name blank (e.g. just pressing **Add entrant**) | Rejected "guest name must contain 1–200 characters"; 中: generic "请求未被接受…" only | **D2** field-level plain message, no request |
| | | | whitespace-only guest name | same as above | **D2** |
| | | | guest name equals a regular's name | Rejected; translated ("该姓名已属于常客，请从常客名单选择。") | none |
| | | | `v.guest{i}` absent → `.trim()` on undefined | Not reachable: `guest{i}` is always rendered with its select | D2 removes the `.trim()` on a possibly-absent value anyway (same line) |
| Scorecard (`score-form`) → `match_score` (+ `match_complete` on Sign) | `id` select of live matches, `a`,`b` numbers (`min=0 max=raceTo required`) | 2 ints 0..raceTo, not both raceTo; complete needs a live race-winning score | blank / out-of-range / fraction | Browser blocks | none |
| | | | both = raceTo | Rejected, translated ("双方不能同时达到获胜比分。") | none |
| | | | Sign with no winner yet | `match_score` saves, `match_complete` rejected, translated | none |
| Table appearance (`appearance-form`) → `settings_update` | `clothColor` select (4 server colours), `lampGlow` range 0–0.5 step 0.02, `showDiamonds` checkbox | colour in the 4-value set, glow finite 0–0.5, bool | a range input always has a value; unchecked box → `false` (tested) | Always valid | none |
| Add stream (`source-form`, rendered by `vision-stage.js`) → `source_add` | `url` (`type=url required`) | https twitch.tv channel or `/videos/<digits>`, no query/fragment, not reserved, not a duplicate | reserved path (e.g. `/wallet`) | Client `parseSource()` accepts it (its reserved list is shorter than the server's), server rejects "Use a Twitch channel or videos/<digits> URL" (untranslated) | **D4b** |
| | | | the same channel twice | Rejected "Source already added" (untranslated) | **D4b** |
| House note (`note-form`) → `note_add` | `text` (`required maxlength=4000`) | 1–4000 chars after trim | whitespace-only | Rejected "note must contain 1–4000 characters" (untranslated) | **D4a** |
| Face photo (`enroll-form`) → `POST /api/identity/enroll` | file (`required`), `player_id` from the rendered profile | non-empty `player_id`, decodable image ≤8 MB | no file | Browser `required` blocks; handler also returns early | none |
| | | | non-image / >12 MB body | Plain "Enrollment failed: …" + server sentence in EN, localized prefix only in 中 | out of scope (not a form-contract defect; server sentence is already plain) |

## Ops click actions (no form)

| Button → action | Payload | Server requires | Edge | Today | Fix |
|---|---|---|---|---|---|
| Shot-clock 20/30/45/60 → `settings_update` | `shotClock:Number(data-value)` | int 5–300 | constants only | Always valid | none |
| Score ± / Win frame / Clear / Sign (floor) → `match_score` / `match_complete` | ints from `data-side`/`data-delta`, clamped to 0..raceTo | as above | buttons render only for a live match | Valid | none |
| Here now / Not here → `match_absence` / `entrant_absence` | `absent:data-absent==='true'` (a bool) | bool | — | Valid | none |
| **Send to table** → `match_schedule` | `{id}` — the server picks the first free table | `table` int 1..tables, not occupied | every table already has a live match (e.g. 1 table, second match ready) | Rejected "table must be an integer from 1 to 1" — the server's `next(..., None)` falls through to the integer check; 中 generic fallback | **D3** plain "All tables are in use…" message, both languages |
| Release table → `match_unschedule`, Forfeit → `match_forfeit`, Remove entrant, Start night, Archive (`tournament_new`, sends `confirm:true`), Delete regular, Promote guest, Delete stream/note | ids / constants from the rendered item | known id; state guards | stale id after another tab edits | Revision check → reload + "State changed" (translated) | none |

## Server actions with no UI (reachable only by a hand-written request)

`guest_promote` with an unknown name, `absent` non-bool, `Invalid member`,
`JSON object required`, `integer revision required`, `Unknown operations action`,
`Invalid cloth color`, `showDiamonds/autoFrame must be boolean`: the UI never sends
these shapes, so they stay technical by design.

## Vision / identity writes (`app.js` `save()` → `unified_server.py`)

| Control → endpoint | Collected | Server requires | Edge | Today | Fix |
|---|---|---|---|---|---|
| Person label: regular select / guest name → `/api/identity/seed` or `/api/vod30/seeds` | `select` value or `guest-name` (`maxlength=60`) | `player_id` non-empty / label = A/B/ignore/guest ≤60 chars/null | nothing picked, blank or whitespace name | Refused client-side before any write, translated ("请先输入访客姓名或选择常客，再保存。") | none |
| Enrol from track → `/api/identity/enroll-confirm` | `enroll-name` (`maxlength=60`) | `player_name` string ≤60; empty → module refusal `player_name_required` | blank name | Refusal shown in operator words, both languages | none |
| VOD replay start → `/api/live` | `vod` text, `start` number (min 0), `rate` number (0.25–4) | `vod_id` parseable, `start_s` ≥0, `0 < rate ≤ 8` | blank start / rate | Client coerces `Number('')||0` → start 0 and `||1` → rate 1: the documented defaults, never an invalid value | none |
| | | | blank VOD | Refused client-side (`vodId` prompt) | none |

## Defects fixed (one commit each, test first)

| Id | Commit | What the user sees now |
|---|---|---|
| #1 client | `dea6606` | New regular sends no `rating`; saved with rating 0 |
| #1 server | `e0d72c7` | `player_save` treats missing/`null`/`''` rating or status as the default; a present invalid rating (`'abc'`, -5, 1001, 12.5, `true`, `' '`) is still rejected. Needs a service restart |
| **D2** | `6223841` + `5e0cb93` | Blank/space guest with no regular picked → no request; next to the guest-name field: "Type a guest name or choose a regular." / "请输入访客姓名，或选择一位常客。". Typing, or choosing a regular (`5e0cb93`), clears it |
| **D3** | `258acd8` | Send to table with every table live → "All tables are in use" / "所有球台都在使用中，请先释放一张球台。" (server half needs a restart; an explicit bad table number keeps the range message) |
| **D4a** | `04123c5` | Any required text field holding only spaces (regular name, event name, house note) → no request; next to the field: "Fill this in — spaces alone don't count." / "请填写此项，仅有空格不算。" |
| **D4b** | `dde7266` | Twitch pages the server refuses (subscriptions, inventory, wallet, jobs, turbo) get the existing bilingual source hint without a request; "Source already added" and "Use a Twitch channel or videos/<digits> URL" are translated |

In every case the raw server sentence, when there is one, stays behind
"技术详情 / Technical details".

(D1 — `settings-form` `Number('')` — was a suspect but is unreachable: the browser's
`required`/`min`/`max` block blank and out-of-range tables before submit, and race
is a select. Recorded above instead of "fixed".)
