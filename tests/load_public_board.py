#!/usr/bin/env python
"""50-phone polling load test for the read-only public board (docs/public-board-load.md).

Starts one isolated fixture -- tests/serve_operations_fixture.py, whose --public-port grew
the same second listener annotator/unified_server.py's --public-port serves -- on two free
loopback ports at or above 8230, mounts the board at --public-prefix /board, and drives it
the way the club's phones do: N pollers, one conditional GET of the board every 3 s for a
fixed window, with the same number of pollers reading GET /api/operations on the console
over that same window. Reports latency percentiles (p50/p95/p99), the 304 share, errors,
the fixture process's CPU time (/proc/<pid>/stat utime+stime) as a percentage of one core,
and the machine's load average.

Loopback only, and asserted per request: every connection checks its host against the
loopback set *and* its port against the two ports this script itself started, so a run
cannot be pointed at production and cannot touch it by accident. Only GET is ever sent,
and only to the fixture. Production is never in scope here.

Stdlib only. From the repository root:

    .venv/bin/python tests/load_public_board.py
    .venv/bin/python tests/load_public_board.py --seconds 60 --json out/load-board.json

Exit status 0 means every assertion held: no failed requests above --max-error-rate, no
p95 above --p95-ms on either surface, the preflight found the fixture serving both
surfaces correctly, and the fixture was cleaned up (process reaped, both ports refusing,
its temporary root gone). Any other outcome is a non-zero exit with the reasons listed.
"""
import argparse
import http.client
import json
import math
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "serve_operations_fixture.py"
FIXTURE_LOG = "fixture-output.log"
LOOPBACK_HOSTS = ("127.0.0.1", "::1", "localhost")
FIRST_PORT = 8230
ANSWERS = (200, 304)


# -- origin ---------------------------------------------------------------------

def assert_loopback(host, port, why, allowed_ports):
    """Refuse anything that is not one of our own loopback fixture ports."""
    if host not in LOOPBACK_HOSTS:
        raise AssertionError(f"{why}: refusing to connect to {host!r}; loopback only")
    if port not in allowed_ports:
        raise AssertionError(f"{why}: refusing to connect to port {port}; "
                             f"only this run's fixture ports {sorted(allowed_ports)}")


class Target:
    """One fixture origin. The origin is re-asserted before every single connection."""

    def __init__(self, name, host, port, allowed_ports):
        assert_loopback(host, port, name, allowed_ports)
        self.name, self.host, self.port, self.allowed_ports = name, host, port, allowed_ports

    def request(self, method, path, headers=None, timeout=10.0):
        assert_loopback(self.host, self.port, self.name, self.allowed_ports)
        connection = http.client.HTTPConnection(self.host, self.port, timeout=timeout)
        started = time.perf_counter()
        try:
            connection.request(method, path, headers=headers or {})
            response = connection.getresponse()
            body = response.read()
            return response.status, {key.lower(): value for key, value in response.getheaders()}, \
                body, (time.perf_counter() - started) * 1000.0
        finally:
            connection.close()


# -- measurement ------------------------------------------------------------------

def percentile(values, quantile):
    """Nearest rank: the value at ceil(q * n), 1-based, over a sorted copy."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, math.ceil(quantile * len(ordered)) - 1))]


class Recorder:
    """Thread-safe sample log for one surface.

    Latency is measured from just before the request is written to the moment the whole
    body has been read, and only for answers that count (200/304): a refusal is a
    failure, not a fast latency sample.
    """

    def __init__(self, name):
        self.name = name
        self.lock = threading.Lock()
        self.latencies = []
        self.stamps = []
        self.statuses = Counter()
        self.failures = Counter()
        self.sent = 0

    def answered(self, status, milliseconds):
        with self.lock:
            self.sent += 1
            self.statuses[status] += 1
            if status in ANSWERS:
                self.latencies.append(milliseconds)
                self.stamps.append(time.monotonic())

    def failed(self, reason):
        with self.lock:
            self.sent += 1
            self.failures[reason] += 1

    def summary(self, window_start=None):
        with self.lock:
            statuses = dict(self.statuses)
            failure_reasons = dict(self.failures.most_common(5))
            failures = sum(self.failures.values())
            latencies = list(self.latencies)
            stamps = list(self.stamps)
            sent = self.sent
        refused = sum(count for status, count in statuses.items() if status not in ANSWERS)
        failed = refused + failures
        span = None
        if stamps and window_start is not None:
            span = [max(0.0, min(stamps) - window_start), max(stamps) - window_start]
        return {
            "name": self.name, "sent": sent, "answers": len(latencies), "failed": failed,
            "answer_span_seconds": span,
            "refused_statuses": {str(status): count for status, count in sorted(statuses.items())
                                 if status not in ANSWERS},
            "statuses": {str(status): count for status, count in sorted(statuses.items())},
            "failure_reasons": failure_reasons,
            "not_modified": statuses.get(304, 0),
            "not_modified_share": (statuses.get(304, 0) / len(latencies)) if latencies else None,
            "error_rate": (failed / sent) if sent else None,
            "p50_ms": percentile(latencies, 0.50), "p95_ms": percentile(latencies, 0.95),
            "p99_ms": percentile(latencies, 0.99), "max_ms": max(latencies) if latencies else None,
        }


def pause(seconds, stopped):
    """Sleep, but come back early the moment the run is stopped."""
    end = time.monotonic() + seconds
    while not stopped.is_set():
        remaining = end - time.monotonic()
        if remaining <= 0:
            return
        stopped.wait(min(remaining, 0.25))


def poll(target, path, recorder, deadline, interval, offset, stopped):
    """One phone: a conditional GET every `interval` seconds until `deadline`.

    board.js polls with the last ETag and a 3 s interval; each poller's first request is
    staggered across the interval so 50 phones do not share one clock. The ETag comes from
    the previous 200, exactly as the page keeps it. `stopped` ends the run early -- set
    only when the fixture has died, so the numbers never mix a missing server with a
    slow one.
    """
    if offset:
        pause(offset, stopped)
    etag = None
    while time.monotonic() < deadline and not stopped.is_set():
        started = time.monotonic()
        try:
            status, headers, _body, milliseconds = target.request(
                "GET", path, {"If-None-Match": etag} if etag else None, timeout=5.0)
            if status == 200:
                etag = headers.get("etag") or etag
            recorder.answered(status, milliseconds)
        except Exception as injury:  # refused, reset, timeout: counted, never raised
            recorder.failed(f"{type(injury).__name__}: {injury}")
        remaining = interval - (time.monotonic() - started)
        if remaining > 0:  # never sleep past the end of the window
            pause(min(remaining, max(0.0, deadline - time.monotonic())), stopped)


def watch(process, started, deadline, stopped, death, samples):
    """Note the instant the fixture stops running, so a run can say what it measured.

    A fixture killed from outside (another agent's cleanup on this shared box, a stray
    signal) would otherwise turn into thousands of connection refusals that look like a
    server limit. The exit status is recorded here and reported as a failed assertion.
    CPU ticks are sampled along the way too, so the CPU figure survives a mid-run death
    (once /proc/<pid> is gone there is nothing left to read).
    """
    while time.monotonic() < deadline:
        ticks = cpu_ticks(process.pid)
        if ticks is not None:
            samples["ticks"], samples["at"] = ticks, time.monotonic()
        code = process.poll()
        if code is not None:
            death.update({"exit_code": code, "at_second": time.monotonic() - started,
                          "signal": -code if code < 0 else None})
            stopped.set()
            return
        if stopped.wait(0.2):
            return


def burst(target, count, path):
    """`count` GETs released at once: what the public listener's 16-slot pool does with a
    simultaneous burst. Reported next to the run, never part of its pass/fail contract."""
    recorder, gate = Recorder("burst"), threading.Barrier(count)

    def one():
        gate.wait()
        try:
            status, _headers, _body, milliseconds = target.request("GET", path, timeout=10.0)
            recorder.answered(status, milliseconds)
        except Exception as injury:
            recorder.failed(f"{type(injury).__name__}: {injury}")

    workers = [threading.Thread(target=one) for _ in range(count)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    summary = recorder.summary()
    return {"sent": summary["sent"], "statuses": summary["statuses"],
            "failure_reasons": summary["failure_reasons"], "p50_ms": summary["p50_ms"],
            "p95_ms": summary["p95_ms"], "p99_ms": summary["p99_ms"], "max_ms": summary["max_ms"]}


# -- machine ----------------------------------------------------------------------

def cpu_ticks(pid):
    """utime+stime of `pid` in clock ticks from /proc/<pid>/stat, or None if it is gone."""
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    except (OSError, IndexError):
        return None
    return int(fields[11]) + int(fields[12])  # state is field 3 (index 0), utime/stime 11/12


def loadavg():
    try:
        return " ".join(Path("/proc/loadavg").read_text().split()[:3])
    except OSError:
        return "unavailable"


def port_closed(port, host="127.0.0.1"):
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return False
    except OSError:
        return True


def free_port(start=FIRST_PORT, stop=FIRST_PORT + 200, taken=()):
    """The first free loopback port at or above 8230 (this run's ports live up here)."""
    for port in range(start, stop):
        if port in taken:
            continue
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise SystemExit(f"no free loopback port in {start}..{stop}")


def wait_for_port(port, process, timeout=30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False
        with socket.socket() as probe:
            probe.settimeout(0.5)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.1)
    return False


# -- fixture ----------------------------------------------------------------------

def start_fixture(console_port, public_port, prefix, tmp_root):
    """Start the fixture with its own output going to a file, never to an unread pipe.

    The fixture's console handler logs every request to stderr. Handing it a pipe nobody
    drains fills the 64 KB pipe buffer, and from then on every console handler thread
    blocks in write() -- 50 console pollers then time out forever while the (silent)
    public listener stays healthy. That is a harness bug, not a server limit, so the
    output goes to a file we can read back and report.
    """
    log_path = tmp_root / FIXTURE_LOG
    log = log_path.open("w")
    environment = dict(os.environ, PYTHONPATH=".", TMPDIR=str(tmp_root))
    command = [sys.executable, str(FIXTURE), "--port", str(console_port),
               "--public-port", str(public_port), "--public-prefix", prefix]
    process = subprocess.Popen(command, cwd=str(ROOT), env=environment, text=True,
                               stdout=log, stderr=subprocess.STDOUT)
    return process, command, log, log_path


def stop_fixture(process, ports, tmp_root):
    """SIGINT first: the fixture's own KeyboardInterrupt path removes its temporary root."""
    record = {"pid": process.pid, "signals": [], "exit_code": None, "ports_closed": {},
              "leftover": []}
    for number, name in ((signal.SIGINT, "SIGINT"), (signal.SIGTERM, "SIGTERM"),
                         (signal.SIGKILL, "SIGKILL")):
        if process.poll() is not None:
            break
        record["signals"].append(name)
        try:
            process.send_signal(number)
        except ProcessLookupError:
            break
        try:
            process.wait(timeout=15.0 if name != "SIGKILL" else 5.0)
            break
        except subprocess.TimeoutExpired:
            continue
    record["exit_code"] = process.poll()
    for port in ports:
        record["ports_closed"][port] = port_closed(port)
    record["leftover"] = sorted(path.name for path in tmp_root.iterdir()
                                if path.name != FIXTURE_LOG)
    return record


def read_tail(path, lines=25):
    """Last lines of the fixture's own output (kept so a failure has raw evidence)."""
    try:
        text = Path(path).read_text(errors="replace").splitlines()
    except OSError as error:
        return f"(could not read {path}: {error})"
    return "\n".join(text[-lines:])


# -- report -----------------------------------------------------------------------

def milliseconds(value):
    return "n/a" if value is None else f"{value:.2f}"


def share(value):
    return "n/a" if value is None else f"{value * 100:.1f}%"


def span_note(summary):
    """Where in the window this surface's answers landed (does it cover the whole run?)."""
    span = summary.get("answer_span_seconds")
    if not span:
        return " | answers: none"
    return f" | answers from t={span[0]:.1f}s to t={span[1]:.1f}s"


def render(result):
    public, console = result["public"], result["console"]
    fixture, machine = result["fixture"], result["machine"]
    lines = [
        "== public board load test (tests/load_public_board.py) ==",
        f"command      : {' '.join(result['command'])}",
        f"targets      : public http://127.0.0.1:{result['ports']['public']}{result['public_path']}"
        f"  |  console http://127.0.0.1:{result['ports']['console']}{result['console_path']}",
        f"origins sent : {', '.join(f'{host}:{port}' for host, port in result['origins'])}"
        "   (loopback only, re-asserted before every request)",
        f"window       : {result['window_seconds']:.1f} s served (asked for {result['seconds']:.0f} s),"
        f" {result['pollers']} public pollers @ {result['interval']:.1f} s,"
        f" {result['console_pollers']} console pollers @ {result['interval']:.1f} s,"
        f" warmup {result['warmup']:.1f} s",
        f"public       : {public['sent']} sent | 200 {public['statuses'].get('200', 0)}"
        f" | 304 {public['not_modified']} ({share(public['not_modified_share'])} of board answers)"
        f" | failed {public['failed']} ({share(public['error_rate'])})"
        + (f" | refused {public['refused_statuses']}" if public["refused_statuses"] else "")
        + (f" | {public['failure_reasons']}" if public["failure_reasons"] else "")
        + span_note(public),
        f"public ms    : p50 {milliseconds(public['p50_ms'])} | p95 {milliseconds(public['p95_ms'])}"
        f" | p99 {milliseconds(public['p99_ms'])} | max {milliseconds(public['max_ms'])}",
        f"console      : {console['sent']} sent | 200 {console['statuses'].get('200', 0)}"
        f" | failed {console['failed']} ({share(console['error_rate'])})"
        + (f" | refused {console['refused_statuses']}" if console["refused_statuses"] else "")
        + (f" | {console['failure_reasons']}" if console["failure_reasons"] else "")
        + span_note(console),
        f"console ms   : p50 {milliseconds(console['p50_ms'])} | p95 {milliseconds(console['p95_ms'])}"
        f" | p99 {milliseconds(console['p99_ms'])} | max {milliseconds(console['max_ms'])}",
        f"fixture cpu  : pid {fixture['pid']} {fixture['cpu_seconds']:.2f} s cpu over"
        f" {fixture['cpu_span_seconds']:.1f} s wall = {fixture['cpu_percent_of_core']:.2f}% of one core"
        " (both listeners in one process)",
        f"client cpu   : this script {result['client_cpu_percent_of_core']:.2f}% of one core"
        " (the load generator shares the machine)",
        f"machine      : loadavg {machine['loadavg_before']} before -> {machine['loadavg_after']} after"
        f" | {machine['cores']} cores",
    ]
    if result["burst"]:
        item = result["burst"]
        lines.append(f"burst probe  : {item['sent']} simultaneous GETs | statuses {item['statuses']}"
                     f" | p50 {milliseconds(item['p50_ms'])} ms p95 {milliseconds(item['p95_ms'])} ms"
                     f" | {item['failure_reasons'] or 'no failures'}")
    if result["fixture_death"]:
        item = result["fixture_death"]
        lines.append(f"fixture death: stopped {item['at_second']:.1f} s into the window, exit"
                     f" {item['exit_code']}"
                     + (f" (signal {item['signal']})" if item.get("signal") else "")
                     + " -- killed from outside this script")
    if result["preflight"]:
        lines.append("preflight    : " + " | ".join(result["preflight"]))
    cleanup = result["cleanup"]
    lines.append(f"cleanup      : signals {cleanup['signals'] or 'none (already gone)'}"
                 f" | exit {cleanup['exit_code']} | ports closed {cleanup['ports_closed']}"
                 f" | leftover in TMPDIR {cleanup['leftover'] or 'none'}")
    lines.append(f"verdict      : {'PASS' if result['passed'] else 'FAIL'} "
                 f"({'; '.join(result['reasons']) or 'every assertion held'})")
    if not result["passed"] and result.get("fixture_output_tail"):
        lines.append("-- fixture's own output, last lines (raw) --")
        lines.extend(f"  {line}" for line in result["fixture_output_tail"].splitlines())
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pollers", type=int, default=50, help="concurrent public pollers (default 50)")
    parser.add_argument("--console-pollers", type=int, default=50,
                        help="concurrent console pollers over the same window (default 50)")
    parser.add_argument("--interval", type=float, default=3.0, help="seconds between polls (default 3)")
    parser.add_argument("--seconds", type=float, default=120.0, help="measured window (default 120)")
    parser.add_argument("--warmup", type=float, default=5.0, help="seconds before measuring (default 5)")
    parser.add_argument("--public-prefix", default="/board", help="fixture mount (default /board)")
    parser.add_argument("--console-path", default="/api/operations")
    parser.add_argument("--max-error-rate", type=float, default=0.01)
    parser.add_argument("--p95-ms", type=float, default=250.0, help="p95 ceiling per surface (default 250)")
    parser.add_argument("--burst", type=int, default=0,
                        help="also fire N simultaneous GETs after the window (0 = off)")
    parser.add_argument("--json", type=Path, help="write the full result as JSON here")
    args = parser.parse_args()

    prefix = (args.public_prefix or "").rstrip("/")
    public_path = f"{prefix}/api/board"
    reasons, preflight = [], []

    console_port = free_port(FIRST_PORT)
    public_port = free_port(console_port + 1)
    allowed_ports = {console_port, public_port}
    public = Target("public", "127.0.0.1", public_port, allowed_ports)
    console = Target("console", "127.0.0.1", console_port, allowed_ports)

    tmp_root = Path(tempfile.mkdtemp(prefix="pool-load-"))
    process, command, log, log_path = start_fixture(console_port, public_port, prefix, tmp_root)
    result = {"command": command, "ports": {"console": console_port, "public": public_port},
              "public_path": public_path, "console_path": args.console_path,
              "origins": sorted({("127.0.0.1", console_port), ("127.0.0.1", public_port)}),
              "pollers": args.pollers, "console_pollers": args.console_pollers,
              "interval": args.interval, "warmup": args.warmup, "seconds": args.seconds,
              "preflight": preflight,
              "burst": None, "passed": False, "reasons": reasons}
    try:
        if not (wait_for_port(console_port, process) and wait_for_port(public_port, process)):
            output = read_tail(log_path) if process.poll() is not None else ""
            raise SystemExit(f"the fixture never listened on {console_port}/{public_port}; "
                             f"exit {process.poll()}\n{output}")

        # Preflight: this really is the fixture, and the public listener really is the
        # public surface -- the console's own routes are not on it.
        status, headers, body, _ms = public.request("GET", public_path)
        document = json.loads(body) if status == 200 else {}
        preflight.append(f"public {public_path} -> {status}, board={document.get('board')!r},"
                         f" revision={document.get('revision')!r}, etag={'etag' in headers}")
        if status != 200 or document.get("board") not in ("on", "off") or "etag" not in headers:
            reasons.append(f"preflight: public {public_path} answered {status} without a board/ETag")
        else:
            status, _headers, _body, _ms = public.request(
                "GET", public_path, {"If-None-Match": headers["etag"]})
            preflight.append(f"public conditional GET -> {status} (304 expected)")
            if status != 304:
                reasons.append(f"preflight: conditional GET answered {status}, not 304")
        status, _headers, _body, _ms = public.request("GET", f"{prefix}/api/operations")
        preflight.append(f"public {prefix}/api/operations -> {status} (must be 404)")
        if status != 404:
            reasons.append(f"preflight: the public listener answered {status} for the console route")
        status, _headers, body, _ms = console.request("GET", args.console_path)
        revision = json.loads(body).get("revision") if status == 200 else None
        preflight.append(f"console {args.console_path} -> {status}, revision={revision!r}")
        if status != 200 or revision is None:
            reasons.append(f"preflight: console {args.console_path} answered {status}")

        public_recorder, console_recorder = Recorder("public"), Recorder("console")
        time.sleep(args.warmup)
        stopped, death, samples = threading.Event(), {}, {}

        def window(recorder, pollers, path, target, deadline):
            workers = [threading.Thread(target=poll, name=f"{recorder.name}-{index}",
                                        args=(target, path, recorder, deadline, args.interval,
                                              args.interval * index / max(pollers, 1), stopped))
                       for index in range(pollers)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join()

        hz = os.sysconf("SC_CLK_TCK")
        fixture_before, client_before = cpu_ticks(process.pid), cpu_ticks(os.getpid())
        before, load_before = time.monotonic(), loadavg()
        deadline = time.monotonic() + args.seconds
        runners = [threading.Thread(target=window, name="public-window",
                                    args=(public_recorder, args.pollers, public_path, public, deadline)),
                   threading.Thread(target=window, name="console-window",
                                    args=(console_recorder, args.console_pollers, args.console_path,
                                          console, deadline))]
        monitor = threading.Thread(target=watch, name="fixture-monitor",
                                  args=(process, before, deadline, stopped, death, samples))
        monitor.start()
        for runner in runners:
            runner.start()
        for runner in runners:
            runner.join()
        stopped.set()
        monitor.join(timeout=5.0)
        wall = time.monotonic() - before
        fixture_after, client_after = cpu_ticks(process.pid), cpu_ticks(os.getpid())
        load_after = loadavg()

        result["window_seconds"] = wall
        result["public"] = public_recorder.summary(before)
        result["console"] = console_recorder.summary(before)
        result["fixture_death"] = death or None
        if fixture_after is not None:
            cpu_end, cpu_span = fixture_after, wall
        else:  # the fixture died: fall back to the last sample the monitor managed to take
            cpu_end, cpu_span = samples.get("ticks"), max(0.0, samples.get("at", before) - before)
        cpu_seconds = ((cpu_end - fixture_before) / hz) if None not in (fixture_before, cpu_end) \
            else -1.0
        result["fixture"] = {
            "pid": process.pid, "cpu_seconds": cpu_seconds, "cpu_span_seconds": cpu_span,
            "cpu_percent_of_core": (cpu_seconds / cpu_span * 100.0)
            if cpu_seconds >= 0 and cpu_span else -1.0}
        result["client_cpu_percent_of_core"] = (((client_after - client_before) / hz) / wall * 100.0) \
            if None not in (client_before, client_after) else -1.0
        result["machine"] = {"cores": os.cpu_count(), "loadavg_before": load_before,
                             "loadavg_after": load_after}

        if args.burst and not death:
            result["burst"] = burst(public, args.burst, public_path)

        # -- assertions ------------------------------------------------------------
        if death:
            reasons.append(f"the fixture stopped running {death['at_second']:.1f} s into the"
                           f" window (exit {death['exit_code']}"
                           + (f", signal {death['signal']}" if death["signal"] else "")
                           + "): killed from outside this script, so the run measured a"
                           " missing server, not a slow one")
        for surface in ("public", "console"):
            summary = result[surface]
            if summary["error_rate"] is None or summary["error_rate"] > args.max_error_rate:
                reasons.append(
                    f"{surface}: error rate {share(summary['error_rate'])} > "
                    f"{share(args.max_error_rate)} ({summary['failed']} failed: "
                    f"{summary['refused_statuses'] or summary['failure_reasons']})")
            if summary["p95_ms"] is None or summary["p95_ms"] > args.p95_ms:
                reasons.append(f"{surface}: p95 {milliseconds(summary['p95_ms'])} ms > "
                               f"{args.p95_ms:.0f} ms")
            if summary["sent"] == 0:
                reasons.append(f"{surface}: no requests were sent")
    finally:
        cleanup = stop_fixture(process, (console_port, public_port), tmp_root)
        result["cleanup"] = cleanup
        log.flush()
        log.close()
        result["fixture_output_tail"] = read_tail(log_path)
        if process.poll() is None:
            reasons.append("cleanup: the fixture process is still alive")
        if not all(cleanup["ports_closed"].values()):
            reasons.append(f"cleanup: a fixture port still accepts connections {cleanup['ports_closed']}")
        shutil.rmtree(tmp_root, ignore_errors=True)
        if tmp_root.exists():
            reasons.append(f"cleanup: {tmp_root} could not be removed")
        result["passed"] = not reasons
        result["reasons"] = reasons

    print(render(result))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(f"json         : {args.json}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
