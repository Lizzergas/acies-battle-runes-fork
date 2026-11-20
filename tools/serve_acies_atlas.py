#!/usr/bin/env python3
"""Serve the local Acies Atlas with seekable audio and video playback."""

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import re


class AtlasHandler(SimpleHTTPRequestHandler):
    def send_head(self):
        self.media_bytes_remaining = None
        path = Path(self.translate_path(self.path))
        self.media_type = {".ogg": "audio/ogg", ".mp4": "video/mp4"}.get(path.suffix.lower()) if path.is_file() else None
        match = re.fullmatch(r"bytes=([0-9]{0,20})-([0-9]{0,20})", self.headers.get("Range", ""))
        if not self.media_type or not match or not any(match.groups()):
            return super().send_head()

        stream = path.open("rb")
        stat = os.fstat(stream.fileno())
        first, last = match.groups()
        start = int(first) if first else max(0, stat.st_size - int(last))
        end = min(int(last), stat.st_size - 1) if first and last else stat.st_size - 1
        if start > end:
            stream.close()
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{stat.st_size}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None

        stream.seek(start)
        self.media_bytes_remaining = end - start + 1
        self.send_response(206)
        self.send_header("Content-Type", self.media_type)
        self.send_header("Content-Range", f"bytes {start}-{end}/{stat.st_size}")
        self.send_header("Content-Length", str(self.media_bytes_remaining))
        self.send_header("Last-Modified", self.date_time_string(stat.st_mtime))
        self.end_headers()
        return stream

    def end_headers(self):
        if getattr(self, "media_type", None):
            self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def copyfile(self, source, outputfile):
        if self.media_bytes_remaining is None:
            return super().copyfile(source, outputfile)
        while self.media_bytes_remaining:
            chunk = source.read(min(self.media_bytes_remaining, 64 * 1024))
            if not chunk:
                break
            outputfile.write(chunk)
            self.media_bytes_remaining -= len(chunk)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8876)
    parser.add_argument("--directory", type=Path, default=Path(__file__).resolve().parent.parent / "work/acies-atlas")
    args = parser.parse_args()
    with ThreadingHTTPServer((args.bind, args.port), partial(AtlasHandler, directory=args.directory)) as server:
        print(f"Acies Atlas at http://{args.bind}:{server.server_port}/", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
