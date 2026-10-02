"""B-8: the console's long-lived streams must not spend the request budget.

The console holds one Server-Sent Events stream per open page
(annotator/clock-sync.js) and that stream lives until its tab closes: its 15 s
heartbeat is also what keeps the handler's socket timeout from ever firing, so
it never gives its slot back on its own. Under a single ceiling spent on
requests, a night of open consoles answered the next ordinary API call with
503 - and the operator's own listener is the one thing that must stay
answering. These tests hold streams past the request ceiling, prove an ordinary
call still gets through, and prove the stream ceiling itself still refuses the
connection over it instead of queueing.

Every server here is the production class on an ephemeral loopback port with a
temporary root; the operator's listener on :8130 is never touched.
"""
import http.client
import json
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from annotator import shot_clock
from annotator.unified_server import Backend, BoundedHTTPServer, make_handler

#: More streams at once than the request ceiling (64): the shape of a night.
CROWD = 80


class ConnectionBudgetTests(unittest.TestCase):
    def serve(self, handler_timeout=None, **attrs):
        """A real loopback server on an ephemeral port with the production handler.

        ``attrs`` (a smaller ``max_streams``, say) are class attributes read at
        construction, which is the only time production reads them either.
        """
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.backend = Backend(Path(temp.name))
        handler = make_handler(self.backend)
        handler.log_message = lambda *args: None
        if handler_timeout is not None:
            handler.timeout = handler_timeout
        server_class = type('FixtureServer', (BoundedHTTPServer,), dict(attrs))
        server = server_class(('127.0.0.1', 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.addCleanup(self.backend.close)
        self.port = server.server_address[1]
        return server

    def connect(self, timeout=10):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=timeout)
        self.addCleanup(connection.close)
        return connection

    @staticmethod
    def leave(connection, response):
        """A tab closing: the response's file object holds the socket, so it goes first."""
        response.close()
        connection.close()

    def stream(self):
        """Open one clock stream: (connection, response), headers already read."""
        connection = self.connect()
        connection.request('GET', '/api/clock/stream')
        response = connection.getresponse()
        self.addCleanup(self.leave, connection, response)
        return connection, response

    @staticmethod
    def first_event(response):
        """The name of the stream's first event (serve_events writes state first)."""
        while True:
            line = response.readline().decode()
            if line == '':
                return None
            line = line.rstrip('\n')
            if line.startswith('event: '):
                return line[7:]

    def api(self, path):
        """One ordinary call on its own connection: (status, body, seconds)."""
        connection = self.connect()
        started = time.monotonic()
        connection.request('GET', path)
        response = connection.getresponse()
        raw = response.read()
        elapsed = time.monotonic() - started
        connection.close()
        try:
            body = json.loads(raw)
        except ValueError:                  # the listener's own refusal is text/plain "busy"
            body = raw
        return response.status, body, elapsed

    def pools(self, server, expected, timeout=5.0):
        """Wait until the two budgets hold exactly `expected`, then return them."""
        deadline = time.monotonic() + timeout
        state = server.pool_state()
        while state != expected and time.monotonic() < deadline:
            time.sleep(0.02)
            state = server.pool_state()
        return state

    def test_streams_past_the_request_ceiling_leave_api_calls_room(self):
        # A short heartbeat only makes a stream notice a closed tab sooner;
        # production's 15 s is precisely what keeps its socket timeout asleep.
        with patch.object(shot_clock, 'HEARTBEAT_S', 0.25):
            server = self.serve()
            self.assertGreater(CROWD, BoundedHTTPServer.max_handlers,
                               'the crowd must exceed the request ceiling to mean anything')
            opened = [self.stream() for _ in range(CROWD)]
            refused = [response.status for _, response in opened if response.status != 200]
            self.assertEqual(refused, [], 'every stream is admitted: they are not funded by the request ceiling')
            self.assertEqual([self.first_event(response) for _, response in opened], ['clock'] * CROWD)
            # The accounting is the proof: 80 streams, no request slot touched.
            self.assertEqual(self.pools(server, {'requests': 0, 'streams': CROWD}),
                             {'requests': 0, 'streams': CROWD})
            status, body, elapsed = self.api('/api/operations')
            self.assertEqual(status, 200, 'an ordinary call is not what pays for a night of streams')
            self.assertEqual(body['revision'], 0)
            self.assertLess(elapsed, 2.0, f'answered while {CROWD} streams were open, in {elapsed:.3f}s')

            for connection, response in opened:
                self.leave(connection, response)
            self.assertEqual(self.pools(server, {'requests': 0, 'streams': 0}),
                             {'requests': 0, 'streams': 0}, 'every closed tab gave its stream slot back')
            status, _, _ = self.api('/api/operations')
            self.assertEqual(status, 200)

    def test_streams_and_requests_hold_their_own_ceilings_at_once(self):
        # max_handlers=4 is a small stage for the incident: four streams used to
        # spend all four slots, so the call below was a 503, not a 200.
        with patch.object(shot_clock, 'HEARTBEAT_S', 0.25):
            server = self.serve(max_handlers=4, handler_timeout=10)
            streams = [self.stream() for _ in range(4)]
            self.assertEqual([response.status for _, response in streams], [200] * 4)

            status, _, elapsed = self.api('/api/operations')
            self.assertEqual(status, 200, 'four open streams must not answer for the request budget')
            self.assertLess(elapsed, 2.0)
            self.assertEqual(self.pools(server, {'requests': 0, 'streams': 4}), {'requests': 0, 'streams': 4})

            idle = []                                # four idle clients hold the four request slots
            for _ in range(4):
                sock = socket.create_connection(('127.0.0.1', self.port), timeout=5)
                idle.append(sock)
                self.addCleanup(sock.close)
            self.assertEqual(self.pools(server, {'requests': 4, 'streams': 4}), {'requests': 4, 'streams': 4},
                             'four requests and four streams fit together, which is the whole fix')

            over = socket.create_connection(('127.0.0.1', self.port), timeout=5)
            self.addCleanup(over.close)
            over.settimeout(5)
            self.assertTrue(over.recv(64).startswith(b'HTTP/1.0 503'),
                            'the request ceiling still refuses the connection over it, with no queue')
            self.assertEqual(self.pools(server, {'requests': 4, 'streams': 4}), {'requests': 4, 'streams': 4},
                             'a refusal holds nothing')

    def test_a_full_stream_budget_is_refused_and_then_gives_the_slot_back(self):
        with patch.object(shot_clock, 'HEARTBEAT_S', 0.25):
            server = self.serve(max_streams=4)
            held = [self.stream() for _ in range(4)]
            self.assertEqual([response.status for _, response in held], [200] * 4)

            connection, response = self.stream()     # one over the stream ceiling
            self.assertEqual(response.status, 503)
            self.assertEqual(response.getheader('Retry-After'), '5')
            self.assertEqual(json.loads(response.read()), {'error': 'unavailable'})
            self.assertEqual(self.pools(server, {'requests': 0, 'streams': 4}),
                             {'requests': 0, 'streams': 4}, 'a refusal holds nothing')
            status, _, _ = self.api('/api/operations')
            self.assertEqual(status, 200, 'and it did not cost the request budget either')

            self.leave(*held[0])                     # the tab closes; the slot is noticed on the next write
            self.assertEqual(self.pools(server, {'requests': 0, 'streams': 3}),
                             {'requests': 0, 'streams': 3}, 'the closed stream gave its slot back')
            _, response = self.stream()
            self.assertEqual(response.status, 200, 'and the next stream is admitted')
            self.assertEqual(self.pools(server, {'requests': 0, 'streams': 4}), {'requests': 0, 'streams': 4})


if __name__ == '__main__':
    unittest.main()
