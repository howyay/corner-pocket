'use strict';
/* Corner Pocket, the public board (docs/public-board.md): tonight's tables, what is
   next, the bracket and tonight's table, for the hall's TV and players' phones.
   Read-only: the one control is the language toggle. It polls the API beside the page
   once per POLL_MS with the last ETag and never looks fresher than its last good answer. Every
   URL is built from the mount that served the page, so one file works at "/", at
   "/board/" (--public-prefix) and at the console's own "/display".
   The core is DOM-free, so tests/test_board.js renders and ages it under node
   with an injected clock; start() wires it to the page. */
(function (factory) {
  const board = factory();
  if (typeof module === 'object' && module.exports) module.exports = board;
  else board.start(window);
}(function () {
  const POLL_MS = 3000, STALE_MS = 15000, TIMEOUT_MS = 8000;
  // A card older than this stops presenting its number as the length of a match in
  // progress: two hours on one table is likelier to be a record nobody closed than a
  // frame still being played, so the card asks for a look instead of counting on.
  const ATTENTION_MS = 2 * 60 * 60 * 1000;
  const WORDS = {
    en: {
      tonight: 'Tonight', tables: 'On the tables', next: 'Next up', bracket: 'Bracket', standings: 'Tonight’s table',
      player: 'Player', team: 'Team', won: 'W', lost: 'L', played: 'Played',
      tableN: 'Table {n}', round: 'Round {n}', final: 'Final', semi: 'Semi-finals', quarter: 'Quarter-finals',
      singles: 'Singles', doubles: 'Doubles', raceTo: 'Race to {n}',
      registration: 'Registration open', active: 'In progress', complete: 'Finished',
      bye: 'Bye', tbd: 'To be decided', vs: 'vs', forfeit: 'Forfeit', ready: 'Ready', held: 'Waiting for a player',
      live: 'On table {n}', champion: 'Champion',
      noTables: 'No match on a table right now', noNext: 'Nothing queued', noBracket: 'The draw has not been made yet',
      noStandings: 'No entrants yet',
      timeOnTable: 'Time on table', checkTable: 'check the table',
      underMinute: 'Just started', minutes: '{n} min', hours: '{h} h {m} min',
      connecting: 'Connecting…', updatedNow: 'Updated just now', updatedS: 'Updated {n} s ago',
      updatedM: 'Updated {n} min ago', reconnecting: 'Reconnecting — showing the last known board',
      reconnectingEmpty: 'Reconnecting…', off: 'The board is off tonight',
      source: 'Source code · AGPL-3.0',
    },
    zh: {
      tonight: '今晚', tables: '台上比赛', next: '即将上台', bracket: '对阵图', standings: '今晚战绩',
      player: '球员', team: '队伍', won: '胜', lost: '负', played: '场次',
      tableN: '{n} 号台', round: '第 {n} 轮', final: '决赛', semi: '半决赛', quarter: '四分之一决赛',
      singles: '单打', doubles: '双打', raceTo: '抢{n}',
      registration: '报名中', active: '进行中', complete: '已结束',
      bye: '轮空', tbd: '待定', vs: '对', forfeit: '弃权', ready: '准备上台', held: '等待球员到场',
      live: '{n} 号台', champion: '冠军',
      noTables: '目前没有台上比赛', noNext: '暂无排队的比赛', noBracket: '尚未抽签', noStandings: '暂无报名',
      timeOnTable: '台上时长', checkTable: '请核对',
      underMinute: '刚开始', minutes: '{n} 分钟', hours: '{h} 小时 {m} 分',
      connecting: '正在连接…', updatedNow: '刚刚更新', updatedS: '{n} 秒前更新', updatedM: '{n} 分钟前更新',
      reconnecting: '正在重新连接 — 显示的是最后一次收到的记分板', reconnectingEmpty: '正在重新连接…',
      off: '今晚记分板已关闭',
      source: '源码 · AGPL-3.0',
    },
  };

  /** The words a match may carry, with the module that owns them: annotator/operations.py
      MATCH_STATUSES and MATCH_RESULTS, the tuples that module is the only writer of. A browser
      cannot import python, and this repository has no build step, so board.js keeps the one copy
      on this side of the wire. Every branch below reads this table; none compares a status or a
      result against a literal. tests/test_board.js reads both tuples back out of that file and
      fails on a difference, the way tests/test_app_timeline.js:3252 holds the console's live
      codes to annotator/live_processing.py.
      The board branches on live, delayed and complete, and on played, forfeit and bye. The copy
      carries the whole list anyway: a word added to the registry then shows up here, and in the
      stylesheet that receives it as a class (board.css). */
  const STATUS = {pending: 'pending', scheduled: 'scheduled', live: 'live', delayed: 'delayed', complete: 'complete'};
  const RESULT = {played: 'played', forfeit: 'forfeit', bye: 'bye'};

  /** Escapes one value for HTML. An absent value (null or undefined) becomes no text.
      The payload comes from another program as JSON. A field that program leaves out
      must show an empty cell. It must never show the word "undefined" on a TV.
      Same contract as the console's own helper (annotator/app.js:17). */
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  /** Fills the {name} holes of one word of WORDS. This function is the only
      substitution engine on the board. A caller that passes a value for an HTML hole
      escapes that value first. Every other caller passes plain text. A key that WORDS
      does not carry returns undefined, and esc() then makes no text of it. */
  function say(lang, key, values) {
    const text = (WORDS[lang] || WORDS.en)[key];
    return values && text ? text.replace(/\{(\w+)\}/g, (_, name) => values[name]) : text;
  }

  /** The layout bucket for a count of tables in play (board.css). Each count up to
      MAX_TABLE_COLS keeps its own name, so no count falls back to the one-column
      default. A count above MAX_TABLE_COLS says "many". tests/test_board.js holds the
      stylesheet to exactly this list. */
  const MAX_TABLE_COLS = 8;
  const countBucket = n => n <= MAX_TABLE_COLS ? String(Math.max(0, n)) : 'many';

  /** 'en' or 'zh': ?lang= wins, else the browser's first language. */
  function pickLang(search, languages) {
    const asked = new URLSearchParams(search || '').get('lang');
    if (asked === 'en' || asked === 'zh') return asked;
    return /^zh\b/i.test((languages || []).find(Boolean) || '') ? 'zh' : 'en';
  }

  function duration(ms, lang) {
    const minutes = Math.floor(Math.max(0, ms) / 60000);
    if (minutes < 1) return say(lang, 'underMinute');
    if (minutes < 60) return say(lang, 'minutes', {n: minutes});
    return say(lang, 'hours', {h: Math.floor(minutes / 60), m: String(minutes % 60).padStart(2, '0')});
  }

  /** "Final", "Semi-finals", "Quarter-finals" for a knockout's last rounds, else "Round N". */
  function roundName(rounds, number, lang) {
    const index = rounds.findIndex(r => r.round === number);
    const fromEnd = rounds.length - 1 - index, count = index < 0 ? 0 : rounds[index].matches.length;
    if (index >= 0 && count === 1 << fromEnd && fromEnd <= 2) return say(lang, ['final', 'semi', 'quarter'][fromEnd]);
    return say(lang, 'round', {n: number});
  }

  const sideName = (side, lang) => side.name != null ? esc(side.name)
    : `<span class="placeholder">${esc(say(lang, side.bye ? 'bye' : 'tbd'))}</span>`;

  function tableCard(m, lang, round, elapsed) {
    const lead = m.score[0] === m.score[1] ? -1 : m.score[0] > m.score[1] ? 0 : 1;
    const side = i => `<p class="side${lead === i ? ' lead' : ''}"><span class="name">${sideName(m.sides[i], lang)}</span>` +
      `<span class="score">${esc(m.score[i])}</span></p>`;
    /** The number is the match's time on its table (labelled by #tables-note). Past
        ATTENTION_MS it says so: the card turns amber and carries the words, so the
        signal survives a greyscale screenshot and a screen reader. data-elapsed is the
        same number in milliseconds, for a check that needs a finer reading than the
        printed minutes: the board's own tests age the DOM-free core with a clock. */
    const late = elapsed != null && elapsed >= ATTENTION_MS;
    const time = elapsed == null ? '' : `<span class="on-table${late ? ' late' : ''}">${esc(duration(elapsed, lang))}` +
      `${late ? `<span class="check">${esc(say(lang, 'checkTable'))}</span>` : ''}</span>`;
    // Shot-clock seam. The board shows no shot clock yet, on purpose: the only clock
    // today is ops.js's per-browser one, which nothing shares, so a clock drawn here
    // would be a guess. When the shared shot clock reaches main, /api/board gains a
    // per-table clock field and its face goes here, between the scores and the foot.
    return `<li class="table-card${late ? ' late' : ''}"${elapsed == null ? '' : ` data-elapsed="${Math.round(elapsed)}"`}>` +
      `<p class="table-no">${say(lang, 'tableN', {n: `<b>${esc(m.table)}</b>`})}</p>` +
      `${side(0)}${side(1)}<p class="card-foot"><span>${esc(round)}</span>${time}</p></li>`;
  }

  function nextItem(m, lang, round) {
    const held = m.status === STATUS.delayed;
    return `<li class="next-item${held ? ' held' : ''}"><span class="names">${sideName(m.sides[0], lang)} ` +
      `<span class="vs">${esc(say(lang, 'vs'))}</span> ${sideName(m.sides[1], lang)}</span>` +
      `<span class="detail">${esc(round)} · ${esc(say(lang, held ? 'held' : 'ready'))}</span></li>`;
  }

  function bracketMatch(m, lang) {
    const scored = m.status === STATUS.live || (m.status === STATUS.complete && m.result === RESULT.played);
    const side = i => `<p class="bs${m.winner === i ? ' won' : ''}"><span class="name">${sideName(m.sides[i], lang)}</span>` +
      `<span class="score">${scored ? esc(m.score[i]) : ''}</span></p>`;
    const note = m.status === STATUS.live ? say(lang, 'live', {n: m.table}) : m.result === RESULT.forfeit ? say(lang, 'forfeit')
      : m.status === STATUS.delayed ? say(lang, 'held') : '';
    return `<li class="bm ${esc(m.status)}${m.result === RESULT.bye ? ' bye' : ''}">${side(0)}${side(1)}` +
      `${note ? `<p class="bm-note">${esc(note)}</p>` : ''}</li>`;
  }

  /** Everything the page shows for one board payload, as text and escaped HTML.
      elapsedOf(match) is the match's time on its table in ms, or null. */
  function render(board, lang, elapsedOf) {
    const rounds = board.bracket || [], event = board.event;
    const final = rounds.length ? rounds[rounds.length - 1].matches[0] : null;
    // event.phase is the night's own word (annotator/operations.py tournament(): 'registration',
    // 'active', 'complete'), a different vocabulary from a match's. No tuple publishes it, so it
    // keeps its literal here; this is not STATUS.complete.
    const winner = event.phase === 'complete' && final && final.winner != null ? final.sides[final.winner].name : null;
    let tables = `<li class="empty">${esc(say(lang, 'noTables'))}</li>`;
    if (winner != null) {
      tables = `<li class="champion"><p class="label">${esc(say(lang, 'champion'))}</p><p class="name">${esc(winner)}</p></li>`;
    } else if (board.tables.length) {
      tables = board.tables.map(m => tableCard(m, lang, roundName(rounds, m.round, lang), elapsedOf(m))).join('');
    }
    const standings = board.standings.map(r => `<tr><th scope="row">${esc(r.name)}</th><td>${esc(r.won)}</td>` +
      `<td>${esc(r.lost)}</td><td>${esc(r.played)}</td></tr>`).join('');
    return {
      title: event.name || say(lang, 'tonight'),
      meta: [say(lang, event.format === 'doubles' ? 'doubles' : 'singles'), say(lang, 'raceTo', {n: event.race_to}),
        say(lang, event.phase)].filter(Boolean).join(' · '),
      player: say(lang, event.format === 'doubles' ? 'team' : 'player'),
      tables, tableCount: winner != null ? 1 : board.tables.length,
      // What a card's number measures, on screen beside it: the board is read from
      // across a room, so the label sits once above the cards instead of on each one.
      tablesNote: winner == null && board.tables.length ? say(lang, 'timeOnTable') : '',
      next: board.next.length ? board.next.map(m => nextItem(m, lang, roundName(rounds, m.round, lang))).join('')
        : `<li class="empty">${esc(say(lang, 'noNext'))}</li>`,
      bracket: rounds.length ? rounds.map(r => `<section class="round${r.matches.every(m => m.status === STATUS.complete) ? ' done' : ''}">` +
        `<h3>${esc(roundName(rounds, r.round, lang))}</h3><ol>${r.matches.map(m => bracketMatch(m, lang)).join('')}</ol></section>`).join('')
        : `<p class="empty">${esc(say(lang, 'noBracket'))}</p>`,
      // The TV hides byes (the next round shows who went through): its tallest column.
      bracketRows: Math.max(0, ...rounds.map(r => r.matches.filter(m => m.result !== RESULT.bye).length)),
      standings: standings || `<tr class="empty"><td colspan="4">${esc(say(lang, 'noStandings'))}</td></tr>`,
      standingRows: board.standings.length,
    };
  }

  /** How old the board on screen is. Stale once STALE_MS pass without a good answer
      (a 304 counts: the server confirmed nothing changed). */
  function freshness(state, now, lang) {
    const since = state.lastSuccess == null ? null : now - state.lastSuccess;
    const stale = now - (since == null ? state.startedAt : state.lastSuccess) >= STALE_MS;
    const updated = since == null ? say(lang, 'connecting') : since < 2000 ? say(lang, 'updatedNow')
      : since < 60000 ? say(lang, 'updatedS', {n: Math.floor(since / 1000)}) : say(lang, 'updatedM', {n: Math.floor(since / 60000)});
    return {updated, stale, message: stale ? say(lang, state.board ? 'reconnecting' : 'reconnectingEmpty') : ''};
  }

  /** The API beside the page, built from the script's own URL rather than the
      document's: "/board/" keeps it under the mount, while the console's own
      "/display" mount resolves to /api/board. Only the script's URL tells those
      two apart, so one file serves every mount (--public-prefix). */
  function apiUrl(scriptUrl) {
    return new URL('api/board', scriptUrl).href;
  }

  /** One conditional GET per poll(). The state keeps the last good board, its ETag,
      and when (by now()) it was received and last confirmed. url comes from apiUrl. */
  function createPoller({fetch, now, url}) {
    const state = {etag: null, board: null, receivedAt: null, lastSuccess: null, startedAt: now()};
    async function poll() {
      const controller = typeof AbortController === 'function' ? new AbortController() : null;
      const timer = controller && setTimeout(() => controller.abort(), TIMEOUT_MS);
      try {
        const headers = state.board && state.etag ? {'If-None-Match': state.etag} : {};
        const response = await fetch(url, {headers, cache: 'no-store', signal: controller ? controller.signal : undefined});
        if (response.status === 304 && state.board) {
          state.lastSuccess = now();
          return 'same';
        }
        if (response.status !== 200) return 'failed';
        const board = await response.json();
        if (!board || (board.board !== 'on' && board.board !== 'off')) return 'failed';
        Object.assign(state, {board, etag: response.headers.get('ETag'), receivedAt: now()});
        state.lastSuccess = state.receivedAt;
        return 'new';
      } catch (error) {
        return 'failed';  // offline, timed out, or not JSON: keep the last board; freshness() says how old it is
      } finally {
        if (timer) clearTimeout(timer);
      }
    }
    return {state, poll};
  }

  /** A live match's time on its table, by the server's clock: the server said how long
      at served_at, and this device's clock only adds the time since that answer. Once
      the board itself is stale that addition is a guess, so the number stops at the last
      answer the server confirmed instead of counting on without it. */
  function elapsedOf(state, now) {
    const served = Date.parse(state.board && state.board.served_at);
    const confirmed = state.lastSuccess != null && now - state.lastSuccess >= STALE_MS ? state.lastSuccess : now;
    return m => {
      const since = Date.parse(m.since);
      return Number.isFinite(served) && Number.isFinite(since) ? served - since + (confirmed - state.receivedAt) : null;
    };
  }

  function start(win) {
    const doc = win.document, nav = win.navigator || {}, $ = id => doc.getElementById(id);
    const clock = () => Date.now();
    const script = doc.currentScript || (doc.querySelector ? doc.querySelector('script[src]') : null);
    const poller = createPoller({fetch: (...args) => win.fetch(...args), now: clock,
      url: apiUrl(script ? script.src : win.location.href)});
    let lang = pickLang(win.location.search, nav.languages && nav.languages.length ? nav.languages : [nav.language]);
    const shown = {};
    const html = (id, value) => { if (shown[id] !== value) $(id).innerHTML = shown[id] = value; };
    const text = (id, value) => { if ($(id).textContent !== value) $(id).textContent = value; };
    const labels = [['tables-title', 'tables'], ['next-title', 'next'], ['bracket-title', 'bracket'],
      ['standings-title', 'standings'], ['h-won', 'won'], ['h-lost', 'lost'], ['h-played', 'played'], ['off-text', 'off'],
      ['source-link', 'source']];

    function paint() {
      const state = poller.state, board = state.board, now = clock(), fresh = freshness(state, now, lang);
      doc.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
      const toggle = $('lang');
      toggle.textContent = lang === 'zh' ? 'EN' : '中';
      toggle.lang = lang === 'zh' ? 'en' : 'zh';
      toggle.setAttribute('aria-label', lang === 'zh' ? 'English' : '中文');
      for (const [id, key] of labels) text(id, say(lang, key));
      text('updated', fresh.updated);
      text('stale', fresh.message);
      $('stale').hidden = !fresh.stale;
      doc.body.classList.toggle('is-stale', fresh.stale);
      const off = Boolean(board) && board.board === 'off';
      $('off').hidden = !off;
      $('board').hidden = off;
      if (!board || off) {
        text('event-name', say(lang, 'tonight'));
        text('event-meta', '');
        doc.title = `Corner Pocket · ${say(lang, 'tonight')}`;
        return;
      }
      const view = render(board, lang, elapsedOf(state, now));
      text('event-name', view.title);
      text('event-meta', view.meta);
      text('h-player', view.player);
      doc.title = `Corner Pocket · ${view.title}`;
      html('tables', view.tables);
      text('tables-note', view.tablesNote);
      $('tables-note').hidden = !view.tablesNote;
      html('next', view.next);
      html('bracket', view.bracket);
      html('standings', view.standings);
      // Layout buckets for the TV, which cannot scroll (board.css).
      const n = view.tableCount;
      $('tables').dataset.count = countBucket(n);
      $('bracket').dataset.rows = view.bracketRows > 8 ? 'many' : view.bracketRows > 4 ? 'some' : 'few';
      $('standings').dataset.rows = view.standingRows > 16 ? 'many' : view.standingRows > 12 ? 'some' : 'few';
      $('board').setAttribute('aria-busy', 'false');
    }

    let timer = null, polling = false;
    async function cycle() {
      if (polling) return;  // the poll in flight schedules the next one
      polling = true;
      win.clearTimeout(timer);
      try {
        await poller.poll();
      } finally {
        polling = false;
      }
      paint();
      timer = win.setTimeout(cycle, POLL_MS);
    }

    let wakeLock = null;
    async function keepAwake() {
      // The TV must not dim mid-match. Where the API is missing or the browser refuses,
      // the screen keeps its own settings; nothing else depends on it.
      if (wakeLock || doc.visibilityState !== 'visible' || !nav.wakeLock || typeof nav.wakeLock.request !== 'function') return;
      try {
        wakeLock = await nav.wakeLock.request('screen');
        if (wakeLock && typeof wakeLock.addEventListener === 'function') {
          wakeLock.addEventListener('release', () => { wakeLock = null; });
        }
      } catch (error) {
        wakeLock = null;
      }
    }

    $('lang').addEventListener('click', () => {
      lang = lang === 'zh' ? 'en' : 'zh';
      try {  // keep the choice in the address, so a reload or a bookmark keeps it
        const url = new URL(win.location.href);
        url.searchParams.set('lang', lang);
        win.history.replaceState(null, '', url);
      } catch (error) { /* the page works without it */ }
      paint();
    });
    doc.addEventListener('visibilitychange', () => {
      if (doc.visibilityState === 'visible') {
        keepAwake();
        cycle();  // a phone that wakes asks at once, not after one poll interval
      }
    });
    paint();
    keepAwake();
    cycle();
    win.setInterval(paint, 1000);
    return {poller, paint, lang: () => lang};
  }

  return {WORDS, STATUS, RESULT, POLL_MS, MAX_TABLE_COLS, STALE_MS, esc, say, countBucket, pickLang, duration, roundName, render, freshness, apiUrl, createPoller, elapsedOf, start};
}));
