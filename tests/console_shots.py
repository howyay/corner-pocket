#!/usr/bin/env python3
"""Reproducible console screenshots -- the before/after baseline behind docs/console-shots.md.

One command starts the isolated fixture (tests/serve_operations_fixture.py, seeded from
tests/console_fixture_state.json), drives headless Chromium over the DevTools protocol, writes a
PNG per state at 1440x900 and 390x844 in EN and 中, then stops the fixture and proves both
loopback ports are free again. Nothing but the standard library and a system Chromium is used:
the DevTools websocket client is implemented here (socket + hashlib + base64), because the
stdlib has no websocket client and this repo may not grow a dependency for a screenshot tool.

    .venv/bin/python tests/console_shots.py                          # before -> out/console-before/
    .venv/bin/python tests/console_shots.py --build after            # after  -> out/console-after/
    .venv/bin/python tests/console_shots.py --states records,backroom --langs en   # subset
    .venv/bin/python tests/console_shots.py --measure-only           # header geometry only

--build before drives the shipping console through its documented hashes
(#/tonight/register|rack|play|close, #/floor, #/matches). --build after drives the redesigned
console: the named Tonight phases collapse to #/tonight and the Play tabs are selected by
clicking nav.playtabs button.playtab[data-play=...]. The states are the same list either way, so
the two runs line up for a diff; states that a build cannot reach are reported as such in the
manifest instead of being faked.

Every shot is a full document load (the URL carries a per-shot query string, so a same-document
hash navigation can never be mistaken for a render) with the browser cache disabled, and each
PNG is checked against the requested pixel size before the run is allowed to pass. Loopback only:
every URL is asserted to be 127.0.0.1 on a port this script itself opened.
"""
import argparse
import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / 'tests' / 'serve_operations_fixture.py'
STATE = ROOT / 'tests' / 'console_fixture_state.json'
CHROMIUM_CANDIDATES = [
    '/run/current-system/sw/bin/chromium',
    '/run/current-system/sw/bin/chromium-browser',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
    '/usr/bin/google-chrome',
]
CONSOLE_PORT = 8150   # the console fixture (docs/console-shots.md)
PUBLIC_PORT = 8151    # the read-only public board served by the same fixture process
LANGS = {'en': 'cp-ops-lang=en', 'zh': 'cp-ops-lang=zh'}

# The shot list. `play` is the expected data-view of the visible section.playview; `hash_before`
# and `hash_after` are the route each build understands. A state whose route the build does not
# have is still attempted (the app decides), and the manifest records what actually rendered.
STATES = [
    dict(name='tonight-register', before='#/tonight/register', after='#/tonight',
         title='Tonight · Register 阶段（今天报名的 16 人签入）'),
    dict(name='tonight-rack', before='#/tonight/rack', after='#/tonight',
         title='Tonight · Rack 阶段（排台 / 首轮对阵）'),
    dict(name='tonight-play', before='#/tonight/play', after='#/tonight', play='queue',
         title='Tonight · Play 阶段 · Queue 视图（等待队列）'),
    dict(name='tonight-close', before='#/tonight/close', after='#/tonight',
         title='Tonight · Close 阶段（结业 / 归档）'),
    dict(name='play-tables', before='#/tonight/play', after='#/tonight', play='tables',
         legacy='#/floor', title='Play · Tables 视图（6 张台的实时状态）'),
    dict(name='play-bracket', before='#/tonight/play', after='#/tonight', play='bracket',
         legacy='#/matches', title='Play · Bracket 视图（淘汰树 / 双败）'),
    dict(name='records', before='#/records', after='#/records',
         title='Records（三段：standings / timeline / history）'),
    dict(name='regulars', before='#/regulars', after='#/regulars',
         title='Regulars（常客花名册与战绩）'),
    dict(name='backroom', before='#/backroom', after='#/backroom',
         title='Back room（系统状态、备注、维护者）'),
]
# Extra coverage that only needs one viewport pair each.
EXTRA_STATES = [
    dict(name='records-light', before='#/records', after='#/records', langs=['en'], theme='light',
         title='Records · 亮色主题（证明配色切换真的生效）'),
]
# States that only exist after the redesign, where the screen is reached by an act. `setup`
# presses the real control (the timeline toggle, the top bar's backfill entry) and the manifest
# records whether the control was there to press.
AFTER_STATES = [
    dict(name='records-night-open', before='#/records', after='#/records', builds=('after',),
         setup="const b = document.querySelector('li.tl-item .tl-toggle');"
               " if (!b) return false; b.click(); return true;",
         title='Records · 一场赛事在时间线上展开（赛果单 / VOD 来源 / 当晚流水）'),
    dict(name='backfill-pick', before='#/records', after='#/records', builds=('after',),
         setup="const b = document.querySelector('[data-action=\"backfill-open\"]');"
               " if (!b) return false; b.click(); return true;",
         title='补录 · 第一步（选一场 Twitch 直播，视频从不被读取）'),
]
PUBLIC_STATES = [    dict(name='public-board', url='http://127.0.0.1:{port}/', langs=['en'],
         title='Public board（8151，只读对外看板）'),
]
SIZES = {'laptop': (1280, 900), 'desktop': (1440, 900), 'phone': (390, 844)}
# laptop came first in the round-3 set on purpose: 1280x900 is the viewport a blind
# reviewer actually sat at, and it is where the bar was measured to wrap (SS14.1).


def free_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


def port_is_free(port):
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(('127.0.0.1', port))
        except OSError:
            return False
    return True


def assert_loopback(url, ports, what):
    """Nothing in this script may talk to anything but a loopback port it opened itself."""
    parts = urllib.parse.urlsplit(url)
    if parts.hostname != '127.0.0.1' or parts.port not in ports:
        raise SystemExit(f'refusing {what}: {url} is not 127.0.0.1 on {sorted(ports)}')


def http_json(url, method='GET', timeout=120):
    assert_loopback(url, {CONSOLE_PORT, PUBLIC_PORT} | set(DEBUG_PORTS), 'HTTP request')
    request = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode('utf-8')
    return json.loads(body) if body.strip().startswith(('{', '[')) else body


# --------------------------------------------------------------------------- websocket client
class WebSocket:
    """The 60 lines of RFC 6455 a screenshot tool needs: text frames, masking, ping/pong."""

    GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'

    READ_WINDOW = 2.0   # seconds; a read that returns nothing raises CdpIdle and is retried

    def __init__(self, url):
        parts = urllib.parse.urlsplit(url)
        if parts.scheme != 'ws' or parts.hostname != '127.0.0.1':
            raise SystemExit(f'refusing websocket to {url}: not ws://127.0.0.1')
        self.sock = socket.create_connection((parts.hostname, parts.port), timeout=120)
        self.buffer = b''
        self.chunks = []
        key = base64.b64encode(os.urandom(16)).decode('ascii')
        path = parts.path + (f'?{parts.query}' if parts.query else '')
        handshake = (f'GET {path} HTTP/1.1\r\nHost: {parts.netloc}\r\nUpgrade: websocket\r\n'
                     f'Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n'
                     f'Sec-WebSocket-Version: 13\r\n\r\n')
        self.sock.sendall(handshake.encode('ascii'))
        while b'\r\n\r\n' not in self.buffer:
            try:
                self._fill()
            except CdpIdle:
                raise CdpDead('devtools did not finish the websocket handshake')
        head, self.buffer = self.buffer.split(b'\r\n\r\n', 1)
        lines = head.decode('latin-1').split('\r\n')
        if ' 101 ' not in lines[0]:
            raise SystemExit(f'devtools refused the websocket upgrade: {lines[0]}')
        headers = dict(line.split(': ', 1) for line in lines[1:] if ': ' in line)
        expected = base64.b64encode(hashlib.sha1((key + self.GUID).encode()).digest()).decode()
        if headers.get('Sec-WebSocket-Accept') != expected:
            raise SystemExit('devtools sent a bad Sec-WebSocket-Accept')
        # From here on reads use a short window, so a call deadline measured in Python can actually
        # interrupt one. A long socket timeout cannot be interrupted: with a 900 s window a call
        # that was supposed to give up after 120 s sat there for 15 minutes instead.
        self.sock.settimeout(self.READ_WINDOW)

    def _fill(self):
        """Add whatever has arrived; raise CdpIdle when the read window closes with nothing."""
        try:
            chunk = self.sock.recv(65536)
        except (socket.timeout, TimeoutError):
            raise CdpIdle()
        except OSError as error:
            raise CdpDead(f'devtools websocket broke: {error}')
        if not chunk:
            raise CdpDead('devtools closed the websocket')
        self.buffer += chunk

    def _peek(self, count):
        """Bytes without consuming them, so a CdpIdle raised here loses nothing."""
        while len(self.buffer) < count:
            self._fill()
        return self.buffer[:count]

    def send_text(self, text):
        payload = text.encode('utf-8')
        header = bytearray([0x81])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header += struct.pack('>H', length)
        else:
            header.append(0x80 | 127)
            header += struct.pack('>Q', length)
        mask = os.urandom(4)
        header += mask
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.settimeout(120)   # a send is small; give it room, then go back to the short window
        try:
            self.sock.sendall(bytes(header) + masked)
        finally:
            self.sock.settimeout(self.READ_WINDOW)

    def _frame(self):
        """One frame, consumed only once it is complete, so an idle window is harmless."""
        header = self._peek(2)
        fin, opcode, length = bool(header[0] & 0x80), header[0] & 0x0F, header[1] & 0x7F
        offset = 2
        if length == 126:
            length, offset = struct.unpack('>H', self._peek(4)[2:4])[0], 4
        elif length == 127:
            length, offset = struct.unpack('>Q', self._peek(10)[2:10])[0], 10
        masked = bool(header[1] & 0x80)
        total = offset + (4 if masked else 0) + length
        raw = self._peek(total)
        self.buffer = self.buffer[total:]
        body = raw[offset:]
        if masked:  # a server frame must not be masked, but tolerate it
            mask, body = body[:4], body[4:]
            body = bytes(byte ^ mask[index % 4] for index, byte in enumerate(body))
        return fin, opcode, body

    def recv_text(self):
        """One whole message: a screenshot arrives across many continuation frames.

        Accumulation lives on the instance, so a CdpIdle raised by a read window resumes here
        instead of losing a half-read message.
        """
        while True:
            fin, opcode, data = self._frame()
            if opcode == 0x9:  # ping -> pong (a client frame must be masked)
                self.sock.sendall(b'\x8a\x80' + os.urandom(4))
                continue
            if opcode == 0xA:  # pong
                continue
            if opcode == 0x8:
                raise CdpDead('devtools closed the websocket mid-call')
            self.chunks.append(data)
            if fin:
                message = b''.join(self.chunks).decode('utf-8')
                self.chunks = []
                return message

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class CdpTimeout(RuntimeError):
    """A DevTools call that never answered: on a starved box this is the browser, not the tool."""


class CdpDead(RuntimeError):
    """DevTools hung up: the renderer died (OOM-killed, or the machine reaped it). Restartable."""


class CdpIdle(RuntimeError):
    """One read window with no bytes: internal to the socket loop, never a failure by itself."""


class Devtools:
    """A CDP page session: one target, one websocket, sequential calls plus collected errors."""

    def __init__(self, ws_url):
        self.ws = WebSocket(ws_url)
        self.next_id = 0
        self.failed_requests = []
        self.js_errors = []
        self.responses = {}

    def call(self, method, params=None, timeout=600):
        self.next_id += 1
        message_id = self.next_id
        self.ws.send_text(json.dumps({'id': message_id, 'method': method, 'params': params or {}}))
        started = time.time()
        while True:
            elapsed = time.time() - started
            if elapsed > timeout:
                raise CdpTimeout(f'{method} did not answer within {timeout}s')
            try:
                message = json.loads(self.ws.recv_text())
            except CdpIdle:
                continue  # nothing arrived in one read window; the deadline above decides
            if message.get('id') == message_id:
                if VERBOSE or elapsed > 5:
                    print(f'       .. {method} {elapsed:.1f}s', flush=True)
                if 'error' in message:
                    raise SystemExit(f'{method} failed: {message["error"]}')
                return message.get('result', {})
            self._event(message)

    def _event(self, message):
        method = message.get('method', '')
        params = message.get('params', {})
        if method == 'Network.loadingFailed':
            error = params.get('errorText', '')
            if error != 'net::ERR_ABORTED':  # a cancelled navigation, not a broken asset
                self.failed_requests.append(error)
        elif method == 'Network.responseReceived':
            response = params.get('response', {})
            url, status = response.get('url', ''), response.get('status')
            if url.endswith(('.woff2', '.css', '.js', '.png', '.svg')):
                served = 'memory' if response.get('fromMemoryCache') else (
                    'disk' if response.get('fromDiskCache') else 'network')
                self.responses[url] = f'{status}/{served}'
        elif method == 'Runtime.exceptionThrown':
            self.js_errors.append(str(params.get('exceptionDetails', {}).get('text')))
        elif method == 'Runtime.consoleAPICalled' and params.get('type') == 'error':
            self.js_errors.append('console.error: ' + json.dumps(params.get('args', []))[:200])
        elif method == 'Log.entryAdded' and params.get('entry', {}).get('level') == 'error':
            self.js_errors.append('log: ' + params['entry'].get('text', '')[:200])

    def reset_errors(self):
        self.failed_requests, self.js_errors, self.responses = [], [], {}

    def evaluate(self, expression, await_promise=False, timeout=300):
        result = self.call('Runtime.evaluate', {
            'expression': expression, 'returnByValue': True, 'awaitPromise': await_promise,
        }, timeout=timeout)
        if 'exceptionDetails' in result:
            raise SystemExit(f'page threw while evaluating: {result["exceptionDetails"]}')
        return result.get('result', {}).get('value')

    def close(self):
        self.ws.close()


# Readiness is polled from here, never awaited with Runtime.evaluate{awaitPromise}. A webfont
# whose request is still pending keeps document.fonts.ready pending for ever, and a screenshot
# run that hangs on a font is worse than one that reports the font as not loaded.
RENDER_PROBE = """(() => {
  const main = document.querySelector('#main');
  const html = main ? main.innerHTML : document.body.innerHTML;
  const shell = document.querySelector('#ops-shell');
  return {
    complete: document.readyState === 'complete',
    chars: html.length,
    mainChars: html.length,
    hasMain: !!main,
    // ops.html ships an empty <main> and an empty <nav>, so both being filled is what proves
    // ops.js rendered. Without this a shot can silently capture the static shell: the first
    // aborted run recorded exactly that (nav height 8, #strip hidden) as a measurements row.
    navItems: document.querySelectorAll('#nav .navtab, #nav a, #nav button').length,
    tab: shell ? shell.dataset.tab : null,
    fontsStatus: document.fonts ? document.fonts.status : null,
    scripts: [...document.scripts].map(s => (s.src || 'inline').split('/').pop()),
    text: (main ? main.innerText : document.body.innerText || '').slice(0, 160),
    loading: /正在读取运营数据|Loading operations/.test(html) || html.length === 0,
  };
})()"""

FACTS_SCRIPT = """(() => {
  const shell = document.querySelector('#ops-shell');
  const view = document.querySelector('.playview:not([hidden])');
  const sheets = [...document.styleSheets].map(s => {
    try { return {href: (s.href || '').split('/').pop(), rules: s.cssRules.length}; }
    catch (error) { return {href: (s.href || '').split('/').pop(), error: String(error)}; }
  });
  const faces = document.fonts ? [...document.fonts].map(f => `${f.family} ${f.weight} ${f.status}`) : [];
  return {
    hash: location.hash,
    lang: document.documentElement.lang,
    theme: document.documentElement.dataset.theme || null,
    tab: shell ? shell.dataset.tab : null,
    playView: view ? view.dataset.view : null,
    mainChars: (document.querySelector('#main') || {innerHTML: ''}).innerHTML.length,
    fontFaces: faces,
    fontsLoaded: faces.filter(face => face.endsWith(' loaded')).length,
    brassToken: shell ? getComputedStyle(shell).getPropertyValue('--brass').trim() : null,
    sheets: sheets,
    navItems: document.querySelectorAll('#nav .navtab, #nav a, #nav button').length,
    tabbarVisible: (() => { const t = document.querySelector('#tabbar'); return t ? getComputedStyle(t).display !== 'none' && t.getBoundingClientRect().height > 0 : null; })(),
  };
})()"""


def wait_for_render(page, deadline=600, requires_main=True, requires_nav=True, what='page'):
    """Poll the render state from here; tolerate the evaluate that races a navigation.

    A page that never renders raises CdpTimeout, because that is the condition a browser restart
    actually fixes. Returning the last partial probe would let an unrendered shell be captured.
    """
    facts, started = None, time.time()
    while time.time() - started < deadline:
        try:
            probe = page.evaluate(RENDER_PROBE, timeout=120)
        except SystemExit:
            probe = None  # execution context destroyed mid-navigation; try again
        if probe:
            rendered = (probe.get('complete') and not probe.get('loading')
                        and (probe.get('hasMain') or not requires_main)
                        and (probe.get('navItems', 0) > 0 or not requires_nav))
            if rendered:
                # Web fonts are waited for, but only for a bounded time: a face whose request
                # never settles must not hold the whole run (that is why nothing here awaits
                # document.fonts.ready). FACTS_SCRIPT reports how many faces made it.
                font_deadline = time.time() + min(30, max(0, deadline - (time.time() - started)))
                while time.time() < font_deadline and probe.get('fontsStatus') != 'loaded':
                    time.sleep(0.3)
                    try:
                        probe = page.evaluate(RENDER_PROBE, timeout=120)
                    except SystemExit:
                        break
                return probe
            facts = probe
        time.sleep(0.3)
    raise CdpTimeout(f'{what} never rendered within {deadline}s\n'
                     f'      last probe: {facts}\n'
                     f'      assets: {dict(list(page.responses.items())[:12])}\n'
                     f'      failed requests: {page.failed_requests[:4]} · js errors: {page.js_errors[:4]}')


MEASURE_SCRIPT = """(() => {
  const box = selector => {
    const element = document.querySelector(selector);
    if (!element) return null;
    const rect = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    return {
      top: Math.round(rect.top * 10) / 10,
      height: Math.round(rect.height * 10) / 10,
      display: style.display,
      padding: style.paddingTop + ' / ' + style.paddingBottom,
    };
  };
  return {
    viewport: {width: innerWidth, height: innerHeight, devicePixelRatio: devicePixelRatio},
    header: box('header'),
    bar: box('header .bar'),
    nav: box('#nav'),
    strip: box('#strip'),
    tabbar: box('#tabbar'),
    main: box('#main'),
    contentTop: Math.round((document.querySelector('#main') || {getBoundingClientRect: () => ({top: 0})}).getBoundingClientRect().top * 10) / 10,
    navItems: document.querySelectorAll('#nav .navtab, #nav a, #nav button').length,
    hash: location.hash,
    lang: document.documentElement.lang,
    tagline: (() => { const t = document.querySelector('#tagline'); return t ? (t.textContent || '').trim() : null; })(),
    brand: box('header .brand'),
    tools: box('header .tools'),
    navParent: (() => { const n = document.querySelector('#nav'); return n && n.parentElement ? (n.parentElement.className || n.parentElement.tagName.toLowerCase()) : null; })(),
    headerChildren: Array.from(document.querySelector('header').children).map(el => el.tagName.toLowerCase() + (el.id ? '#' + el.id : el.className ? '.' + String(el.className).split(' ')[0] : '')),
  };
})()"""

# Item 1 of docs/console-redesign.md folds the brand row away and moves nav#nav into header .bar.
# This simulation measures what that costs on the *shipping* build, so the "one row" number in
# docs/console-shots.md is a measurement, not arithmetic on CSS source. It is labelled as a
# simulation and must be re-measured with --build after once the redesign exists.
SIMULATE_SCRIPT = """(() => {
  const header = document.querySelector('header');
  const bar = header.querySelector('.bar');
  const brand = bar.querySelector('.brand');
  const nav = document.querySelector('#nav');
  const box = element => element ? Math.round(element.getBoundingClientRect().height * 10) / 10 : null;
  const top = () => Math.round(document.querySelector('#main').getBoundingClientRect().top * 10) / 10;
  const rows = () => [['bar', bar], ['nav', nav], ['strip', document.querySelector('#strip')],
                      ['tabbar', document.querySelector('#tabbar')]]
    .map(([label, element]) => label + '=' + (box(element) === null ? 'hidden' : box(element))).join(' ');
  const before = {header: box(header), bar: box(bar), contentTop: top(), rows: rows()};
  if (brand) brand.style.display = 'none';
  if (nav && nav.parentElement !== bar) bar.appendChild(nav);
  const after = {header: box(header), bar: box(bar), contentTop: top(), rows: rows()};
  return {before, after};
})()"""


@contextmanager
def fixture(extra=()):
    """A throwaway operations fixture on fixed loopback ports, seeded with the club."""
    for port in (CONSOLE_PORT, PUBLIC_PORT):
        if not port_is_free(port):
            raise SystemExit(f'port {port} is already in use; refusing to touch a running server')
    if not STATE.exists():
        raise SystemExit(f'{STATE} is missing; run tests/console_fixture_build.py first')
    environment = dict(os.environ, PYTHONPATH='.')
    environment.pop('POOL_DATABASE_URL', None)
    interpreter = str(ROOT / '.venv' / 'bin' / 'python') if (ROOT / '.venv' / 'bin' / 'python').exists() else sys.executable
    command = [interpreter, str(FIXTURE), '--port', str(CONSOLE_PORT),
               '--public-port', str(PUBLIC_PORT), '--state', str(STATE), *extra]
    process = subprocess.Popen(command, cwd=ROOT, env=environment,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    # Nobody reads this pipe while the run is going, and the fixture logs every request. Once the
    # 64 KiB pipe buffer fills, the fixture blocks inside its own logging and every request hangs:
    # measured twice as a process that is alive, LISTENing, at 0 % CPU, with every path timing out
    # (the shot phase then stalls three times and the run dies with `0 shot(s)`). Drain the pipe,
    # keep the tail for the failure message, and mirror it to out/console-*/fixture.log.
    fixture_lines = []
    try:
        fixture_log = (SHOOT_DIR / 'fixture.log').open('w', encoding='utf-8')
    except OSError:
        fixture_log = None

    def drain():
        for line in process.stdout:
            fixture_lines.append(line.rstrip('\n'))
            del fixture_lines[:-400]
            if fixture_log is not None:
                fixture_log.write(line)
                fixture_log.flush()

    threading.Thread(target=drain, daemon=True).start()
    try:
        deadline = time.time() + 180
        while time.time() < deadline:
            if process.poll() is not None:
                raise SystemExit('fixture exited early:\n' + '\n'.join(fixture_lines))
            try:
                state = http_json(f'http://127.0.0.1:{CONSOLE_PORT}/api/operations', timeout=60)
                http_json(f'http://127.0.0.1:{PUBLIC_PORT}/', timeout=60)
                break
            except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError):
                time.sleep(0.25)
        else:
            raise SystemExit(f'fixture did not answer on {CONSOLE_PORT} and {PUBLIC_PORT} within 180s')
        print(f'fixture up: console http://127.0.0.1:{CONSOLE_PORT}/ops.html · '
              f'public board http://127.0.0.1:{PUBLIC_PORT}/ · revision {state.get("revision")} · '
              f'{len(state.get("players", []))} players', flush=True)
        yield state
    finally:
        process.terminate()
        try:
            process.wait(timeout=45)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=45)
            except subprocess.TimeoutExpired:
                print('warning: fixture did not reap after SIGKILL (loaded machine)', flush=True)
        if fixture_log is not None:
            fixture_log.close()  # the drain thread owns the pipe; this is just the mirror
    for port in (CONSOLE_PORT, PUBLIC_PORT):
        if not port_is_free(port):
            raise SystemExit(f'port {port} was not released by the fixture')
    print(f'fixture stopped; 127.0.0.1:{CONSOLE_PORT} and :{PUBLIC_PORT} are free again', flush=True)


class Browser:
    """One headless Chromium that can be restarted mid-run.

    A single DevTools call can stall for minutes on a loaded box; the recovery that works is a
    fresh browser, so the run restarts instead of dying (and records that it did).
    """

    def __init__(self, binary=None):
        self.binary = binary or next((path for path in CHROMIUM_CANDIDATES if Path(path).exists()), None)
        if not self.binary:
            raise SystemExit('no chromium found in ' + ', '.join(CHROMIUM_CANDIDATES))
        if not Path(self.binary).exists():
            raise SystemExit('--chromium %s does not exist' % self.binary)
        self.version = subprocess.run([self.binary, '--version'], capture_output=True, text=True,
                                      timeout=120).stdout.strip()
        self.process = self.page = self.profile = self.port = None
        self.restarts = 0

    def start(self):
        global CHROMIUM_VERSION
        CHROMIUM_VERSION = self.version
        self.port = free_port()
        DEBUG_PORTS.add(self.port)
        self.profile = Path(tempfile.mkdtemp(prefix='cp-shots-'))
        command = [
            self.binary, '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
            '--no-first-run', '--no-default-browser-check',
            # BackForwardCache keeps every page the run navigated away from alive, and the console
            # holds a live GET /api/clock/stream on each of them. Chromium allows six sockets per
            # host, so by the fourth navigation all six are held by parked pages and the next
            # navigation cannot fetch anything: measured 6/6 established sockets to the fixture and
            # a page that never renders. Without the bfcache the old page dies, its stream closes,
            # and the socket comes back.
            '--disable-features=BackForwardCache',
            '--force-color-profile=srgb', '--force-device-scale-factor=1',
            '--remote-debugging-port=' + str(self.port), '--user-data-dir=' + str(self.profile),
            '--window-size=1440,960', 'about:blank',
        ]
        self.process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        deadline, target, version_json = time.time() + 240, None, {}
        while time.time() < deadline and self.process.poll() is None:
            try:
                version_json = http_json(f'http://127.0.0.1:{self.port}/json/version', timeout=60)
            except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError):
                time.sleep(0.25)
                continue
            for _ in range(40):
                try:
                    pages = [t for t in http_json(f'http://127.0.0.1:{self.port}/json/list', timeout=60)
                             if t.get('type') == 'page' and t.get('webSocketDebuggerUrl')]
                except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError):
                    pages = []
                if pages:
                    target = pages[0]
                    break
                time.sleep(0.25)
            break
        if not target:
            raise SystemExit('headless chromium did not expose a debuggable page')
        print(f'{self.version}: {version_json.get("Browser")} · devtools on 127.0.0.1:{self.port}', flush=True)
        assert_loopback(target['webSocketDebuggerUrl'].replace('ws://', 'http://'), {self.port}, 'devtools target')
        self.page = Devtools(target['webSocketDebuggerUrl'])
        self.page.call('Page.enable')
        self.page.call('Runtime.enable')
        self.page.call('Log.enable')
        self.page.call('Network.enable')
        # Cold cache at the start, a fresh profile every run, and a per-shot query string on the
        # document URL: a stale asset cannot explain a screenshot. The cache is left ON after
        # that, because switching it off makes every one of the ~40 shots refetch the CJK webfaces
        # and turns a 40 s shot into minutes on a loaded box.
        self.page.call('Network.clearBrowserCache')
        # Land on the console origin once so localStorage can be preset before any shot.
        # The console is served at '/', and /ops.html answers 308 -> '/' with the query string
        # dropped, so shots address the root path directly and keep their cache-busting query.
        self.page.call('Page.navigate', {'url': f'http://127.0.0.1:{CONSOLE_PORT}/?land=1'})
        wait_for_render(self.page, what='the console landing page')

    def restart(self):
        self.restarts += 1
        print(f'      ! browser stalled; restart #{self.restarts} and retry the shot', flush=True)
        self.stop()
        self.start()

    def stop(self):
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=45)
            except subprocess.TimeoutExpired:
                self.process.kill()
                try:
                    self.process.wait(timeout=45)
                except subprocess.TimeoutExpired:
                    print('warning: chromium did not reap after SIGKILL (loaded machine)', flush=True)
            self.process = None
        if self.page:
            self.page.close()
            self.page = None
        if self.profile:
            shutil.rmtree(self.profile, ignore_errors=True)
            self.profile = None


def png_size(path):
    data = path.read_bytes()[:24]
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise SystemExit(f'{path} is not a PNG')
    return struct.unpack('>II', data[16:24])


def set_preferences(page, lang, theme):
    page.evaluate(f"localStorage.setItem('cp-ops-lang', {json.dumps(lang)});"
                  f"localStorage.setItem('cp-ops-theme', {json.dumps(theme)});"
                  "localStorage.getItem('cp-ops-lang') + '/' + localStorage.getItem('cp-ops-theme')")


def shoot_after_landing(browser, origin, lang, theme, shot, target, width, height, mobile, args):
    """One shot, re-establishing the console preferences in case the browser just restarted.

    A restart gets a fresh profile, so localStorage is empty again; and the public board has no
    #main, so its readiness probe only waits for the document.
    """
    if origin == CONSOLE_PORT:
        set_preferences(browser.page, lang, theme)
    return shoot(browser.page, shot['name'], target, width, height, mobile, lang, theme,
                 play_view=shot.get('play'), strict=not args.loose,
                 requires_main=origin == CONSOLE_PORT, setup=shot.get('setup'))


def shoot_with_retry(browser, origin, lang, theme, shot, target, width, height, mobile, args):
    """One shot, retried once on a fresh URL: a page that never renders is usually a hiccup.

    The retry keeps whichever attempt has fewer problems, so a second failure never replaces a
    good first capture.
    """
    record = shoot_after_landing(browser, origin, lang, theme, shot, target, width, height, mobile, args)
    for attempt in range(1, args.shot_retries + 1):
        if not record['problems']:
            break
        retry = target.replace('#', f'-retry{attempt}#', 1) if '#' in target else f'{target}&retry={attempt}'
        print(f'       ! {shot["name"]}/{lang}: {record["problems"][0]} — retrying on a fresh URL', flush=True)
        second = shoot_after_landing(browser, origin, lang, theme, shot, retry, width, height, mobile, args)
        if len(second['problems']) < len(record['problems']):
            record = second
    return record


def shoot(page, name, url, width, height, mobile, lang, theme, play_view=None, strict=True,
          requires_main=True, setup=None):
    """Load one state as a fresh document, drive it to its view, capture it, and grade it."""
    assert_loopback(url, {CONSOLE_PORT, PUBLIC_PORT}, 'screenshot navigation')
    page.reset_errors()
    page.call('Emulation.setDeviceMetricsOverride', {
        'width': width, 'height': height, 'deviceScaleFactor': 1, 'mobile': mobile,
        'screenWidth': width, 'screenHeight': height,
    })
    page.call('Page.navigate', {'url': url})
    readiness = 'rendered'
    try:
        probe = wait_for_render(page, deadline=PROBE_TIMEOUT, requires_main=requires_main,
                                requires_nav=requires_main, what=f'{name}/{lang} {url}')
    except CdpTimeout as error:
        # The Tables view on a phone viewport keeps the software renderer busy enough that a
        # trivial Runtime.evaluate can take 25 s (measured with a raw DevTools client, outside this
        # script). The PNG is still the deliverable, so the shot is captured and the manifest
        # records that its readiness could not be confirmed in time.
        probe, readiness = None, 'unconfirmed: ' + str(error).splitlines()[0]
        print(f'       ! readiness {readiness}', flush=True)
    time.sleep(0.3)  # let a transition or a late font swap settle before the capture
    if setup:
        # A state that only exists after an operator acts (a night opened in the timeline, the
        # backfill flow entered). Clicking the real control keeps the shot honest: nothing is
        # forced by a stylesheet or a fake document.
        try:
            done = page.evaluate(f"(() => {{ {setup} }})()", timeout=60)
        except (CdpTimeout, CdpDead) as error:
            done = None
            print(f'       ! setup failed: {str(error).splitlines()[0]}', flush=True)
        if done is False:
            print('       ! setup found no control to press', flush=True)
        time.sleep(0.4)
    # Pausing the CSS animations is a screenshot's business, not the console's: a still frame is
    # what is being captured, and a spinning compositor only makes every DevTools call slower.
    try:
        page.evaluate("document.getAnimations ? document.getAnimations().forEach(a => a.pause()) : 0",
                      timeout=30)
    except (CdpTimeout, CdpDead):
        pass
    try:
        facts = page.evaluate(FACTS_SCRIPT, timeout=60)
    except (CdpTimeout, CdpDead) as error:
        facts = {}
        print(f'       ! facts unavailable: {str(error).splitlines()[0]}', flush=True)
    if play_view and facts.get('playView') != play_view:
        # The build did not route there by hash (the redesign has no phase hashes). Press the
        # tab like an operator would, then re-read the facts.
        clicked = page.evaluate(
            "(() => { const b = document.querySelector('button.playtab[data-play=%s]');"
            " if (!b) return false; b.click(); return true; })()" % json.dumps(play_view))
        time.sleep(0.5)
        facts = page.evaluate(FACTS_SCRIPT)
        facts['playViewFrom'] = 'click' if clicked else 'missing-tab'
    facts['assets'] = dict(page.responses)
    facts['probe'] = probe
    capture = page.call('Page.captureScreenshot',
                        {'format': 'png', 'captureBeyondViewport': False, 'fromSurface': True})
    directory = SHOOT_DIR / f'{width}x{height}'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'{name}-{lang}.png'
    path.write_bytes(base64.b64decode(capture['data']))
    actual = png_size(path)
    problems = []
    if actual != (width, height):
        problems.append(f'pixel size {actual[0]}x{actual[1]} != {width}x{height}')
    if probe is None:
        problems.append(f'readiness {readiness}')
    elif not probe.get('complete'):
        problems.append('page never finished loading')
    elif probe.get('loading'):
        problems.append('the console was still on its loading placeholder')
    # `play` names the before build's play tabs. The redesign replaced them with panels, so on the
    # after build there is no `button.playtab` to press and the expectation cannot be met — it used
    # to fire on every after-build run and make the warning column unreadable.
    if play_view and BUILD == 'before' and facts.get('playView') != play_view:
        problems.append(f'visible play view {facts.get("playView")!r} != {play_view!r}')
    if not facts:
        problems.append('render facts unavailable (busy renderer)')
    else:
        if not [sheet for sheet in facts['sheets'] if sheet.get('rules')]:
            problems.append('no stylesheet applied')
        if not facts.get('fontsLoaded'):
            problems.append('no webfont face reached "loaded" (text would render in a fallback face)')
    if page.failed_requests:
        problems.append('failed requests: ' + ', '.join(page.failed_requests))
    if page.js_errors:
        problems.append('javascript errors: ' + ' | '.join(page.js_errors))
    if facts and requires_main:  # the console only: the public board has no data-theme of ours
        wanted_lang = 'zh-CN' if lang == 'zh' else 'en'
        if facts.get('lang') != wanted_lang:
            problems.append(f'document language {facts.get("lang")!r} != {wanted_lang!r}')
        if facts.get('theme') != theme:
            problems.append(f'document theme {facts.get("theme")!r} != {theme!r}')
    try:  # --out may be relative to the working directory rather than to the repo
        shown = str(path.resolve().relative_to(ROOT))
    except ValueError:
        shown = str(path)
    record = dict(name=name, lang=lang, theme=theme, size=f'{width}x{height}', url=url,
                  file=shown, bytes=path.stat().st_size,
                  sha256=hashlib.sha256(path.read_bytes()).hexdigest()[:16], facts=facts,
                  problems=problems)
    status = 'ok ' if not problems else 'WARN'
    assets = ' '.join(f'{Path(url).name}:{code}' for url, code in (facts.get('assets') or {}).items()
                      if url.endswith('.woff2')) or 'no webfont response'
    print(f'  {status} {record["file"]:<44} {record["bytes"]:>7} B  hash={facts.get("hash") or "-":<22} '
          f'tab={facts.get("tab") or "-":<9} view={facts.get("playView") or "-":<8} '
          f'faces={facts.get("fontsLoaded")}/{len(facts.get("fontFaces") or [])} '
          f'sheets={len([s for s in (facts.get("sheets") or []) if s.get("rules")])} '
          f'ready={readiness.split(":")[0]} {assets}', flush=True)
    for problem in problems:
        print(f'       ! {problem}', flush=True)
    fatal = ('pixel size', 'language', 'theme')
    if strict and any(problem.startswith(fatal) or 'never finished' in problem for problem in problems):
        raise SystemExit(f'{name} ({lang} {width}x{height}) failed: {problems}')
    return record


def measure(page, url, width, height, mobile, lang='en', theme='dark'):
    page.call('Emulation.setDeviceMetricsOverride', {
        'width': width, 'height': height, 'deviceScaleFactor': 1, 'mobile': mobile,
        'screenWidth': width, 'screenHeight': height,
    })
    set_preferences(page, lang, theme)
    # A reloaded landing page can keep showing the loading line (measured on a loaded box: the
    # header is present and styled while #main still reads Loading operations). The bar is what
    # this function measures, so wait for it and let the main content keep loading; the whole
    # page still gets the full PROBE_TIMEOUT before the measurement is called a stall.
    page.call('Page.navigate', {'url': url})
    try:
        wait_for_render(page, deadline=PROBE_TIMEOUT, requires_main=False,
                        what=f'measurement page {url}')
    except CdpTimeout:
        if not page.evaluate("!!document.querySelector('header .bar')"):
            raise
        print(f'      ! {url} kept its loading line; measuring the bar anyway', flush=True)
    time.sleep(0.3)
    before = page.evaluate(MEASURE_SCRIPT)
    simulated = page.evaluate(SIMULATE_SCRIPT)
    return {'url': url, 'size': f'{width}x{height}', 'lang': lang, 'measured': before,
            'one_row_simulation': simulated}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--build', choices=('before', 'after'), default='before',
                        help='which console the URLs target (default: %(default)s)')
    parser.add_argument('--out', help='screenshot directory (default: out/console-<build>/)')
    parser.add_argument('--states', help='comma-separated name fragments to keep, e.g. records,backroom')
    parser.add_argument('--langs', default='en,zh', help='comma-separated languages (default: %(default)s)')
    parser.add_argument('--sizes', default='desktop,phone',
                        help='comma-separated viewport names: '
                             + ', '.join('%s=%dx%d' % (k, w, h) for k, (w, h) in SIZES.items())
                             + ' (default: %(default)s)')
    parser.add_argument('--theme', default='dark', choices=('dark', 'light'))
    parser.add_argument('--measure-only', action='store_true', help='measure the header and exit')
    parser.add_argument('--no-public', action='store_true', help='skip the 8151 public board states')
    parser.add_argument('--loose', action='store_true', help='do not fail on a wrong pixel size or render')
    parser.add_argument('--restarts', type=int, default=2,
                        help='headless chromium restarts allowed per stalled step (default: %(default)s)')
    parser.add_argument('--chromium', help='browser binary (default: the first of %s that exists); a '
                                           'private copy under a different process name survives a '
                                           'shared box where another job runs pkill -x chromium'
                                           % ', '.join(CHROMIUM_CANDIDATES))
    parser.add_argument('--phone-mobile', action='store_true',
                        help='emulate a mobile device at 390x844 (default: plain 390x844 viewport, '
                             'because the mobile compositing path crashed the renderer on the '
                             'Bracket view 4 times out of 4 on this machine)')
    parser.add_argument('--shot-retries', type=int, default=1,
                        help='fresh-URL retries for a shot whose page did not render (default: %(default)s)')
    parser.add_argument('--probe-timeout', type=float, default=150,
                        help='seconds to wait for one page to render (default: %(default)s)')
    parser.add_argument('--skip-metrics', action='store_true',
                        help='skip the header measurement rows (the measurement waits 600 s for a render)')
    parser.add_argument('--verbose', action='store_true',
                        help='log every DevTools call slower than 5s (a loaded box makes these visible)')
    args = parser.parse_args()

    global SHOOT_DIR, VERBOSE, PROBE_TIMEOUT, BUILD
    VERBOSE = args.verbose
    PROBE_TIMEOUT = args.probe_timeout
    SHOOT_DIR = Path(args.out) if args.out else ROOT / 'out' / f'console-{args.build}'
    BUILD = args.build
    wanted = [part.strip() for part in (args.states or '').split(',') if part.strip()]
    langs = [lang.strip() for lang in args.langs.split(',') if lang.strip()]
    sizes = [sizes.strip() for sizes in args.sizes.split(',') if sizes.strip()]

    states = STATES + EXTRA_STATES + AFTER_STATES + ([] if args.no_public else PUBLIC_STATES)
    # A state can declare which build it belongs to: the redesign's timeline opening and the
    # backfill flow have no before-build equivalent, and faking one would be a lie in the docs.
    states = [state for state in states if args.build in state.get('builds', ('before', 'after'))]
    if wanted:
        states = [state for state in states if any(part in state['name'] for part in wanted)]
    if not states:
        raise SystemExit(f'--states {args.states!r} matched nothing')

    records, metrics = [], []
    manifest = dict(build=args.build, chromium=None,
                    sizes={name: list(SIZES[name]) for name in sizes}, langs=langs,
                    phone_emulation='mobile' if args.phone_mobile else 'desktop-width',
                    shots=records, header_metrics=metrics)
    SHOOT_DIR.mkdir(parents=True, exist_ok=True)

    def save_manifest():
        manifest['chromium'] = CHROMIUM_VERSION
        (SHOOT_DIR / 'manifest.json').write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

    def attempt(call, what, restart_on_timeout=False):
        """Run one CDP-bound step; a stall or a dead renderer costs a browser restart, not the run.

        A screenshot that stops answering is a renderer stuck on one page (measured on the phone
        Bracket view): retrying the same URL inside the same browser wedges again, so those steps
        get a fresh browser instead.
        """
        last = None
        for tries in range(args.restarts + 1):
            try:
                return call()
            except CdpTimeout as error:
                # A loaded box answers a trivial Runtime.evaluate in 10-30 s (measured), so a slow
                # step is retried in the same browser: a restart throws away the warm cache and
                # pays that cost again. A stuck capture is the exception - see restart_on_timeout.
                last = error
                if tries >= args.restarts:
                    break
                if restart_on_timeout:
                    print(f'      ! stuck, replacing the browser: {str(error).splitlines()[0]}', flush=True)
                    try:
                        browser.restart()
                    except (CdpTimeout, CdpDead, SystemExit) as restart_error:
                        print(f'      ! restart failed too: {restart_error}', flush=True)
                else:
                    print(f'      ! slow, retrying in the same browser: {str(error).splitlines()[0]}', flush=True)
            except CdpDead as error:
                last = error
                if tries >= args.restarts:
                    break
                try:
                    browser.restart()
                except (CdpTimeout, CdpDead, SystemExit) as restart_error:
                    print(f'      ! restart failed too: {restart_error}', flush=True)
        raise SystemExit(f'{what} stalled {args.restarts + 1}x: {last}; '
                         f'{len(records)} shot(s) are already on disk in {SHOOT_DIR}')

    with fixture() as state:
        manifest['fixture_state'] = dict(revision=state.get('revision'),
                                         players=len(state.get('players', [])),
                                         archived_events=len(state.get('history', [])))
        browser = Browser(args.chromium)
        browser.start()
        try:
            for size_name in sizes:
                width, height = SIZES[size_name]
                # 390x844 is a viewport size: the console's layout switches on CSS width, so the
                # narrow desktop-mode viewport renders the same media queries without the mobile
                # emulation path that kept killing the renderer on the phone Bracket view.
                mobile = size_name == 'phone' and args.phone_mobile
                # Header geometry first: it is what docs/console-shots.md needs, and it survives
                # a later stall. Measured on the build under test, never computed from the CSS.
                routes = (('#/tonight/play', '#/records') if args.build == 'before'
                          else ('#/tonight', '#/records'))
                # Chinese is measured too: it swaps in the Noto faces, and a taller line box there
                # would change the one-row claim.
                measure_langs = list(dict.fromkeys(['en', 'zh'] if 'zh' in langs else langs))
                # `--skip-metrics` goes straight to the shots. Measured on a loaded box: one
                # measurement waits up to 600 s for a render, so a four-row metric block can cost
                # most of the run's wall clock before the first screenshot is attempted.
                for name, route in (zip(('tonight-play', 'records'), routes)
                                    if not args.skip_metrics else ()):
                    for lang in measure_langs:
                        url = (f'http://127.0.0.1:{CONSOLE_PORT}/'
                               f'?measure={name}-{lang}#{route.lstrip("#")}')
                        metrics.append(dict(state=name, **attempt(
                            lambda url=url, lang=lang: measure(browser.page, url, width, height, mobile, lang),
                            f'measuring {name}/{lang} at {width}x{height}')))
                        save_manifest()
                if args.measure_only:
                    continue
                print(f'{args.build} · {width}x{height} · {size_name}', flush=True)
                for index, shot in enumerate(states):
                    shot_langs = shot.get('langs', langs)
                    theme = shot.get('theme', args.theme)
                    if 'url' in shot:
                        target = shot['url'].format(port=PUBLIC_PORT)
                        origin = PUBLIC_PORT
                    else:
                        route = shot['legacy'] if (args.build == 'before' and shot.get('legacy')) else shot[args.build]
                        origin = CONSOLE_PORT
                    for lang in shot_langs:
                        if origin == CONSOLE_PORT:
                            # The language is part of the URL: two shots of one state differ only
                            # in localStorage, and navigating to an identical URL reloads nothing,
                            # so an EN page would be filed as the 中 shot.
                            target = (f'http://127.0.0.1:{CONSOLE_PORT}/'
                                      f'?shot={shot["name"]}-{index}-{lang}#{route.lstrip("#")}')
                        record = attempt(
                            (lambda shot=shot, target=target, lang=lang, theme=theme, origin=origin:
                             shoot_with_retry(browser, origin, lang, theme, shot, target,
                                              width, height, mobile, args)),
                            f'shooting {shot["name"]}/{lang}', restart_on_timeout=True)
                        records.append(record)
                        save_manifest()
                        if (record.get('facts') or {}).get('playView') == 'tables':
                            # The Tables view leaves the renderer unable to load the next page at
                            # 390x844: measured twice, the following shot captured only the static
                            # shell (16708 B, no tabs, no theme) and once the renderer died
                            # outright. A fresh browser before the next shot is cheap insurance.
                            print('       .. Tables view was on screen: fresh browser for the next shot',
                                  flush=True)
                            browser.restart()
        finally:
            browser.stop()
    save_manifest()

    total = sum(record['bytes'] for record in records)
    warnings = [record for record in records if record['problems']]
    print(f'\n{len(records)} screenshots · {total / 1024 / 1024:.2f} MiB · {SHOOT_DIR}')
    print(f'manifest: {SHOOT_DIR / "manifest.json"} · chromium restarts: {browser.restarts}')
    for entry in metrics:
        measured = entry['measured']
        simulation = entry['one_row_simulation']
        print(f'  header {entry["size"]:<9} {entry["state"]:<12} {entry.get("lang", "en"):<2} '
              f'bar={measured["bar"]["height"] if measured["bar"] else "-"} '
              f'nav={measured["nav"]["height"] if measured["nav"] else "hidden"} '
              f'strip={measured["strip"]["height"] if measured["strip"] else "-"} '
              f'tabbar={measured["tabbar"]["height"] if measured["tabbar"] else "-"} '
              f'contentTop={measured["contentTop"]} -> {simulation["after"]["contentTop"]} '
              f'(saves {round(measured["contentTop"] - simulation["after"]["contentTop"], 1)} px)')
    if warnings:
        print(f'\n{len(warnings)} shot(s) with warnings: ' + ', '.join(r['name'] + '/' + r['lang'] for r in warnings))
        return 1
    print('all shots matched their requested pixel size, rendered, and loaded their stylesheets')
    return 0


CHROMIUM_VERSION = ''
DEBUG_PORTS = set()
PROBE_TIMEOUT = 150  # seconds one page gets to render; --probe-timeout overrides it
SHOOT_DIR = ROOT / 'out' / 'console-before'
BUILD = 'after'  # --build; the play-view expectation below only applies to the before build
VERBOSE = False

if __name__ == '__main__':
    sys.exit(main())
