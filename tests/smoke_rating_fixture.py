"""One process, four surfaces: the seeded club, the console, the review workspace and the board.

    PYTHONPATH=. .venv/bin/python tests/smoke_rating_fixture.py --label after

Why it exists (docs/console-redesign.md SS14.9, F1's environment half): the fixture the
reviewer was pointed at, tests/serve_operations_fixture.py, deliberately populates no
review tools, so its review workspace can only answer with the red `media not found`
callout. tests/serve_workbench_fixture.py has the media but used to have no seeded club,
no board listener and a hardcoded port. This script starts it with the club seeded and
proves, over HTTP and in headless chromium, that all four surfaces answer:

  * the console (GET /), the public board (GET / on --public-port) and /api/board
  * the review workspace: the Vision tab mounts, the stage decodes a frame (#t-img with a
    natural size) and no 'unavailable' callout is anywhere in the DOM
  * two review routes asked of this fixture and of the media-less operations fixture:
    /api/frame?dataset=vod30&frame=0 answers 200 with a JPEG here and 404
    {"error": "media not found"} there, while /api/vod30/tracklets answers 200 on both
    (the absent media is what 404s; the annotation routes degrade instead)

The board half of the evidence (F20) is the text and PNG it writes to out/console-<label>/
for 1280x900 and 390x844 in both languages, in two runs: the seeded club as shipped, and a
copy of it whose live matches went on the table minutes ago (out/console-<label>/state-fresh
.json, written here and never into tests/), so the same board is measured both on an old
record and on a night in progress. --stale stops the fixture's process mid-run (SIGSTOP) and
records what the board does when the server stops answering: the stale notice, and table
numbers that stop moving instead of counting on.
Exit status is 0 only if every surface answered; the measured report lands in
out/console-<label>/smoke.json.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
# The shot harness owns the browser: the same websocket client, the same CDP session and
# the same PNG check, so a board caption here is measured the way the shots are. Its
# launcher is pinned to the shot ports (8150/8151) and refuses anything else, so this
# script launches chromium itself and reuses everything below that.
from console_shots import CHROMIUM_CANDIDATES, Devtools, free_port, png_size

SIZES = [('1280x900', 1280, 900), ('390x844', 390, 844)]
LANGS = ['en', 'zh']


class SmokeError(SystemExit):
    pass


def port_is_free(port):
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(('127.0.0.1', port))
        except OSError:
            return False
    return True


def http_get(url, expect=200, timeout=30):
    request = urllib.request.Request(url, headers={'Accept': '*/*'})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            status, headers = response.status, dict(response.headers)
    except urllib.error.HTTPError as error:
        body, status, headers = error.read(), error.code, dict(error.headers)
    if expect is not None and status != expect:
        raise SmokeError(f'{url} answered {status}, expected {expect}: {body[:200]!r}')
    return {'status': status, 'headers': headers, 'body': body, 'url': url}


def wait_for_port(port, process, what, deadline=60):
    until = time.time() + deadline
    while time.time() < until:
        if process.poll() is not None:
            raise SmokeError(f'the fixture exited with {process.returncode} before {what} answered')
        with socket.socket() as probe:
            probe.settimeout(1)
            if probe.connect_ex(('127.0.0.1', port)) == 0:
                return
        time.sleep(0.2)
    raise SmokeError(f'{what} did not answer on 127.0.0.1:{port} within {deadline}s')


@contextmanager
def fixture(script, ports, arguments, log_path):
    """A fixture subprocess whose stdout is drained, mirroring tests/console_shots.py.

    Once the 64 KiB pipe buffer fills, the fixture blocks inside its own logging and every
    request hangs: measured twice in this repo as a process that is alive, LISTENing, at
    0 % CPU, with every path timing out.
    """
    environment = dict(os.environ, PYTHONPATH='.')
    environment.pop('POOL_DATABASE_URL', None)
    log = log_path.open('w')
    process = subprocess.Popen([str(ROOT / '.venv' / 'bin' / 'python'), str(ROOT / 'tests' / script)] + arguments,
                               cwd=ROOT, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    def drain():
        for line in process.stdout:
            log.write(line)
            log.flush()
    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    try:
        for port in ports:
            wait_for_port(port, process, f'the fixture ({script})')
        yield process
    finally:
        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
        log.close()
        for port in ports:
            if not port_is_free(port):
                raise SmokeError(f'127.0.0.1:{port} is still bound after the fixture stopped')


class Chromium:
    """Headless chromium with one debuggable page: enough for a board and a console tab."""

    def __init__(self, binary=None):
        self.binary = binary or next((path for path in CHROMIUM_CANDIDATES if Path(path).exists()), None)
        if not self.binary or not Path(self.binary).exists():
            raise SmokeError('no chromium found: pass --chromium')
        self.process = self.page = self.profile = self.port = None

    def __enter__(self):
        self.port, self.profile = free_port(), Path(tempfile.mkdtemp(prefix='cp-smoke-'))
        command = [self.binary, '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
                   '--no-first-run', '--no-default-browser-check', '--disable-features=BackForwardCache',
                   '--force-color-profile=srgb', '--force-device-scale-factor=1',
                   '--remote-debugging-port=' + str(self.port), '--user-data-dir=' + str(self.profile),
                   '--window-size=1440,960', 'about:blank']
        self.process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        target, version = None, {}
        deadline = time.time() + 240
        while time.time() < deadline and self.process.poll() is None and target is None:
            try:
                version = json.load(urllib.request.urlopen(f'http://127.0.0.1:{self.port}/json/version', timeout=20))
                pages = [t for t in json.load(urllib.request.urlopen(f'http://127.0.0.1:{self.port}/json/list', timeout=20))
                         if t.get('type') == 'page' and t.get('webSocketDebuggerUrl')]
                target = pages[0] if pages else None
            except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError):
                pass
            if target is None:
                time.sleep(0.25)
        if target is None:
            raise SmokeError('headless chromium did not expose a debuggable page')
        print(f'{subprocess.run([self.binary, "--version"], capture_output=True, text=True).stdout.strip()}'
              f' · devtools on 127.0.0.1:{self.port}', flush=True)
        self.page = Devtools(target['webSocketDebuggerUrl'])
        for method in ('Page.enable', 'Runtime.enable', 'Log.enable', 'Network.enable'):
            self.page.call(method)
        self.page.call('Network.clearBrowserCache')
        return self

    def __exit__(self, *exception):
        try:
            self.page.close()
        except Exception:  # a broken socket must not mask the real failure
            pass
        self.process.terminate()
        try:
            self.process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.process.kill()

    def viewport(self, width, height, mobile=False):
        self.page.call('Emulation.setDeviceMetricsOverride', {
            'width': width, 'height': height, 'deviceScaleFactor': 1, 'mobile': mobile,
            'screenWidth': width, 'screenHeight': height})

    def until(self, expression, what, deadline=30, interval=0.25):
        """Poll an expression in the page until it is truthy; return the value."""
        until = time.time() + deadline
        value = None
        while time.time() < until:
            value = self.page.evaluate(f'(() => {{ try {{ return {expression}; }} catch (e) {{ return null; }} }})()')
            if value:
                return value
            time.sleep(interval)
        raise SmokeError(f'{what} did not happen within {deadline}s (last value {value!r})')

    def shot(self, path):
        data = self.page.call('Page.captureScreenshot',
                              {'format': 'png', 'captureBeyondViewport': False, 'fromSurface': True})['data']
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(__import__('base64').b64decode(data))
        return png_size(path)


BOARD_TEXT = """(() => {
  const one = id => (document.getElementById(id) || {}).textContent || '';
  const flat = node => (node ? node.innerText.replace(/\\s+/g, ' ').trim() : '');
  const note = document.getElementById('tables-note');
  const stale = document.getElementById('stale');
  return {
    updated: one('updated'), staleHidden: stale ? stale.hidden : null, stale: one('stale'),
    note: one('tables-note'), noteHidden: note ? note.hidden : null,
    count: document.getElementById('tables').dataset.count,
    onTable: [...document.querySelectorAll('#tables .on-table')].map(flat),
    lateCards: document.querySelectorAll('#tables .table-card.late').length,
    elapsedRaw: [...document.querySelectorAll('#tables .table-card')].map(card => card.dataset.elapsed || null),
    cards: [...document.querySelectorAll('#tables .table-card')].map(card => flat(card)),
    foot: [...document.querySelectorAll('#tables .card-foot')].map(flat),
  };
})()"""


def board_check(browser, url, out, label, sizes, langs, name='board'):
    """The board at each size and language: text read from the DOM, plus a PNG of it."""
    measured = []
    for name_size, width, height in sizes:
        for lang in langs:
            browser.viewport(width, height, mobile=width < 600)
            browser.page.call('Page.navigate', {'url': f'{url}?lang={lang}&smoke={int(time.time())}'})
            browser.until("document.getElementById('tables') && document.getElementById('tables').innerHTML.trim()",
                          f'the board to render at {name_size} {lang}')
            browser.until("document.getElementById('updated').textContent.trim() !== 'Connecting…'",
                          f'the board to confirm an answer at {name_size} {lang}')
            facts = browser.page.evaluate(BOARD_TEXT)
            path = out / f'{name}-{name_size}-{lang}.png'
            facts['png'], facts['pngSize'] = str(path.relative_to(ROOT)), browser.shot(path)
            facts['size'], facts['lang'], facts['url'] = name_size, lang, url
            measured.append(facts)
            print(f'  {label} {name} {name_size} {lang}: onTable={facts["onTable"]} note={facts["note"]!r} '
                  f'(hidden={facts["noteHidden"]}) late={facts["lateCards"]} updated={facts["updated"]!r} '
                  f'stale={facts["stale"]!r} png={facts["png"]} {facts["pngSize"]}', flush=True)
    return measured


def fresh_state(source, destination, minutes=(8, 12, 20)):
    """A copy of the seeded club with its live matches re-anchored to minutes ago.

    Evidence only, and never written into tests/: the fixture's own --state file is served
    byte-identical. The shipped club was seeded on 2026-10-03 with its three live matches
    scheduled at 05:23Z, so on any later day the board correctly reads a 12 h old record;
    this copy exists so the same code can also be measured on a night in progress.
    """
    document = json.loads(Path(source).read_text())
    live = sorted((m for m in document['tournament']['matches'] if m.get('status') == 'live'),
                  key=lambda m: int(m.get('table') or 0))
    now = datetime.now(timezone.utc)
    for match, offset in zip(live, minutes):
        for event in document['events']:
            if event.get('action') == 'match_schedule' and (event.get('context') or {}).get('id') == match['id']:
                event['createdAt'] = (now - timedelta(minutes=offset)).isoformat()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(document, indent=2, ensure_ascii=False) + '\n')
    return {'matches': [{'table': m.get('table'), 'minutes': offset} for m, offset in zip(live, minutes)],
            'path': str(destination.relative_to(ROOT))}


def review_check(browser, base, out, log_path):
    """The review workspace on the console: mounted, decoding a frame, no callout."""
    url = base + '/'
    browser.viewport(1440, 900)
    browser.page.call('Page.navigate', {'url': f'{url}?smoke={int(time.time())}'})
    browser.until("!!document.querySelector('#nav button[data-tab=\"vision\"]')", 'the console nav to render')
    browser.page.evaluate("document.querySelector('#nav button[data-tab=\"vision\"]').click()")
    browser.until("!!document.querySelector('#vision-host #review-root')",
                  'the review workspace markup to mount (/api/review-template)', deadline=60)
    stage = browser.until("document.querySelector('#content').dataset.stage === '1'",
                          'the review stage to render', deadline=90)
    frame = browser.until("""(() => { const image = document.querySelector('#t-img');
        return image && image.naturalWidth > 0 ? {src: image.currentSrc || image.src,
        width: image.naturalWidth, height: image.naturalHeight} : null; })()""",
                          'the review stage to decode a frame', deadline=90)
    facts = browser.page.evaluate("""(() => ({
        placeholder: !!document.querySelector('#content .empty'),
        placeholderText: (document.querySelector('#content .empty') || {}).textContent || '',
        callout: /unavailable|not found|media not found|不可用/i.test(document.body.innerText),
        heading: (document.querySelector('#review-root h1, #review-root h2, #content') || {}).textContent || '',
        src: (document.querySelector('#t-img') || {}).src || '',
    }))()""")
    # What the workspace actually asked the server for: the fixture's own access log,
    # which is also the list of routes a rating fixture has to answer.
    asked = sorted(set(re.findall(r'"(?:GET|HEAD) (/api/\S+) HTTP', log_path.read_text(errors='replace'))))
    facts.update({'stageRendered': stage, 'frame': frame, 'apiAsked': asked, 'url': url})
    path = out / 'review-workspace.png'
    facts['png'], facts['pngSize'] = str(path.relative_to(ROOT)), browser.shot(path)
    print(f'  review workspace: mounted, stage={stage}, frame={frame["width"]}x{frame["height"]} from {frame["src"]} '
          f'placeholder={facts["placeholder"]} callout={facts["callout"]} png={facts["png"]} {facts["pngSize"]}',
          flush=True)
    print(f'  the workspace asked for {len(asked)} API paths, among them '
          f'{[path for path in asked if path.startswith(("/api/video", "/api/frame", "/api/vod30"))]}', flush=True)
    return facts


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--label', default='after', help='names the output folder out/console-<label> (default: after)')
    parser.add_argument('--port', type=int, default=8167, help='the review fixture console (default: 8167)')
    parser.add_argument('--public-port', type=int, default=8168, help='its public board listener (default: 8168)')
    parser.add_argument('--prefix', default='/board', help='the board mount (default: /board)')
    parser.add_argument('--state', default='tests/console_fixture_state.json', help='the seeded club')
    parser.add_argument('--ops-port', type=int, default=8169,
                        help='a second, media-less fixture used for the before half of the F1 pair')
    parser.add_argument('--chromium', help='a chromium binary (default: the first candidate on PATH)')
    parser.add_argument('--stale', action='store_true',
                        help='stop the fixture mid-run and record what the board says without a server')
    parser.add_argument('--sizes', default='1280x900,390x844', help='board viewports to measure')
    parser.add_argument('--no-fresh', action='store_true',
                        help='skip the second run against a club whose live matches started minutes ago')
    args = parser.parse_args()
    name, _, size = args.label.partition('-')  # 'after' and 'before' name the pair the brief asks for

    out = ROOT / 'out' / f'console-{args.label}'
    out.mkdir(parents=True, exist_ok=True)
    sizes = []
    for spec in args.sizes.split(','):
        match = re.fullmatch(r'(\d+)x(\d+)', spec.strip())
        if not match:
            raise SmokeError(f'--sizes wants WxH pairs, got {spec!r}')
        sizes.append((spec.strip(), int(match.group(1)), int(match.group(2))))
    console = f'http://127.0.0.1:{args.port}'
    board = f'http://127.0.0.1:{args.public_port}{args.prefix}'
    if args.port == 8137 or args.public_port == 8138 or 8130 in (args.port, args.public_port):
        raise SmokeError('refusing to use the production (8130/8132) or live rating (8137/8138) ports')
    report = {'label': args.label, 'console': console, 'board': board, 'state': args.state, 'checks': {}}
    print(f'review fixture on {console} + {board}, seeded from {args.state}', flush=True)

    arguments = ['--port', str(args.port), '--public-port', str(args.public_port), '--public-prefix', args.prefix,
                 '--state', args.state]
    with fixture('serve_workbench_fixture.py', [args.port, args.public_port], arguments,
                 out / 'review-fixture.log') as fixture_process:
        # 1. The surfaces answer, over HTTP, before any browser is involved.
        console_page = http_get(console + '/')
        board_page = http_get(board + '/')
        api = http_get(board + '/api/board')
        payload = json.loads(api['body'])
        template = http_get(console + '/api/review-template')
        datasets = json.loads(http_get(console + '/api/datasets')['body'])
        report['checks']['http'] = {
            'console': console_page['status'], 'board': board_page['status'], 'apiBoard': api['status'],
            'revision': payload.get('revision'), 'tables': len(payload.get('tables', [])),
            'since': [m.get('since') for m in payload.get('tables', [])],
            'reviewTemplate': template['status'], 'reviewTemplateHasRoot': b'review-root' in template['body'],
            'datasets': [d.get('id') or d.get('name') for d in (datasets if isinstance(datasets, list)
                                                                else datasets.get('datasets', []))],
        }
        print(f'  http: console {console_page["status"]}, board {board_page["status"]}, /api/board {api["status"]} '
              f'revision {payload.get("revision")} with {len(payload.get("tables", []))} tables in play, '
              f'/api/review-template {template["status"]} (review-root: '
              f'{report["checks"]["http"]["reviewTemplateHasRoot"]})', flush=True)
        if not payload.get('tables'):
            raise SmokeError('the seeded club has no live table: the board evidence would be empty')

        with Chromium(args.chromium) as browser:
            # 2. The review workspace: the half the rating fixture could not do.
            review = review_check(browser, console, out, out / 'review-fixture.log')
            report['checks']['review'] = review
            if review['placeholder'] or review['callout']:
                raise SmokeError(f'the review workspace still shows its placeholder/callout: {review}')
            # 3. The measured before/after for the environment half: the two routes the
            # workspace asks for footage on, asked of a media-less operations fixture and
            # of this one. A frame is decoded pixels (small), not the 690 MB VOD.
            dataset = next((urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)['dataset'][0]
                            for path in review['apiAsked'] if path.startswith('/api/video?dataset=')), 'vod30')
            asked = [f'/api/frame?dataset={dataset}&frame=0', f'/api/vod30/tracklets']
            report['checks']['media'] = {'dataset': dataset, 'routes': []}
            ops_arguments = ['--port', str(args.ops_port), '--state', args.state]
            with fixture('serve_operations_fixture.py', [args.ops_port], ops_arguments, out / 'ops-fixture.log'):
                for route in asked:
                    here = http_get(console + route, expect=None)
                    there = http_get(f'http://127.0.0.1:{args.ops_port}' + route, expect=None)
                    row = {'route': route, 'reviewFixture': here['status'], 'reviewBytes': len(here['body']),
                           'reviewType': here['headers'].get('Content-Type'),
                           'opsFixture': there['status'],
                           'opsFixtureBody': there['body'][:120].decode('utf-8', 'replace').strip()}
                    report['checks']['media']['routes'].append(row)
                    print(f'  {route}: this fixture {row["reviewFixture"]} ({row["reviewBytes"]} bytes '
                          f'{row["reviewType"]}), the operations fixture {row["opsFixture"]} '
                          f'{row["opsFixtureBody"]!r}', flush=True)

            # 4. The board (F20): rendered text and a PNG at each size and language.
            report['checks']['board'] = board_check(browser, board, out, args.label, sizes, LANGS)

            # 5. What the board does when the server stops answering. The page has to be
            #    loaded first and only then frozen: a navigate while the fixture is SIGSTOPped
            #    never gets an answer, and its CDP call hangs for the full 600 s timeout
            #    (measured once, on the way to this order).
            if args.stale:
                browser.viewport(1280, 900)
                browser.page.call('Page.navigate', {'url': f'{board}/?lang=en&stale={int(time.time())}'}, timeout=60)
                browser.until("document.getElementById('tables') && document.getElementById('tables').innerHTML.trim()",
                              'the board to render before it is frozen')
                browser.until("document.getElementById('updated').textContent.trim() !== 'Connecting…'",
                              'the board to confirm an answer before it is frozen')
                os.kill(fixture_process.pid, signal.SIGSTOP)
                try:
                    first = browser.until("""(() => { const stale = document.getElementById('stale');
                        return !stale.hidden ? {updated: document.getElementById('updated').textContent,
                        stale: stale.textContent, onTable: [...document.querySelectorAll('#tables .on-table')]
                            .map(node => node.innerText.replace(/\\s+/g, ' ').trim()),
                        elapsedRaw: [...document.querySelectorAll('#tables .table-card')]
                            .map(card => card.dataset.elapsed || null)} : null; })()""",
                                          'the stale notice after the fixture stopped answering', deadline=120)
                    # 65 s, not 6: the card's number is printed in minutes, so only a gap longer
                    # than a minute can show whether it is still counting while no answer arrives.
                    time.sleep(65)
                    second = browser.page.evaluate("""(() => ({updated: document.getElementById('updated').textContent,
                        onTable: [...document.querySelectorAll('#tables .on-table')]
                            .map(node => node.innerText.replace(/\\s+/g, ' ').trim()),
                        elapsedRaw: [...document.querySelectorAll('#tables .table-card')]
                            .map(card => card.dataset.elapsed || null)}))()""")
                    path = out / 'board-1280x900-en-stale.png'
                    report['checks']['stale'] = {'atNotice': first, 'sixtyFiveSecondsLater': second,
                                                 'frozen': first['onTable'] == second['onTable'],
                                                 'png': str(path.relative_to(ROOT)), 'pngSize': browser.shot(path)}
                    print(f'  stale: {first["stale"]!r} updated={first["updated"]!r} '
                          f'onTable {first["onTable"]} -> {second["onTable"]} (frozen='
                          f'{report["checks"]["stale"]["frozen"]}, elapsedMs {first["elapsedRaw"]} -> '
                          f'{second["elapsedRaw"]}) png={report["checks"]["stale"]["png"]}', flush=True)
                finally:
                    os.kill(fixture_process.pid, signal.SIGCONT)

    # 6. The other face of the clock, same code: a club whose live matches went on the table
    #    minutes ago. The shipped seed was built on 2026-10-03, so on any later day the
    #    seeded club is 12 h old by construction and the board correctly says so; this run
    #    re-anchors a copy of it under out/ (never into tests/) to measure the small,
    #    plausible number the same board prints on a night in progress.
    if not args.no_fresh:
        fresh = fresh_state(args.state, out / 'state-fresh.json')
        fresh_arguments = ['--port', str(args.port), '--public-port', str(args.public_port),
                           '--public-prefix', args.prefix, '--state', fresh['path']]
        print(f'  fresh club: {fresh["path"]} with live matches at {fresh["matches"]} minutes', flush=True)
        with fixture('serve_workbench_fixture.py', [args.port, args.public_port], fresh_arguments,
                     out / 'review-fresh.log'):
            with Chromium(args.chromium) as browser:
                report['checks']['boardFresh'] = board_check(browser, board, out, args.label, sizes, LANGS,
                                                             name='board-fresh')
        report['checks']['freshState'] = fresh

    report_path = out / 'smoke.json'
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(f'smoke: {name} evidence in {out.relative_to(ROOT)} (measured report {report_path.relative_to(ROOT)})',
          flush=True)


if __name__ == '__main__':
    main()
