import subprocess
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import speed_test


class DownloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = []
        cls.payload = b'x' * 150_000

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                cls.paths.append(self.path)
                if self.path == '/error':
                    self.send_error(503)
                    return
                self.send_response(200)
                self.send_header('Content-Length', str(len(cls.payload)))
                self.end_headers()
                try:
                    self.wfile.write(cls.payload[:75_000])
                    self.wfile.flush()
                    time.sleep(0.01)
                    if self.path != '/truncated':
                        self.wfile.write(cls.payload[75_000:])
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *args):
                pass

        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(Path(__file__).with_name('speed_test.py')), *args],
            capture_output=True, text=True, timeout=10,
        )

    def test_reads_ten_complete_responses_and_calculates_speed(self):
        self.paths.clear()
        # One second per request, independent of machine/network speed.
        ticks = [value for i in range(10) for value in (i * 2, i * 2 + 1)]
        with patch('speed_test.time.perf_counter', side_effect=ticks):
            result = speed_test.measure(self.url)
        self.assertEqual(self.paths, ['/'] * 10)
        self.assertEqual(result.total_bytes, 1_500_000)
        self.assertEqual(result.average_seconds, 1)
        self.assertAlmostEqual(result.mib_per_second, 1_500_000 / 10 / 1024**2)

    def test_cli_prints_results(self):
        result = self.run_cli(self.url)
        self.assertEqual(result.returncode, 0, result.stderr)
        for expected in ('10', '1500000 bytes', 'Average request time:', 'MiB/s'):
            self.assertIn(expected, result.stdout)

    def test_http_error_stops_without_success_summary(self):
        self.paths.clear()
        result = self.run_cli(self.url + '/error')
        self.assertEqual(result.returncode, 1)
        self.assertIn('503', result.stderr)
        self.assertNotIn('Download speed:', result.stdout)
        self.assertEqual(self.paths, ['/error'])

    def test_truncated_body_fails(self):
        result = self.run_cli(self.url + '/truncated')
        self.assertEqual(result.returncode, 1)
        self.assertNotIn('Download speed:', result.stdout)

    def test_rejects_invalid_arguments(self):
        for args in ((), ('file:///etc/hosts',), ('http://',),
                     (self.url, '--timeout', '0'), (self.url, '--timeout', 'nan')):
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 2)


if __name__ == '__main__':
    unittest.main()
