'use strict';
/* The shared shot clock — client half. Server half: annotator/shot_clock.py with
 * GET/POST /api/clock and GET /api/clock/stream in annotator/unified_server.py.
 *
 * ops.js owns the clock's DOM: one closure-private `timer`, one 200 ms interval
 * that repaints every [data-clock] / [data-progress], and the strip, the floor
 * scoreboard and the vision stage bar all painted from that same `timer`. That
 * closure is unreachable from outside — ops.js is a single IIFE that exports
 * nothing — so ops.js publishes one named seam for it:
 *
 *   window.OpsClock = {
 *     receive(value),       // in:  the JSON a storage event carries
 *     words(),              // out: { lang, kicker } — the one name, and the language it is in
 *     sync(text)            // out: the one sentence the sync line shows, painted by ops.js
 *     onAccepted(a, v, t)   // in:  published here; ops.js calls it when it takes a press
 *   };
 *
 * So this module hands ops.js a clock whose deadline is expressed in *this
 * device's* clock base (server deadline − measured offset) by calling that seam.
 * ops.js stays the only painter: it paints the shot timer's name, and it paints
 * the sync line it already emits, from the sentence this module sends back
 * over the same seam. Nothing here writes into the page, so no observer of the
 * console's renders is needed and no language has to be guessed from screen text.
 * A real `storage` event from another tab is the other way in, and ops.js keeps
 * listening for it; this module no longer forges one.
 *
 * Offset, NTP style: offset = server_now_ms − (t_send + rtt/2), measured around
 * one GET /api/clock. What is displayed is deadline_ms − (Date.now() + offset),
 * which is exactly what ops.js computes from the local deadline pushed above.
 * An SSE event has no round trip to split, so it is treated as rtt 0: that
 * estimate is late by at most one one-way delay.
 *
 * Transport: EventSource on /api/clock/stream while it is healthy; on error, or
 * after 30 s with no heartbeat (two missed heartbeats), GET /api/clock every 1 s
 * until the stream is back. A 503 is not an exception: Retry-After is honoured
 * and the last known value stays on screen, labelled as such. Resync on
 * visibilitychange, focus and online. A command POST that fails shows the error
 * and leaves the displayed state alone — a command that did not land never looks
 * like it did.
 *
 * Everything below `install()` is dependency-injected and Node-testable.
 */

const CLOCK_KEY = 'cp-ops-clock';
const API_URL = '/api/clock';
const STREAM_URL = '/api/clock/stream';
const POLL_MS = 1000;                /* fallback poll while the stream is down */
const HEARTBEAT_TIMEOUT_MS = 30000;  /* two missed 15 s heartbeats: stream dead */
const RECONNECT_MS = 2000;           /* the retry: the server's stream asks for */
const OFFLINE_AFTER_MS = 10000;      /* no answer this long while polling = offline */
const ERROR_MS = 6000;               /* how long a failed command stays on screen */

const LABELS = Object.freeze({
  en: Object.freeze({
    failed: 'clock command failed — nothing changed',
    busy: 'server busy — retrying'
  }),
  zh: Object.freeze({
    failed: '计时指令失败 — 未改变',
    busy: '服务器繁忙 — 正在重试'
  })
});

/* §12.1: the shot timer has one name in both clocks, and that name has one definition —
 * words.shotTimer in annotator/ops.js, in both languages. This file holds no copy of it: not to
 * paint it, and not to read a language off it. The console publishes the name and the language it
 * is painted in on window.OpsClock (seamNames below), so both facts arrive as data instead of as
 * text that happens to be on screen. */

function labels(lang) {
  return LABELS[lang === 'zh' ? 'zh' : 'en'];
}

function statusText(status, lang, errorText) {
  // The only sentence the bar still says about the clock is a failure (owner §13.3):
  // connecting, live, polling and offline are states, and the bar shows the time instead.
  // The status still matters to the sync layer; it just has no copy of its own any more.
  return errorText || '';
}

/* NTP-style estimate: the server's clock reading minus the midpoint of the
 * request, both endpoints taken from this device's Date.now(). */
function offsetEstimate(serverNowMs, sentMs, receivedMs) {
  return serverNowMs - (sentMs + (receivedMs - sentMs) / 2);
}

/* Milliseconds left on the server's deadline, in this device's clock base. */
function displayMs(state, nowMs, offset) {
  if (!state || !state.running || !Number.isFinite(state.deadline_ms)) return null;
  return state.deadline_ms - (nowMs + offset);
}

/* The server snapshot in the shape ops.js keeps in localStorage — the local
 * deadline is the server deadline minus the measured offset, so ops.js's own
 * clockLeft() computes the shared remaining time with no other change. A
 * deadline already in the past is never re-armed: it would make every device
 * replay the expiry message. */
function toLocalClock(state, nowMs, offset) {
  const duration = Number.isFinite(state.duration) ? state.duration : 30;
  const left = displayMs(state, nowMs, offset);
  if (left !== null && left > 0) return {duration: duration, remaining: left / 1000, deadline: state.deadline_ms - offset};
  if (left !== null) return {duration: duration, remaining: 0, deadline: null};
  const remaining = Math.max(0, (Number.isFinite(state.remaining_ms) ? state.remaining_ms : 0) / 1000);
  return {duration: duration, remaining: remaining, deadline: null};
}

/* What a clock button press means once ops.js has accepted it. `next` is the
 * clock ops.js wrote to localStorage afterwards; a press ops.js refused (the
 * "delayed" guard, or a settings_update that failed) writes nothing, and nothing
 * is sent to the server. */
/* `written` is the clock ops.js WROTE after accepting the press (ops.js flips
 * the deadline, so a fresh deadline is a start and a cleared one is a pause);
 * a press it refused writes nothing and never reaches here. */
function intentFor(action, value, written) {
  if (!written || typeof written !== 'object') return null;
  if (action === 'clock-toggle') return written.deadline ? {action: 'start'} : {action: 'pause'};
  if (action === 'clock-reset') return {action: 'reset'};
  if (action === 'clock-set') return Number(written.duration) === value ? {action: 'set', duration: value} : null;
  return null;
}

function retryAfterMsFrom(response) {
  let raw = null;
  try {
    raw = response && response.headers && response.headers.get ? response.headers.get('Retry-After') : null;
  } catch (error) {
    raw = null;
  }
  const seconds = Number(raw);
  if (!Number.isFinite(seconds) || seconds <= 0) return RECONNECT_MS;
  return Math.min(seconds, 60) * 1000;
}

function parseJson(text) {
  try {
    return JSON.parse(text);
  } catch (error) {
    return null;
  }
}

/* The sync layer itself. Everything it touches outside itself is injected, so
 * tests drive it with fakes instead of a browser. */
function createClockSync(deps) {
  const now = deps.now || function () { return Date.now(); };
  const timers = deps.timers || {
    setTimeout: function (fn, ms) { return setTimeout(fn, ms); },
    setInterval: function (fn, ms) { return setInterval(fn, ms); },
    clearTimeout: function (id) { return clearTimeout(id); },
    clearInterval: function (id) { return clearInterval(id); }
  };
  const request = deps.fetch;
  const openStream = deps.openStream || null;
  const apply = deps.apply || function () {};
  const onStatus = deps.onStatus || function () {};
  const onError = deps.onError || function () {};
  const lang = deps.lang || function () { return 'en'; };
  const apiUrl = deps.apiUrl || API_URL;
  const streamUrl = deps.streamUrl || STREAM_URL;

  let offset = 0;
  let state = null;
  let answered = false;       /* has the server ever answered? */
  let answeredAt = 0;
  let startedAt = 0;
  let beatAt = 0;             /* last stream event; 0 = nothing heard yet */
  let openedAt = 0;           /* when the current stream was opened */
  let stream = null;
  let streamDown = true;
  let pollTimer = null;
  let reconnectTimer = null;
  let watchdogTimer = null;
  let retryAfterMs = 0;
  let busyUntil = 0;
  let status = 'connecting';
  let stopped = true;

  function statusNow() {
    /* "live" means the stream said something recently — an open socket that has
     * not spoken is not a synced device. */
    if (stream && !streamDown && beatAt > 0 && (now() - beatAt) < HEARTBEAT_TIMEOUT_MS) return 'live';
    if (now() - (answered ? answeredAt : startedAt) > OFFLINE_AFTER_MS) return 'offline';
    return answered && pollTimer !== null ? 'polling' : 'connecting';
  }

  function note() {
    const next = statusNow();
    if (next === status) return;
    status = next;
    onStatus(status);
  }

  function adopt(payload, sentMs, receivedMs) {
    if (!payload || typeof payload !== 'object') return null;
    if (Number.isFinite(payload.server_now_ms)) offset = offsetEstimate(payload.server_now_ms, sentMs, receivedMs);
    state = payload;
    answered = true;
    answeredAt = now();
    const local = toLocalClock(payload, now(), offset);
    apply(local, payload);
    note();
    return local;
  }

  async function send(method, body) {
    const sent = now();
    let response;
    try {
      response = await request(apiUrl, body === undefined
        ? {method: method, cache: 'no-store'}
        : {method: method, cache: 'no-store', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    } catch (error) {
      return {ok: false, reason: 'network', error: error};
    }
    const received = now();
    if (response.status === 503) {           /* the bounded server is out of slots */
      retryAfterMs = retryAfterMsFrom(response);
      busyUntil = now() + retryAfterMs;
      note();
      return {ok: false, reason: 'busy'};
    }
    retryAfterMs = 0;
    if (!response.ok) {
      note();
      return {ok: false, reason: 'status', status: response.status};
    }
    let payload;
    try {
      payload = await response.json();
    } catch (error) {
      return {ok: false, reason: 'body', error: error};
    }
    return {ok: true, local: adopt(payload, sent, received)};
  }

  async function resync(reason) {
    const result = await send('GET');
    if (!result.ok) note();
    return result;
  }

  async function intent(action, duration) {
    const result = await send('POST', duration === undefined ? {action: action} : {action: action, duration: duration});
    if (!result.ok) {
      const words = labels(lang());
      onError(result.reason === 'busy' ? words.busy : words.failed, result);
      /* The press may already have flipped this device optimistically; pull the
       * truth back rather than leaving a state the server never accepted. */
      timers.setTimeout(function () { resync('after-failed-command'); }, Math.max(RECONNECT_MS, retryAfterMs));
    }
    return result;
  }

  function clockEvent(payload) {
    const at = now();
    stopPolling();
    adopt(payload, at, at);
  }

  function heartbeatEvent(payload) {
    if (payload && Number.isFinite(payload.server_now_ms)) {
      const at = now();
      offset = offsetEstimate(payload.server_now_ms, at, at);
      if (state) apply(toLocalClock(state, now(), offset), state);
    }
    stopPolling();
    note();
  }

  function startPolling() {
    if (stopped || pollTimer !== null) return;
    pollTimer = timers.setInterval(function () {
      if (now() < busyUntil) return;         /* honour Retry-After */
      resync('poll');
    }, POLL_MS);
  }

  function stopPolling() {
    if (pollTimer === null) return;
    timers.clearInterval(pollTimer);
    pollTimer = null;
  }

  function reconnectLater(delay) {
    if (stopped || !openStream || reconnectTimer !== null) return;
    reconnectTimer = timers.setTimeout(function () {
      reconnectTimer = null;
      if (stopped || stream) return;
      openStreamNow();
    }, delay === undefined ? Math.max(RECONNECT_MS, retryAfterMs) : delay);
  }

  function openStreamNow() {
    if (stopped || !openStream || stream) return;
    streamDown = false;
    beatAt = 0;
    openedAt = now();
    stream = openStream(streamUrl, {
      event: function (payload) {
        openedAt = 0;
        beatAt = now();
        clockEvent(payload);
      },
      heartbeat: function (payload) {
        openedAt = 0;
        beatAt = now();
        heartbeatEvent(payload);
      },
      error: function () { streamFailed(); }
    });
    note();
  }

  function streamFailed() {
    beatAt = 0;
    openedAt = 0;
    streamDown = true;
    if (stream) {
      try { stream.close(); } catch (error) { /* already gone */ }
      stream = null;
    }
    note();
    resync('stream-lost');
    startPolling();
    reconnectLater();
  }

  function checkStream() {
    if (stopped || !stream || streamDown) return;
    const since = beatAt > 0 ? beatAt : openedAt;
    if (since > 0 && now() - since >= HEARTBEAT_TIMEOUT_MS) streamFailed();
  }

  function start() {
    stopped = false;
    startedAt = now();
    answeredAt = startedAt;
    note();
    resync('start');
    openStreamNow();
    if (watchdogTimer === null) watchdogTimer = timers.setInterval(checkStream, HEARTBEAT_TIMEOUT_MS / 3);
  }

  function stop() {
    stopped = true;
    stopPolling();
    if (reconnectTimer !== null) {
      timers.clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (watchdogTimer !== null) {
      timers.clearInterval(watchdogTimer);
      watchdogTimer = null;
    }
    if (stream) {
      try { stream.close(); } catch (error) { /* already gone */ }
      stream = null;
    }
  }

  return {
    start: start,
    stop: stop,
    resync: resync,
    intent: intent,
    status: function () { return status; },
    offset: function () { return offset; },
    state: function () { return state; },
    answered: function () { return answered; }
  };
}

/* -- DOM half ------------------------------------------------------------- */

/* The console publishes what only it knows: the shot timer's one name, and the language that name
 * is painted in (words.shotTimer in annotator/ops.js, handed out as window.OpsClock.words()).
 * Reading it is a call, never a comparison against rendered text. */
function seamNames(win) {
  const seam = win && win.OpsClock;
  const names = seam && typeof seam.words === 'function' ? seam.words() : null;
  return names && (names.lang === 'zh' || names.lang === 'en') ? names : null;
}

function nodeLang(doc, win) {
  // The console answers first, and its answer covers a page whose document element lies.
  const names = seamNames(win);
  if (names) return names.lang;
  // ops.js publishes the language it paints in on the shell (owner §13.2), which is
  // the shell element or its dataset, depending on which DOM is asking.
  const shell = (doc.querySelector && doc.querySelector('#ops-shell')) || (doc.getElementById && doc.getElementById('ops-shell')) || null;
  const published = (shell && ((shell.dataset && shell.dataset.lang) || (shell.getAttribute && shell.getAttribute('lang')))) || '';
  if (published === 'zh' || published === 'en') return published;
  const root = doc.documentElement;
  const attr = ((root && root.getAttribute && root.getAttribute('lang')) || '').toLowerCase();
  return attr.indexOf('zh') === 0 ? 'zh' : 'en';
}

/* The clock's news has one home: annotator/ops.js paints the sync line inside the clock
 * markup it emits itself. This half decides only what the sentence is — a failed or busy command
 * is a fact the operator has to see, while connecting/live/polling/offline are states the bar no
 * longer narrates (owner §13.3) — and hands it over on the seam. The label above the digits is
 * never rewritten, no node is created, and nothing is read back out of the page. */
function announce(win, status, errorText) {
  const seam = win && win.OpsClock;
  if (!seam || typeof seam.sync !== 'function') return;
  seam.sync(statusText(status, nodeLang(win.document, win), errorText));
}

// The console publishes one named seam for the clock: annotator/ops.js sets window.OpsClock with a
// receive() that takes the same string a storage event carries in newValue. The one page that loads
// this file, annotator/ops.html, defers ops.js before it, so the seam is always there first. No
// synthetic StorageEvent is dispatched, and no page without ops.js is served (checked: only
// annotator/ops.html loads this file).
function pushToOps(win, local) {
  const value = JSON.stringify(local);
  const seam = win.OpsClock;
  if (seam && typeof seam.receive === 'function') seam.receive(value);
}

function openEventStream(win, url, handlers) {
  const source = new win.EventSource(url);
  source.addEventListener('clock', function (event) { handlers.event(parseJson(event.data)); });
  source.addEventListener('heartbeat', function (event) { handlers.heartbeat(parseJson(event.data)); });
  source.addEventListener('error', function () { handlers.error(); });
  return {
    close: function () {
      try { source.close(); } catch (error) { /* already gone */ }
    }
  };
}

function install(win) {
  if (!win || !win.document) return null;
  if (win.__clockSync) return win.__clockSync;
  const doc = win.document;
  let errorText = null;
  let errorTimer = null;

  function paint() {
    announce(win, win.__clockSync ? win.__clockSync.status() : 'connecting', errorText);
  }

  const sync = createClockSync({
    now: function () { return Date.now(); },
    timers: {
      setTimeout: function (fn, ms) { return win.setTimeout(fn, ms); },
      setInterval: function (fn, ms) { return win.setInterval(fn, ms); },
      clearTimeout: function (id) { return win.clearTimeout(id); },
      clearInterval: function (id) { return win.clearInterval(id); }
    },
    fetch: function (url, options) { return win.fetch(url, options); },
    openStream: function (url, handlers) { return openEventStream(win, url, handlers); },
    apply: function (local) { pushToOps(win, local); paint(); },
    onStatus: function () { paint(); },
    onError: function (text) {
      errorText = text;
      if (errorTimer !== null) win.clearTimeout(errorTimer);
      errorTimer = win.setTimeout(function () { errorText = null; errorTimer = null; paint(); }, ERROR_MS);
      paint();
    },
    lang: function () { return nodeLang(doc, win); }
  });

  win.__clockSync = sync;
  sync.start();

  win.addEventListener('focus', function () { sync.resync('focus'); });
  win.addEventListener('online', function () { sync.resync('online'); });
  doc.addEventListener('visibilitychange', function () {
    if (!doc.hidden) sync.resync('visibilitychange');
  });

  /* An accepted press is the console's news, not something to be inferred afterwards. ops.js
   * calls window.OpsClock.onAccepted(action, value, timer) in the very branches that write its
   * own clock, so a press it refuses (the "delayed" guard) is never reported — the same
   * condition the old store watch could only guess at, without reading the store at all. The
   * seam is there to be widened because annotator/ops.html defers ops.js before this file. */
  const seam = win.OpsClock;
  if (seam) {
    seam.onAccepted = function (action, value, written) {
      const intent = intentFor(action, value, written);
      if (intent) sync.intent(intent.action, intent.duration);
    };
  }

  paint();
  return sync;
}

const api = {
  CLOCK_KEY: CLOCK_KEY,
  API_URL: API_URL,
  STREAM_URL: STREAM_URL,
  POLL_MS: POLL_MS,
  HEARTBEAT_TIMEOUT_MS: HEARTBEAT_TIMEOUT_MS,
  OFFLINE_AFTER_MS: OFFLINE_AFTER_MS,
  LABELS: LABELS,
  labels: labels,
  statusText: statusText,
  offsetEstimate: offsetEstimate,
  displayMs: displayMs,
  toLocalClock: toLocalClock,
  intentFor: intentFor,
  retryAfterMsFrom: retryAfterMsFrom,
  createClockSync: createClockSync,
  seamNames: seamNames,
  nodeLang: nodeLang,
  announce: announce,
  install: install
};

if (typeof module === 'object' && module.exports) module.exports = api;
if (typeof window !== 'undefined' && window) window.ClockSync = api;

if (typeof document !== 'undefined' && typeof window !== 'undefined' && window) {
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { install(window); });
  else install(window);
}
