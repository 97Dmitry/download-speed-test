#!/usr/bin/env python3
"""Measure download throughput using ten sequential HTTP requests."""

import argparse
from dataclasses import dataclass
from http.client import HTTPException
import math
import sys
import time
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


REQUEST_COUNT = 10
CHUNK_SIZE = 64 * 1024


@dataclass(frozen=True)
class Measurement:
    total_bytes: int
    total_seconds: float

    @property
    def average_seconds(self):
        return self.total_seconds / REQUEST_COUNT

    @property
    def mib_per_second(self):
        return self.total_bytes / self.total_seconds / 1024**2


def http_url(value):
    try:
        parsed = urlsplit(value)
        if parsed.scheme in ('http', 'https') and parsed.hostname:
            return value
    except ValueError:
        pass
    raise argparse.ArgumentTypeError('provide an absolute HTTP or HTTPS URL')


def positive_timeout(value):
    try:
        timeout = float(value)
        if math.isfinite(timeout) and timeout > 0:
            return timeout
    except ValueError:
        pass
    raise argparse.ArgumentTypeError('timeout must be a finite positive number')


def measure(url, timeout=30.0):
    total_bytes = 0
    total_seconds = 0.0
    for _ in range(REQUEST_COUNT):
        request = Request(url, headers={
            'Accept-Encoding': 'identity',
            'Cache-Control': 'no-cache',
            'User-Agent': 'download-speed-test/1.0',
        })
        started = time.perf_counter()
        with urlopen(request, timeout=timeout) as response:
            downloaded = 0
            while chunk := response.read(CHUNK_SIZE):
                downloaded += len(chunk)
            # A bounded read may return EOF without detecting a short body.
            expected = response.headers.get('Content-Length')
            if expected is not None and downloaded != int(expected):
                raise OSError('incomplete response body (Content-Length mismatch)')
        total_seconds += time.perf_counter() - started
        total_bytes += downloaded
    if total_seconds <= 0:
        raise OSError('elapsed time is too small to measure')
    return Measurement(total_bytes, total_seconds)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url', type=http_url, help='URL of the file to download')
    parser.add_argument('--timeout', type=positive_timeout, default=30.0,
                        help='socket operation timeout in seconds (default: 30)')
    args = parser.parse_args()
    try:
        result = measure(args.url, args.timeout)
    except (URLError, HTTPException, OSError, ValueError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('Interrupted.', file=sys.stderr)
        return 130
    print(f'Requests completed: {REQUEST_COUNT}')
    print(f'Average request time: {result.average_seconds:.3f} s')
    print(f'Total downloaded: {result.total_bytes} bytes '
          f'({result.total_bytes / 1024**2:.3f} MiB)')
    print(f'Download speed: {result.mib_per_second:.3f} MiB/s')
    return 0


if __name__ == '__main__':
    sys.exit(main())
