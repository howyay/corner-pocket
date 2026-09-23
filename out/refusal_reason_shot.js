#!/usr/bin/env node
'use strict';
// Evidence for the refusal-reason plumbing: drive the real Vision surface on the
// browser fixture (tests/serve_workbench_fixture.py, :8131) with headless Chromium
// over CDP and capture what the operator sees.  No npm packages: Node's global
// WebSocket talks to the browser's DevTools endpoint, the same way agent-browser
// would, and every screenshot waits for the overlay to settle (never mid-LOADING).
//
// Usage: node out/refusal_reason_shot.js [--out out] [--port 9222] [--base http://127.0.0.1:8131/]
const { spawn } = require('child_process');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');

const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
};
const OUT = path.resolve(arg('out', 'out'));
const PORT = Number(arg('port', '9222'));
const BASE = arg('base', 'http://127.0.0.1:8131/');
const FIXTURE_RESULTS = path.resolve(arg('fixture', 'out/ui-browser-fixture/out/scan30/frame_results'));

const CASES = [
  { name: 'refused-849.5-en', frame: 25485, lang: 'en', expect: 'quad refused' },
  { name: 'refused-849.5-zh', frame: 25485, lang: 'zh', expect: '四边形已拒绝' },
  { name: 'refused-387-sides-en', frame: 11610, lang: 'en', expect: 'sides unverified' },
  { name: 'accepted-61-en', frame: 1830, lang: 'en', expect: 'quad drift' },
  { name: 'accepted-61-zh', frame: 1830, lang: 'zh', expect: '漂移' },
  { name: 'manual-split-en', frame: 1830, lang: 'en', expect: '(+1 manual)', correction: true },
  { name: 'manual-split-zh', frame: 1830, lang: 'zh', expect: '(+1 人工)', correction: true },
];

const CORRECTION = {
  dataset: 'vod30', frame_index: 1830, width: 1280, height: 720, source: 'manual',
  boxes: [], table_polygon: [[532.0, 323.0], [800.0, 324.0], [997.0, 569.0], [384.0, 563.0]],
  saved_at: '2026-09-22T00:00:00+00:00',
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const getJson = (pathname) => new Promise((resolve, reject) => {
  const req = http.get({ host: '127.0.0.1', port: PORT, path: pathname }, (res) => {
    let body = '';
    res.on('data', (chunk) => { body += chunk; });
    res.on('end', () => { try { resolve(JSON.parse(body)); } catch (error) { reject(error); } });
  });
  req.on('error', reject);
});

async function connect() {
  for (let i = 0; i < 120; i++) {
    try { return await getJson('/json/version'); } catch (_) { await sleep(250); }
  }
  throw new Error(`chromium never answered on 127.0.0.1:${PORT}`);
}

class Cdp {
  constructor(socket) {
    this.socket = socket;
    this.id = 0;
    this.pending = new Map();
    this.waiters = [];
    socket.addEventListener('message', (event) => {
      const message = JSON.parse(event.data);
      if (message.id !== undefined && this.pending.has(message.id)) {
        const { resolve, reject } = this.pending.get(message.id);
        this.pending.delete(message.id);
        message.error ? reject(new Error(JSON.stringify(message.error))) : resolve(message.result);
      } else if (message.method) {
        this.waiters = this.waiters.filter((waiter) => {
          if (waiter.method !== message.method) return true;
          waiter.resolve(message.params);
          return false;
        });
      }
    });
  }
  send(method, params = {}, sessionId) {
    const id = ++this.id;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.socket.send(JSON.stringify(sessionId ? { id, method, params, sessionId } : { id, method, params }));
    });
  }
  waitFor(method, timeoutMs = 20000) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(`timeout waiting for ${method}`)), timeoutMs);
      this.waiters.push({ method, resolve: (params) => { clearTimeout(timer); resolve(params); } });
    });
  }
}

async function main() {
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'refusal-shot-'));
  const chrome = spawn('chromium', [
    '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
    '--hide-scrollbars', '--force-device-scale-factor=1', '--window-size=1600,1100',
    `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, 'about:blank',
  ], { stdio: ['ignore', 'pipe', 'pipe'] });
  const evidence = [];
  try {
    const version = await connect();
    const socket = new WebSocket(version.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      socket.addEventListener('open', resolve);
      socket.addEventListener('error', reject);
    });
    const cdp = new Cdp(socket);
    const { targetId } = await cdp.send('Target.createTarget', { url: 'about:blank' });
    const { sessionId } = await cdp.send('Target.attachToTarget', { targetId, flatten: true });
    await cdp.send('Page.enable', {}, sessionId);
    await cdp.send('Runtime.enable', {}, sessionId);
    const evaluate = async (expression) => {
      const result = await cdp.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }, sessionId);
      if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
      return result.result.value;
    };
    const goto = async (url) => {
      const loaded = cdp.waitFor('Page.loadEventFired');
      await cdp.send('Page.navigate', { url }, sessionId);
      await loaded;
      await sleep(400);
    };

    for (const item of CASES) {
      // the shell reads its language from localStorage before ops.js evaluates
      await goto(BASE);
      await evaluate(`localStorage.setItem('cp-ops-lang', ${JSON.stringify(item.lang)}); true`);
      await goto(BASE);
      let correctionPath = null;
      if (item.correction) {
        correctionPath = path.join(FIXTURE_RESULTS, String(item.frame), 'correction.json');
        fs.mkdirSync(path.dirname(correctionPath), { recursive: true });
        fs.writeFileSync(correctionPath, JSON.stringify(CORRECTION, null, 1));
      }
      try {
        const facts = await evaluate(`(async () => {
          const facts = () => (document.querySelector('#vs-facts') || {}).textContent || '';
          const sleep = ms => new Promise(r => setTimeout(r, ms));
          const wanted = new RegExp('(?:frame|帧) ${item.frame}\\b');
          for (let i = 0; i < 60 && !document.querySelector('#vs-scrub'); i++) {
            const tab = document.querySelector('[data-tab="vision"]');
            if (tab) tab.click();
            await sleep(500);
          }
          let seeks = 0;
          for (let i = 0; i < 120; i++) {
            const scrub = document.querySelector('#vs-scrub');
            const text = facts();
            const onFrame = wanted.test(text);
            // one seek at a time: re-dispatching while the overlay loads restarts it
            if (onFrame && !/LOADING|读取中/.test(text)) return text;
            if (scrub && !onFrame && seeks < 5) {
              scrub.value = '${item.frame}';
              scrub.dispatchEvent(new Event('change', {bubbles: true}));
              seeks++;
            }
            await sleep(500);
          }
          return facts();
        })()`);
        const note = await evaluate(`(document.querySelector('#stage-note') || {}).textContent || ''`);
        const tags = await evaluate(`(document.querySelector('#t-overlay') || {innerHTML:''}).innerHTML.match(/YOURS|MODEL/g)?.join(',') || ''`);
        if (!facts.includes(item.expect)) throw new Error(`facts line has no ${JSON.stringify(item.expect)}: ${facts}`);
        if (/LOADING|读取中/.test(facts)) throw new Error(`overlay still loading: ${facts}`);
        const shot = await cdp.send('Page.captureScreenshot', { format: 'png' }, sessionId);
        const file = path.join(OUT, `refusal-reason-${item.name}.png`);
        fs.writeFileSync(file, Buffer.from(shot.data, 'base64'));
        evidence.push({ case: item.name, frame: item.frame, lang: item.lang, facts, note, tags: tags || 'none', file });
        console.log(`OK ${item.name} frame=${item.frame} lang=${item.lang} tags=${tags || 'none'}`);
        console.log(`   facts: ${facts}`);
        console.log(`   note : ${note || '(no stage note)'}`);
      } finally {
        if (correctionPath && fs.existsSync(correctionPath)) fs.unlinkSync(correctionPath);
      }
    }
    fs.writeFileSync(path.join(OUT, 'refusal-reason-evidence.json'), JSON.stringify(evidence, null, 1));
    console.log(`wrote ${path.join(OUT, 'refusal-reason-evidence.json')}`);
  } finally {
    chrome.kill('SIGKILL');
    fs.rmSync(profile, { recursive: true, force: true });
  }
}

main().catch((error) => { console.error('FAILED:', error.message); process.exit(1); });
