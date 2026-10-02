'use strict';
// Run: node --test tests/test_board.js. The public board's script, with no DOM or network:
// rendering in EN and 中, the stale indicator on an injected clock, the ETag poller, and
// start() against a fake page with and without a screen wake lock.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const board = require('../annotator/board.js');

const match = (slot, round, a, b, extra = {}) => ({slot, round, sides: [a, b], score: [0, 0], status: 'pending', winner: null, ...extra});
const SAMPLE = {
  board: 'on', revision: 40, served_at: '2026-09-29T19:12:30+00:00',
  event: {name: 'Friday 8-Ball', format: 'singles', race_to: 3, phase: 'active'},
  tables: [match('r2m1', 2, {name: 'Ana'}, {name: 'Bo'}, {score: [2, 1], status: 'live', table: 1, since: '2026-09-29T19:00:00+00:00'})],
  next: [match('r2m2', 2, {name: 'Cy'}, {name: 'Gina Park'}, {status: 'delayed'})],
  bracket: [
    {round: 1, matches: [
      match('r1m1', 1, {name: 'Ana'}, {bye: true}, {status: 'complete', winner: 0, result: 'bye'}),
      match('r1m2', 1, {name: 'Bo'}, {bye: true}, {status: 'complete', winner: 0, result: 'bye'}),
      match('r1m3', 1, {name: 'Cy'}, {name: 'Dee'}, {status: 'complete', winner: 0, result: 'played', score: [3, 1]}),
      match('r1m4', 1, {name: 'Gina Park'}, {name: 'Eve'}, {status: 'complete', winner: 0, result: 'forfeit'})]},
    {round: 2, matches: [
      match('r2m1', 2, {name: 'Ana'}, {name: 'Bo'}, {score: [2, 1], status: 'live', table: 1, since: '2026-09-29T19:00:00+00:00'}),
      match('r2m2', 2, {name: 'Cy'}, {name: 'Gina Park'}, {status: 'delayed'})]},
    {round: 3, matches: [match('r3m1', 3, {tbd: true}, {tbd: true})]}],
  standings: [{name: 'Cy', won: 1, lost: 0, played: 1}, {name: 'Gina Park', won: 1, lost: 0, played: 1},
    {name: 'Dee', won: 0, lost: 1, played: 1}, {name: 'Eve', won: 0, lost: 1, played: 1},
    {name: 'Ana', won: 0, lost: 0, played: 0}, {name: 'Bo', won: 0, lost: 0, played: 0}],
};
const text = html => html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
const twelveMinutes = () => 12.5 * 60000;

test('renders the board in English', () => {
  const view = board.render(SAMPLE, 'en', twelveMinutes);
  assert.equal(view.title, 'Friday 8-Ball');
  assert.equal(view.meta, 'Singles · Race to 3 · In progress');
  assert.equal(view.player, 'Player');
  assert.equal(text(view.tables), 'Table 1 Ana 2 Bo 1 Semi-finals 12 min');
  assert.match(view.tables, /class="side lead"><span class="name">Ana/);
  assert.equal(text(view.next), 'Cy vs Gina Park Semi-finals · Waiting for a player');
  assert.equal(text(view.bracket), 'Quarter-finals Ana Bye Bo Bye Cy 3 Dee 1 Gina Park Eve Forfeit ' +
    'Semi-finals Ana 2 Bo 1 On table 1 Cy Gina Park Waiting for a player Final To be decided To be decided');
  assert.equal(text(view.standings), 'Cy 1 0 1 Gina Park 1 0 1 Dee 0 1 1 Eve 0 1 1 Ana 0 0 0 Bo 0 0 0');
  assert.equal(view.tableCount, 1);
  assert.equal(view.bracketRows, 2, 'the tallest round without its byes');
});

test('renders the board in Chinese', () => {
  const view = board.render(SAMPLE, 'zh', twelveMinutes);
  assert.equal(view.meta, '单打 · 抢3 · 进行中');
  assert.equal(view.player, '球员');
  assert.equal(text(view.tables), '1 号台 Ana 2 Bo 1 半决赛 12 分钟');
  assert.equal(text(view.next), 'Cy 对 Gina Park 半决赛 · 等待球员到场');
  assert.match(text(view.bracket), /^四分之一决赛 Ana 轮空 Bo 轮空 .* 弃权 半决赛 .* 1 号台 .* 决赛 待定 待定$/);
});

test('an untitled night, doubles, a finished night, an empty night', () => {
  const doubles = {...SAMPLE, event: {name: '', format: 'doubles', race_to: 5, phase: 'registration'},
    tables: [], next: [], bracket: [], standings: []};
  const en = board.render(doubles, 'en', () => null), zh = board.render(doubles, 'zh', () => null);
  assert.deepEqual([en.title, en.meta, en.player], ['Tonight', 'Doubles · Race to 5 · Registration open', 'Team']);
  assert.deepEqual([zh.title, zh.meta, zh.player], ['今晚', '双打 · 抢5 · 报名中', '队伍']);
  assert.equal(text(en.tables), 'No match on a table right now');
  assert.equal(text(en.next), 'Nothing queued');
  assert.equal(text(en.bracket), 'The draw has not been made yet');
  assert.equal(text(zh.standings), '暂无报名');
  const final = match('r3m1', 3, {name: 'Cy'}, {name: 'Ana'}, {status: 'complete', winner: 1, result: 'played', score: [1, 3]});
  const done = {...SAMPLE, event: {...SAMPLE.event, phase: 'complete'}, tables: [], next: [],
    bracket: [...SAMPLE.bracket.slice(0, 2), {round: 3, matches: [final]}]};
  assert.equal(text(board.render(done, 'en', () => null).tables), 'Champion Ana');
  assert.equal(text(board.render(done, 'zh', () => null).tables), '冠军 Ana');
});

test('every name is escaped', () => {
  const evil = '<img src=x onerror=alert(1)>&"\'';
  const hostile = {...SAMPLE, event: {...SAMPLE.event, name: evil},
    tables: [{...SAMPLE.tables[0], sides: [{name: evil}, {name: 'Bo'}]}],
    standings: [{name: evil, won: 0, lost: 0, played: 0}]};
  hostile.bracket = [{round: 1, matches: [match('r1m1', 1, {name: evil}, {name: 'x'})]}];
  hostile.next = [match('r1m1', 1, {name: evil}, {tbd: true}, {status: 'scheduled'})];
  const view = board.render(hostile, 'en', () => null);
  for (const html of [view.tables, view.next, view.bracket, view.standings]) {
    assert.ok(!html.includes('<img'), html);
    assert.ok(html.includes('&lt;img src=x onerror=alert(1)&gt;&amp;&quot;&#39;'), html);
  }
  assert.equal(view.title, evil);  // the title is set as text, never as HTML
});

test('language: ?lang= wins, else the browser', () => {
  assert.equal(board.pickLang('?lang=zh', ['en-US']), 'zh');
  assert.equal(board.pickLang('?lang=en', ['zh-CN']), 'en');
  assert.equal(board.pickLang('?lang=fr', ['zh-TW', 'en']), 'zh');
  assert.equal(board.pickLang('', ['zh']), 'zh');
  assert.equal(board.pickLang('', ['en-GB', 'zh-CN']), 'en');
  assert.equal(board.pickLang('', []), 'en');
  assert.equal(board.pickLang(undefined, [undefined]), 'en');
});

test('time on the table', () => {
  assert.equal(board.duration(59999, 'en'), 'Just started');
  assert.equal(board.duration(60000, 'zh'), '1 分钟');
  assert.equal(board.duration(-5000, 'en'), 'Just started');
  assert.equal(board.duration((2 * 60 + 5) * 60000, 'en'), '2 h 05 min');
  assert.equal(board.duration((2 * 60 + 5) * 60000, 'zh'), '2 小时 05 分');
  // By the server's clock: served_at minus since, plus the time since the answer arrived.
  const elapsed = board.elapsedOf({board: SAMPLE, receivedAt: 1000}, 31000);
  assert.equal(elapsed(SAMPLE.tables[0]), 12.5 * 60000 + 30000);
  assert.equal(elapsed({since: null}), null);
});

function fakeFetch(script) {
  const calls = [];
  const fetch = async (url, options) => {
    calls.push({url, headers: {...options.headers}});
    const next = script.shift();
    if (next instanceof Error) throw next;
    return {status: next.status, headers: {get: name => name === 'ETag' ? next.etag || null : null},
      json: async () => { if (next.body === undefined) throw new SyntaxError('not JSON'); return next.body; }};
  };
  return {fetch, calls};
}

test('the stale indicator comes after 15 s without a good answer, on an injected clock', async () => {
  let now = 0;
  const {fetch, calls} = fakeFetch([
    {status: 200, etag: 'W/"40-a"', body: SAMPLE}, {status: 304}, new TypeError('offline'), {status: 503},
    {status: 200, body: undefined}, {status: 200, body: {error: 'x'}}, {status: 200, etag: 'W/"41-b"', body: SAMPLE}]);
  const poller = board.createPoller({fetch, now: () => now, url: '/api/board'});
  const at = (ms, lang = 'en') => board.freshness(poller.state, ms, lang);
  assert.deepEqual(at(0), {updated: 'Connecting…', stale: false, message: ''});
  assert.equal(await poller.poll(), 'new');
  assert.deepEqual(calls[0], {url: '/api/board', headers: {}});
  assert.equal(at(1999).updated, 'Updated just now');
  assert.equal(at(5000).updated, 'Updated 5 s ago');
  assert.equal(at(5000, 'zh').updated, '5 秒前更新');
  now = 3000;
  assert.equal(await poller.poll(), 'same');  // a 304 is a good answer: nothing changed
  assert.deepEqual(calls[1].headers, {'If-None-Match': 'W/"40-a"'});
  for (const t of [6000, 9000, 12000, 15000]) {
    now = t;
    assert.equal(await poller.poll(), 'failed');  // offline, 503, not JSON, not a board
  }
  assert.equal(poller.state.board, SAMPLE, 'the last known board stays');
  assert.deepEqual(at(17999), {updated: 'Updated 14 s ago', stale: false, message: ''});
  assert.deepEqual(at(18000), {updated: 'Updated 15 s ago', stale: true,
    message: 'Reconnecting — showing the last known board'});
  assert.equal(at(18000, 'zh').message, '正在重新连接 — 显示的是最后一次收到的记分板');
  assert.equal(at(3000 + 125000).updated, 'Updated 2 min ago');
  assert.equal(at(3000 + 125000, 'zh').updated, '2 分钟前更新');
  now = 130000;
  assert.equal(await poller.poll(), 'new');
  assert.deepEqual(at(130500), {updated: 'Updated just now', stale: false, message: ''});
  assert.equal(poller.state.etag, 'W/"41-b"');
});

test('never seen a board: connecting, then reconnecting', async () => {
  let now = 1000;
  const poller = board.createPoller({fetch: fakeFetch([new TypeError('offline')]).fetch, now: () => now,
    url: '/api/board'});
  await poller.poll();
  assert.deepEqual(board.freshness(poller.state, 15999, 'en'), {updated: 'Connecting…', stale: false, message: ''});
  assert.deepEqual(board.freshness(poller.state, 16000, 'en'), {updated: 'Connecting…', stale: true, message: 'Reconnecting…'});
  assert.equal(board.freshness(poller.state, 16000, 'zh').message, '正在重新连接…');
});

test('the board switched off, and back on', async () => {
  const {fetch} = fakeFetch([{status: 200, etag: 'W/"off-1"', body: {board: 'off'}}, {status: 200, etag: 'W/"2-c"', body: SAMPLE}]);
  const poller = board.createPoller({fetch, now: () => 0});
  assert.equal(await poller.poll(), 'new');
  assert.deepEqual(poller.state.board, {board: 'off'});
  assert.equal(await poller.poll(), 'new');
  assert.equal(poller.state.board.board, 'on');
  assert.equal(board.say('en', 'off'), 'The board is off tonight');
  assert.equal(board.say('zh', 'off'), '今晚记分板已关闭');
});

function fakePage({search = '', languages = ['en-US'], wakeLock, responses, mount = '/', script = './board.js'}) {
  const elements = {}, listeners = {}, timers = [];
  const element = id => elements[id] || (elements[id] = {
    id, innerHTML: '', textContent: '', hidden: false, dataset: {}, attributes: {}, lang: '',
    setAttribute(name, value) { this.attributes[name] = value; },
    addEventListener(type, fn) { listeners[`${id}:${type}`] = fn; }});
  const location = {search, href: `http://board.test${mount}${search}`};
  const document = {
    getElementById: element, documentElement: {lang: ''}, title: '', visibilityState: 'visible',
    currentScript: script === null ? null : {src: new URL(script, location.href).href},
    body: {classes: new Set(), classList: {toggle(name, on) { on ? document.body.classes.add(name) : document.body.classes.delete(name); }}},
    addEventListener(type, fn) { listeners[`document:${type}`] = fn; }};
  const net = fakeFetch(responses);
  const win = {
    document, location, navigator: {languages, ...(wakeLock === undefined ? {} : {wakeLock})},
    fetch: net.fetch,
    setTimeout: (fn, ms) => timers.push({fn, ms}), clearTimeout() {}, setInterval() {},
    history: {replaceState(state, title, url) { location.href = String(url); location.search = new URL(url).search; }}};
  return {win, elements, listeners, timers, document, location, calls: net.calls};
}
const settle = () => new Promise(resolve => setImmediate(resolve));

test('start(): paints the board, and a missing or refused wake lock throws nothing', async () => {
  for (const wakeLock of [undefined, null, {}, {request: async () => { throw new Error('NotAllowedError'); }},
    {request: () => { throw new Error('sync'); }}]) {
    const page = fakePage({wakeLock, responses: [{status: 200, etag: 'W/"40-a"', body: SAMPLE}]});
    board.start(page.win);
    await settle();
    await settle();
    assert.equal(page.document.title, 'Corner Pocket · Friday 8-Ball');
    assert.equal(page.elements['event-meta'].textContent, 'Singles · Race to 3 · In progress');
    assert.match(page.elements.tables.innerHTML, /Ana/);
    assert.equal(page.elements.tables.dataset.count, '1');
    assert.equal(page.elements.stale.hidden, true);
    assert.equal(page.elements.off.hidden, true);
    assert.equal(page.elements.board.attributes['aria-busy'], 'false');
    assert.equal(page.timers.at(-1).ms, 3000, 'the next poll is 3 s away');
  }
});

test('start(): takes the wake lock where there is one', async () => {
  const requested = [];
  const page = fakePage({wakeLock: {request: async type => { requested.push(type); return {addEventListener() {}}; }},
    responses: [{status: 200, body: SAMPLE}]});
  board.start(page.win);
  await settle();
  assert.deepEqual(requested, ['screen']);
});

test('start(): the language toggle is the one control, and the address keeps it', async () => {
  const page = fakePage({search: '?lang=zh', languages: ['en-US'], responses: [{status: 200, body: SAMPLE}]});
  const handle = board.start(page.win);
  await settle();
  await settle();
  assert.equal(page.document.documentElement.lang, 'zh-CN');
  assert.equal(page.elements['tables-title'].textContent, '台上比赛');
  assert.equal(page.elements.lang.textContent, 'EN');
  page.listeners['lang:click']();
  assert.equal(handle.lang(), 'en');
  assert.equal(page.location.search, '?lang=en');
  assert.equal(page.elements['tables-title'].textContent, 'On the tables');
  assert.equal(page.elements.lang.textContent, '中');
  assert.deepEqual(Object.keys(page.listeners).sort(), ['document:visibilitychange', 'lang:click']);
});

test('start(): board off shows only the notice, in the language the page is in', async () => {
  for (const [lang, notice] of [['en', 'The board is off tonight'], ['zh', '今晚记分板已关闭']]) {
    const page = fakePage({search: `?lang=${lang}`, responses: [{status: 200, body: {board: 'off'}}]});
    board.start(page.win);
    await settle();
    await settle();
    assert.equal(page.elements.off.hidden, false, lang);
    assert.equal(page.elements.board.hidden, true, lang);
    assert.equal(page.elements['off-text'].textContent, notice, lang);
  }
});

test('start(): the poll follows the mount the page was served from', async () => {
  for (const [mount, api] of [['/', 'http://board.test/api/board'],
    ['/board/', 'http://board.test/board/api/board'],
    ['/display', 'http://board.test/api/board']]) {
    const page = fakePage({mount, responses: [{status: 200, etag: 'W/"1-a"', body: SAMPLE}]});
    board.start(page.win);
    await settle();
    await settle();
    assert.deepEqual(page.calls.map(call => call.url), [api], mount);
    assert.equal(page.elements['event-name'].textContent, 'Friday 8-Ball', mount);
  }
});

test('one file, both mounts: every reference stays inside the mount', () => {
  const html = fs.readFileSync(path.join(__dirname, '../annotator/board.html'), 'utf8');
  const refs = [...html.matchAll(/(?:href|src)="([^"]+)"/g)].map(m => m[1]);
  assert.ok(refs.length >= 4, `expected the page to reference its assets, got ${refs.length}`);
  for (const ref of refs) {
    assert.ok(!ref.startsWith('/') && !/^[a-z]+:/i.test(ref),
      `${ref} is absolute: it would leave the mount the page was served from`);
  }
  const resolve = base => refs.map(ref => new URL(ref, base).pathname);
  assert.deepEqual(resolve('http://board.test/'),
    ['/favicon.svg', '/favicon-32.png', '/board.css', '/board.js']);
  assert.deepEqual(resolve('http://board.test/board/'),
    ['/board/favicon.svg', '/board/favicon-32.png', '/board/board.css', '/board/board.js']);
  // The API sits beside the script that loaded the page: "/", "/board/" and the console's
  // own "/display" mount each resolve to their own API.
  assert.equal(board.apiUrl('http://board.test/board.js'), 'http://board.test/api/board');
  assert.equal(board.apiUrl('http://board.test/board/board.js'), 'http://board.test/board/api/board');
  assert.equal(board.apiUrl('http://board.test/display'), 'http://board.test/api/board');
  // ...and the fonts inside the stylesheet resolve inside the mount too.
  const css = fs.readFileSync(path.join(__dirname, '../annotator/board.css'), 'utf8');
  const urls = [...css.matchAll(/url\(\s*['"]?([^'")]+)['"]?\s*\)/g)].map(m => m[1]);
  assert.ok(urls.length >= 5, `expected the stylesheet to load its fonts, got ${urls.length}`);
  for (const url of urls) {
    assert.ok(!url.startsWith('/') && !/^[a-z]+:/i.test(url), `${url} is absolute: the fonts would leave the mount`);
  }
  assert.equal(new URL(urls[0], 'http://board.test/board/board.css').pathname,
    '/board/fonts/noto-sans-sc-500-common.woff2');
});

test('the page: no inline script or style, and nothing from the console', () => {
  const html = fs.readFileSync(path.join(__dirname, '../annotator/board.html'), 'utf8');
  assert.deepEqual([...html.matchAll(/<script\b([^>]*)>/g)].map(m => m[1].trim()), ['src="./board.js" defer']);
  assert.doesNotMatch(html, /<style|\sstyle=|\son[a-z]+=|javascript:/i);
  for (const name of ['ops.js', 'app.js', 'ops.css', 'app.css']) assert.ok(!html.includes(name), name);
  const js = fs.readFileSync(path.join(__dirname, '../annotator/board.js'), 'utf8');
  assert.doesNotMatch(js, /\.style\b|setAttribute\('style'|eval\(|new Function/);
});
