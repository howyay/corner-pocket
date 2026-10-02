# The public board under load — measured

*The 50-poller measurement `docs/public-board.md` recorded as still owed (§5 pre-flight,
"the 50-poller load test was not run"): what 50 phones polling the board every 3 s cost,
and whether the console feels it. Every figure below comes from a run on this host on
2026-10-02 and is traceable to the raw report block pasted in §3.*

| | |
|---|---|
| script | `tests/load_public_board.py` (stdlib only, re-runnable, exit 0 = every assertion held) |
| fixture | `tests/serve_operations_fixture.py --public-port <p> --public-prefix /board` — the same `PublicBoardServer` + `make_public_handler` the deployed listener runs, in a throwaway root, on two free loopback ports ≥ 8230 |
| driven like the page | 50 pollers, one conditional `GET /board/api/board` every 3 s (`board.js`'s `POLL_MS = 3000`), `If-None-Match` from the last `ETag` |
| the number that matters | `GET /api/operations` on the console port, 50 pollers over the same window (§5) |
| never touched | anything but the loopback fixture: the origin is asserted per request (host must be `127.0.0.1`/`::1`/`localhost` **and** the port must be one of the two this run started), and only `GET` is ever sent |

## 1. How to reproduce

From the repository root:

```
.venv/bin/python tests/load_public_board.py                          # 50 public + 50 console, 3 s, 120 s
.venv/bin/python tests/load_public_board.py --json out/load-board.json
.venv/bin/python tests/load_public_board.py --pollers 0 --console-pollers 50   # console-only baseline
```

The script starts the fixture itself, waits for both listeners, preflights them (public
board answers `200` with a `board` field and an `ETag`; the same `ETag` answers `304`;
`/board/api/operations` is a `404` on the public port; the console answers
`/api/operations` with a `revision`), runs the window, optionally fires `--burst` N
simultaneous GETs, then reads the fixture's CPU from `/proc/<pid>/stat` (utime+stime) and
computes the share of one core. It reaps the fixture with `SIGINT` (the fixture's own
`KeyboardInterrupt` path removes its temporary root), escalates to `SIGTERM`/`SIGKILL`
only if it has to, and asserts both ports stopped accepting and the temporary root is gone.
It exits non-zero on an error rate above `--max-error-rate` (default 1%) or a p95 above
`--p95-ms` (default 250 ms) on either surface.

A note on the two ends of that loop: the fixture's console is a stdlib `ThreadingHTTPServer`
(backlog 5, one thread per connection), while the deployed console is the repository's
`BoundedHTTPServer` (64 slots, backlog 64, `503 busy` when they run out). The **public**
listener is production's own class in both cases. So the public figures transfer directly,
and the console figures are a loaded-versus-baseline comparison, not a capacity figure for
the deployed console — see §5.

## 2. The numbers

Two full runs, back to back, same flags (`--burst 24`), same host. "baseline" is the third
run: the same 50 console pollers with **zero** public pollers, which is what "the console
must stay unaffected" has to be measured against.

| | run A2 (started 12:37:55) | run B (started 12:40:01) | baseline (window ≈12:44:53 → 12:46:53) |
|---|---|---|---|
| public port / console port | 8233 / 8232 | 8231 / 8230 | 8231 / 8230 |
| public requests sent | 2000 | 2000 | 0 (none sent, on purpose) |
| public `200` / `304` | 50 / 1950 (**97.5%** of answers) | 50 / 1950 (**97.5%**) | — |
| public failures | **0** (0.0%) | **0** (0.0%) | — |
| public p50 / p95 / p99 / max | 1.19 / 4.23 / 9.05 / 29.23 ms | 0.98 / 3.01 / 6.19 / 18.74 ms | — |
| console requests sent | 2000 | 2000 | 2000 |
| console failures | **0** (0.0%) | **0** (0.0%) | **0** (0.0%) |
| console p50 / p95 / p99 / max | 1.51 / 6.00 / 428.93 / 1620.16 ms | 1.04 / 3.22 / 8.15 / 87.08 ms | 1.15 / **2.92** / 14.60 / 414.69 ms |
| fixture CPU (both listeners, one process) | 2.63 s / 120.0 s = **2.19%** of one core | 2.39 s / 120.0 s = **1.99%** | 1.34 s / 120.0 s = **1.12%** |
| load generator's own CPU | 2.65% of one core | 2.37% | 1.32% |
| burst: 24 simultaneous GETs | 24× `200`, p50 4.59 / p95 5.98 ms, no failures | 24× `200`, p50 20.22 / p95 26.37 ms, no failures | — |
| machine | 12 cores, loadavg 25.82 → 23.58 | 12 cores, loadavg 23.03 → 18.36 | 12 cores, loadavg 20.75 → 17.91 |
| cleanup | `SIGINT`, exit 0, both ports closed, no leftover | `SIGINT`, exit 0, both ports closed, no leftover | `SIGINT`, exit 0, both ports closed, no leftover |
| verdict | **PASS** | **PASS** | exits 1 by design (no public pollers) |

How those times are known: runs A2 and B were bracketed by `date -Is` stamps in the shell
that started them, and their report files are stamped 12:40:01 and 12:42:09 — 126 s and
128 s after their starts, which matches the 120 s window plus warmup and cleanup. The
baseline's last fixture log line is stamped `12:46:53` (quoted in §3) and its report file
was written at 12:46:53.316, so its window ended then and therefore began ≈12:44:53.

## 3. Raw output

### Run A2 — 50 public + 50 console pollers, 3 s, 120 s

```
== public board load test (tests/load_public_board.py) ==
command      : /home/haoye/projects/pool-w-load/.venv/bin/python /home/haoye/projects/pool-w-load/tests/serve_operations_fixture.py --port 8232 --public-port 8233 --public-prefix /board
targets      : public http://127.0.0.1:8233/board/api/board  |  console http://127.0.0.1:8232/api/operations
origins sent : 127.0.0.1:8232, 127.0.0.1:8233   (loopback only, re-asserted before every request)
window       : 120.0 s served (asked for 120 s), 50 public pollers @ 3.0 s, 50 console pollers @ 3.0 s, warmup 5.0 s
public       : 2000 sent | 200 50 | 304 1950 (97.5% of board answers) | failed 0 (0.0%) | answers from t=0.0s to t=120.0s
public ms    : p50 1.19 | p95 4.23 | p99 9.05 | max 29.23
console      : 2000 sent | 200 2000 | failed 0 (0.0%) | answers from t=0.0s to t=120.0s
console ms   : p50 1.51 | p95 6.00 | p99 428.93 | max 1620.16
fixture cpu  : pid 3796023 2.63 s cpu over 120.0 s wall = 2.19% of one core (both listeners in one process)
client cpu   : this script 2.65% of one core (the load generator shares the machine)
machine      : loadavg 25.82 19.01 13.28 before -> 23.58 19.94 14.28 after | 12 cores
burst probe  : 24 simultaneous GETs | statuses {'200': 24} | p50 4.59 ms p95 5.98 ms | no failures
preflight    : public /board/api/board -> 200, board='on', revision=0, etag=True | public conditional GET -> 304 (304 expected) | public /board/api/operations -> 404 (must be 404) | console /api/operations -> 200, revision=0
cleanup      : signals ['SIGINT'] | exit 0 | ports closed {8232: True, 8233: True} | leftover in TMPDIR none
verdict      : PASS (every assertion held)
```

### Run B — same flags, second run

```
window       : 120.0 s served (asked for 120 s), 50 public pollers @ 3.0 s, 50 console pollers @ 3.0 s, warmup 5.0 s
public       : 2000 sent | 200 50 | 304 1950 (97.5% of board answers) | failed 0 (0.0%) | answers from t=0.0s to t=120.0s
public ms    : p50 0.98 | p95 3.01 | p99 6.19 | max 18.74
console      : 2000 sent | 200 2000 | failed 0 (0.0%) | answers from t=0.0s to t=120.0s
console ms   : p50 1.04 | p95 3.22 | p99 8.15 | max 87.08
fixture cpu  : pid 3825815 2.39 s cpu over 120.0 s wall = 1.99% of one core (both listeners in one process)
client cpu   : this script 2.37% of one core (the load generator shares the machine)
machine      : loadavg 23.03 19.94 14.35 before -> 18.36 19.36 14.83 after | 12 cores
burst probe  : 24 simultaneous GETs | statuses {'200': 24} | p50 20.22 ms p95 26.37 ms | no failures
cleanup      : signals ['SIGINT'] | exit 0 | ports closed {8230: True, 8231: True} | leftover in TMPDIR none
verdict      : PASS (every assertion held)
```

### Baseline — 50 console pollers, no public pollers

```
window       : 120.0 s served (asked for 120 s), 0 public pollers @ 3.0 s, 50 console pollers @ 3.0 s, warmup 5.0 s
public       : 0 sent | 200 0 | 304 0 (n/a of board answers) | failed 0 (n/a) | answers: none
public ms    : p50 n/a | p95 n/a | p99 n/a | max n/a
console      : 2000 sent | 200 2000 | failed 0 (0.0%) | answers from t=0.0s to t=120.0s
console ms   : p50 1.15 | p95 2.92 | p99 14.60 | max 414.69
fixture cpu  : pid 3855201 1.34 s cpu over 120.0 s wall = 1.12% of one core (both listeners in one process)
client cpu   : this script 1.32% of one core (the load generator shares the machine)
machine      : loadavg 20.75 21.01 16.27 before -> 17.91 20.37 16.64 after | 12 cores
cleanup      : signals ['SIGINT'] | exit 0 | ports closed {8230: True, 8231: True} | leftover in TMPDIR none
verdict      : FAIL (public: error rate n/a > 1.0% (0 failed: {}); public: p95 n/a ms > 250 ms; public: no requests were sent)
```

`--pollers 0` is the one way to make the script exit non-zero on purpose: its three public
assertions have nothing to look at. The console rows are still the whole point of the run.

## 4. What it says

- **The board is cheap.** 100 pollers in total — 50 phones on the board plus 50 on the
  console, both at 3 s — cost the serving process **~2% of one core** (2.19% and 1.99% in
  the two runs), i.e. under a quarter of one percent of this 12-core host.
- **The phones mostly get `304`s.** 1950 of 2000 board answers were `304 Not Modified`
  (97.5%); the ETag round trip works exactly as `board.js` expects: one `200` per poller at
  the start, then conditional GETs. The board's own p95 stayed at 3-4 ms on loopback.
- **The console stayed up and fast** under the same load: 2000/2000 answers, no failures,
  p95 6.00 ms (run A2) and 3.22 ms (run B) — against a console-only baseline of p95 2.92 ms
  with **no** public load at all. So the board's 50 pollers did not move the console's
  p50 (1.04-1.51 ms loaded vs 1.15 ms baseline) or its p95 into a different order of
  magnitude; the tails are host noise, see §5.
- **The listener pool held.** 24 simultaneous GETs — more than `PublicBoardServer`'s 16
  slots — all answered `200` (p95 5.98 ms / 26.37 ms), so the pool queues and drains
  requests rather than refusing them: no `503 busy` appeared in any run.
- **The run cleans up after itself.** Every run reaped the fixture with a single
  `SIGINT` (exit 0), both ports stopped accepting, and the fixture's temporary root was
  removed — nothing was left running.

## 5. Honest limits

- **The console side of the fixture is not the deployed console.** The fixture's console is
  a stdlib `ThreadingHTTPServer` (backlog 5); production runs `BoundedHTTPServer` (64 slots,
  backlog 64, explicit `503` when full). The loaded-versus-baseline *comparison* is still the
  answer to §5's question, but the absolute console milliseconds belong to the fixture.
- **The box was heavily shared.** Other agents were running on this host throughout
  (loadavg 18-27 on 12 cores), which is why run A2's console p99 is 428.93 ms (max 1620.16 ms)
  while run B — the same test, same flags — shows p99 8.15 ms and max 87.08 ms. The baseline
  settles it: with **no** public pollers at all, the console still produced a single 414.69 ms
  answer, so the console's tail here is scheduler starvation on an oversubscribed host, not a
  property of the server or of the board's load. The public surface never showed this (its
  worst single answer across both runs was 29.23 ms). Use the p50/p95 columns, not the p99.
- **The board's own cost is the delta, not the total.** The fixture process uses ~1.12% of a
  core serving 50 console pollers with the public listener idle, and ~2% serving 50 console
  *and* 50 public pollers — so the 50 phones on the board cost roughly **1% of one core**.
- **The fixture's board never changes** (`revision` 0 for the whole run), so every poller gets
  `304`s forever. A board whose revision ticks once a second would rebuild the JSON on the
  1 s cache boundary in `Backend.public_board` and answer `200` far more often: the measured
  CPU share is a **lower bound** for a live board, and the `304` share here is an upper bound.
- **Loopback, not the internet.** These numbers contain no TLS, no Cloudflare edge and no
  tunnel; §6 measures a little of that, with 10 pollers rather than 50.
- **A first pair of full runs is void, and the reason is kept here.** The harness originally
  handed the fixture's stderr to a pipe nobody drained. The public handler logs only refusals
  — `log_request` is overridden at `annotator/unified_server.py:1921` precisely so that "a
  3 s poller" does not fill the journal — but the console handler has no such override and
  logs every request, so once ~64 KB of lines had accumulated every console handler thread
  blocked in `write()`. The symptom was a console that answered 106 requests and then timed
  out 1150 times while the public listener stayed perfect — and a fixture that ignored
  `SIGINT` for 15 s and had to be `SIGTERM`ed (its threads were stuck in those same blocked
  writes; the shutdown path itself was not instrumented, so that last link is inference, not
  measurement). The fix writes the fixture's output to `fixture-output.log` under its own
  temporary root; the same 25 s run afterwards answered 417/417 console requests with no
  failures. If a future reader finds the void runs' numbers (`/tmp/load-runA.json`), that is
  what they measured.
- **The fixture itself has no automated test** — `tests/load_public_board.py` is its only
  programmatic user. Alongside this work: `node --test tests/test_ops.js` (102 pass / 0 fail),
  `node tests/test_app_timeline.js` (80 passed, 0 failed) and
  `PYTHONPATH=.:tests .venv/bin/python -m unittest test_public_board` (28 tests, OK) all pass
  unchanged.

## 6. Production, read-only spot check

Separate throwaway probe (not part of the deliverable, which is loopback-only by design),
run from this host over the public internet on 2026-10-02: 10 concurrent pollers, one
conditional `GET https://pool.yay.how/board/api/board` every 3 s for 60 s — **only `GET`**.
No `POST`, no `PUT`, no `PATCH`, no `DELETE`, no console route, no credentials, nothing
written; the console's `/api/operations` was never requested.

```
prod read-only GET https://pool.yay.how/board/api/board | 10 pollers @ 3 s | 60.0 s wall | only GET, nothing else
statuses    : {'200': 10, '304': 190} | failed 0 (none)
requests    : 200 sent
latency ms  : p50 78.22 | p95 172.49 | p99 375.15 | max 378.93
304 share   : 95.0% of answers
```

That is the whole path — TLS, Cloudflare, the tunnel, then the listener — so it is ~78 ms
per answer at the median against 1 ms on loopback, and the `304` behaviour holds there too.
One caveat about the tool, not the server: this venv's Python cannot see the system trust
store (`SSLCertVerificationError: unable to get local issuer certificate`), so the probe
verifies against `certifi`'s bundle; a `curl` run against the same URL reported
`ssl_verify_result=0`, `status=200` and `time_total=0.201510s`.

## 7. Where this leaves the pre-flight

`docs/public-board.md` §5 asked for four things against a fixture: the public port's CPU,
the p95 of `GET /api/board`, the p95 of `GET /api/operations` on the console during that
window, and 50 concurrent pollers at 3 s for two minutes. All four are above, from two
runs, with the console's baseline for comparison. The board can be left serving.
