"""A pretend network printer for testing PrintEasy without real hardware.

Speaks enough IPP (port 631) to answer Get-Printer-Attributes, accepts raw print jobs
on port 9100 (saved to a folder), and can announce itself with Bonjour/mDNS.

    python tests/fake_printer.py --ip 192.168.1.50 --out /tmp/jobs
"""
from __future__ import annotations

import argparse
import os
import socket
import socketserver
import struct
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from printeasy.core.ipp import _attr, parse_response  # noqa: E402

MODEL = "Acme InkJet 5000"


def ipp_response(request: bytes, ip: str) -> bytes:
    rid = struct.unpack(">I", request[4:8])[0]
    body = struct.pack(">BBHI", 2, 0, 0x0000, rid)
    body += b"\x01" + _attr(0x47, "attributes-charset", b"utf-8") + _attr(0x48, "attributes-natural-language", b"en")
    body += b"\x04"
    body += _attr(0x41, "printer-make-and-model", MODEL.encode())
    body += _attr(0x42, "printer-name", b"Acme-InkJet")
    body += _attr(0x41, "printer-info", b"Acme InkJet (Kitchen)")
    body += _attr(0x41, "printer-location", b"Kitchen")
    body += _attr(0x23, "printer-state", struct.pack(">i", 3))
    body += _attr(0x45, "printer-uri-supported", f"ipp://{ip}:631/ipp/print".encode())
    body += _attr(0x22, "color-supported", b"\x01")
    body += _attr(0x49, "document-format-supported", b"application/pdf")
    body += _attr(0x49, "", b"image/pwg-raster")
    body += _attr(0x42, "marker-names", b"Black")
    body += _attr(0x42, "", b"Cyan")
    body += _attr(0x21, "marker-levels", struct.pack(">i", 64))
    body += _attr(0x21, "", struct.pack(">i", 8))
    body += b"\x03"
    return body


def serve(ip: str, out_dir: str, mdns: bool = True):
    os.makedirs(out_dir, exist_ok=True)

    class IPPHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            data = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            parse_response(data)                      # make sure the request is well formed
            reply = ipp_response(data, ip)
            self.send_response(200)
            self.send_header("Content-Type", "application/ipp")
            self.send_header("Content-Length", str(len(reply)))
            self.end_headers()
            self.wfile.write(reply)

        def do_GET(self):
            page = b"<html><head><title>Acme InkJet 5000 - Settings</title></head><body>ok</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)

        def log_message(self, *a):
            pass

    class RawHandler(socketserver.BaseRequestHandler):
        def handle(self):
            chunks = []
            while True:
                b = self.request.recv(65536)
                if not b:
                    break
                chunks.append(b)
            path = os.path.join(out_dir, f"job_{int(time.time() * 1000)}.bin")
            with open(path, "wb") as fh:
                fh.write(b"".join(chunks))

    class RawServer(socketserver.ThreadingTCPServer):
        allow_reuse_address = True

    ThreadingHTTPServer.allow_reuse_address = True
    servers = [ThreadingHTTPServer((ip, 631), IPPHandler), ThreadingHTTPServer((ip, 80), IPPHandler),
               RawServer((ip, 9100), RawHandler)]
    for s in servers:
        threading.Thread(target=s.serve_forever, daemon=True).start()

    zc = None
    if mdns:
        from zeroconf import ServiceInfo, Zeroconf
        zc = Zeroconf(interfaces=[ip])
        info = ServiceInfo("_ipp._tcp.local.", "Acme InkJet Kitchen._ipp._tcp.local.",
                           addresses=[socket.inet_aton(ip)], port=631,
                           properties={"ty": MODEL, "rp": "ipp/print", "note": "Kitchen",
                                       "adminurl": f"http://{ip}/"}, server="acme-inkjet.local.")
        zc.register_service(info)
    return servers, zc


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", required=True)
    ap.add_argument("--out", default="/tmp/printeasy_jobs")
    ap.add_argument("--no-mdns", action="store_true")
    a = ap.parse_args()
    serve(a.ip, a.out, not a.no_mdns)
    print(f"Fake printer running on {a.ip} (IPP 631, raw 9100). Jobs -> {a.out}", flush=True)
    while True:
        time.sleep(3600)
