'use strict';
/* The shared shot clock — client half. Server half: annotator/shot_clock.py with
 * GET/POST /api/clock and GET /api/clock/stream in annotator/unified_server.py.
 *
 * ops.js owns the clock's DOM: one closure-private `timer`, one 200 ms interval
 * that repaints every [data-clock] / [data-progress], and the strip, the floor
 * scoreboard and the vision stage bar all painted from that same `timer`. That
 * closure is unreachable from outside — ops.js is a single IIFE that exports
 * nothing — but it already publishes the seam another device needs:
 *
 *   window.addEventListener('storage', e => { if (e.key === 'cp-ops-clock') {
 *     const next = JSON.parse(e.newValue) || timer;
 *     const durationChanged = next.duration !== timer.duration;
 *     timer = next; durationChanged ? render() : tick(); } });
 *
 * So this module hands ops.js a clock whose deadline is expressed in *this
 * device's* clock base (server deadline − measured offset) by dispatching that
 * same storage event. ops.js stays the only painter, so its single interval and
 * "every view shows the same instant" still hold, and it needs no edit here.
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
const WATCH_MS = 2000;               /* ops.js may await settings_update first */
const WATCH_EVERY_MS = 50;
const DECORATE_MS = 50;              /* coalesce decoration after ops.js renders */
const ERROR_MS = 6000;               /* how long a failed command stays on screen */

const LABELS = Object.freeze({
  en: Object.freeze({
    kicker: 'Shot timer',
    failed: 'clock command failed — nothing changed',
    busy: 'server busy — retrying'
  }),
  zh: Object.freeze({
    kicker: '出杆计时',
    failed: '计时指令失败 — 未改变',
    busy: '服务器繁忙 — 正在重试'
  })
});

/* The two strings ops.js still paints on every render. They are replaced at the
 * DOM level (see decorate) because `words` is closure-private and ops.js is not
 * ours to edit; matching the exact text is also how decorate knows which
 * language the surrounding chrome is in. §12.1: the shot timer has one name in
 * both clocks, so the "lie" and the honest label are the same two words — the
 * machine/local difference is carried by the sync-state line, never by a label. */
const LOCAL_TIMER_LIE = Object.freeze([
  'Shot timer',
  '出杆计时'
]);

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

function nodeLang(doc, holder) {
  // ops.js publishes the language it paints in on the shell (owner §13.2), which is
  // the shell element or its dataset, depending on which DOM is asking.
  const shell = (doc.querySelector && doc.querySelector('#ops-shell')) || (doc.getElementById && doc.getElementById('ops-shell')) || null;
  const published = (shell && ((shell.dataset && shell.dataset.lang) || (shell.getAttribute && shell.getAttribute('lang')))) || '';
  if (published === 'zh' || published === 'en') return published;
  const root = doc.documentElement;
  const attr = ((root && root.getAttribute && root.getAttribute('lang')) || '').toLowerCase();
  if (attr) return attr.indexOf('zh') === 0 ? 'zh' : 'en';
  // Last resort for a page that publishes neither: the one label the shell paints.
  const kicker = holder.querySelector ? holder.querySelector('.kicker') : null;
  const sample = ((kicker && kicker.textContent) || (holder.getAttribute && holder.getAttribute('title')) || '').trim();
  if (sample === LOCAL_TIMER_LIE[1]) return 'zh';
  if (sample === LOCAL_TIMER_LIE[0]) return 'en';
  return 'en';
}

/* One idempotent pass over the clock mounts ops.js renders (the bar's timer slot, the
 * floor scoreboard, the vision stage bar): adopt the shell's one shot-timer name in the
 * whitelisted label, and speak only when something is wrong — a failed or busy command
 * is a fact the operator has to see, while connecting/live/polling/offline are states the
 * bar no longer narrates (owner §13.3). Re-running it after any render is safe. */
function decorate(doc, status, errorText) {
  const nodes = doc.querySelectorAll('[data-clock]');
  for (let i = 0; i < nodes.length; i++) {
    const clockNode = nodes[i];
    const holder = (clockNode.closest && clockNode.closest('.vs-clock')) || clockNode.parentElement;
    if (!holder) continue;
    const lang = nodeLang(doc, holder);
    const words = labels(lang);
    const kicker = holder.querySelector ? holder.querySelector('.kicker') : null;
    if (kicker && LOCAL_TIMER_LIE.indexOf(kicker.textContent.trim()) >= 0) kicker.textContent = words.kicker;
    if (holder.getAttribute && LOCAL_TIMER_LIE.indexOf((holder.getAttribute('title') || '').trim()) >= 0) {
      holder.setAttribute('title', words.kicker);
    }
    const text = statusText(status, lang, errorText);
    let line = holder.querySelector ? holder.querySelector('.sync-error') : null;
    if (!line && text) {
      line = doc.createElement('span');
      line.className = 'sync-error';
      line.setAttribute('hidden', '');
      if (holder.appendChild) holder.appendChild(line);
    }
    if (line) {
      if (line.textContent !== text) line.textContent = text;
      if (text) {
        if (line.removeAttribute) line.removeAttribute('hidden');
        else line.hidden = false;
        if (line.classList && line.classList.add) line.classList.add('low');
      } else {
        if (line.setAttribute) line.setAttribute('hidden', '');
        else line.hidden = true;
        if (line.classList && line.classList.remove) line.classList.remove('low');
      }
    }
    // The retired sync line is not left behind on a page that still carries one.
    const stale = holder.querySelector ? holder.querySelector('.muted[data-clock-sync]') : null;
    if (stale && stale.parentNode && stale.parentNode.removeChild) stale.parentNode.removeChild(stale);
  }
}

function pushToOps(win, local) {
  const value = JSON.stringify(local);
  let event = null;
  try {
    event = new win.StorageEvent('storage', {key: CLOCK_KEY, newValue: value, oldValue: null, url: win.location ? win.location.href : '', storageArea: null});
  } catch (error) {
    event = null;
  }
  if (!event) {
    event = new win.Event('storage');
    event.key = CLOCK_KEY;
    event.newValue = value;
  }
  win.dispatchEvent(event);
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
    decorate(doc, win.__clockSync ? win.__clockSync.status() : 'connecting', errorText);
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
    lang: function () {
      const nodes = doc.querySelectorAll('[data-clock]');
      const holder = nodes.length ? ((nodes[0].closest && nodes[0].closest('.vs-clock')) || nodes[0].parentElement) : null;
      return holder ? nodeLang(doc, holder) : 'en';
    }
  });

  win.__clockSync = sync;
  sync.start();

  win.addEventListener('focus', function () { sync.resync('focus'); });
  win.addEventListener('online', function () { sync.resync('online'); });
  doc.addEventListener('visibilitychange', function () {
    if (!doc.hidden) sync.resync('visibilitychange');
  });

  /* A click on a clock button is mirrored to the server only once ops.js has
   * accepted it — which it shows by writing its own clock to localStorage
   * (a refused press, e.g. the "delayed" guard, writes nothing). Capture phase:
   * this listener must read the old value before ops.js's bubble handler runs. */
  function readStore() {
    try {
      return win.localStorage.getItem(CLOCK_KEY);
    } catch (error) {
      return null;
    }
  }
  function watchLocalWrite(action, value, before) {
    const deadline = Date.now() + WATCH_MS;
    function check() {
      const current = readStore();
      if (current !== before) {
        const next = parseJson(current);
        const intent = intentFor(action, value, next);
        if (intent) sync.intent(intent.action, intent.duration);
        return true;
      }
      return Date.now() > deadline;
    }
    if (check()) return;
    const timer = win.setInterval(function () {
      if (check()) win.clearInterval(timer);
    }, WATCH_EVERY_MS);
  }
  doc.addEventListener('click', function (event) {
    const target = event.target;
    const button = target && target.closest ? target.closest('[data-action^="clock-"]') : null;
    if (!button) return;
    const action = button.dataset ? button.dataset.action : button.getAttribute('data-action');
    const raw = button.dataset ? button.dataset.value : button.getAttribute('data-value');
    const value = raw === null || raw === undefined || raw === '' ? undefined : Number(raw);
    const before = readStore();
    win.setTimeout(function () { watchLocalWrite(action, value, before); }, 0);
  }, true);

  /* ops.js rebuilds its views on every render, so the honest labels and the
   * sync line have to be re-applied whenever it does. */
  if (win.MutationObserver) {
    let pending = null;
    const observer = new win.MutationObserver(function () {
      if (pending !== null) return;
      pending = win.setTimeout(function () { pending = null; paint(); }, DECORATE_MS);
    });
    observer.observe(doc.body || doc.documentElement, {childList: true, subtree: true, characterData: true});
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
  LOCAL_TIMER_LIE: LOCAL_TIMER_LIE,
  labels: labels,
  statusText: statusText,
  offsetEstimate: offsetEstimate,
  displayMs: displayMs,
  toLocalClock: toLocalClock,
  intentFor: intentFor,
  retryAfterMsFrom: retryAfterMsFrom,
  createClockSync: createClockSync,
  decorate: decorate,
  install: install
};

if (typeof module === 'object' && module.exports) module.exports = api;
if (typeof window !== 'undefined' && window) window.ClockSync = api;

if (typeof document !== 'undefined' && typeof window !== 'undefined' && window) {
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { install(window); });
  else install(window);
}
