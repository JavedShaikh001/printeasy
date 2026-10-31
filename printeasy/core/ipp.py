"""A tiny IPP client: asks a printer for its name, model and status.

IPP (Internet Printing Protocol) is spoken by nearly every network printer made in
the last 15 years, which is what makes a "universal" connector possible.
"""
from __future__ import annotations

import http.client
import random
import re
import ssl
import struct

GET_PRINTER_ATTRIBUTES = 0x000B
PRINT_JOB = 0x0002

WANTED = [
    "printer-make-and-model", "printer-name", "printer-info", "printer-location",
    "printer-state", "printer-state-reasons", "printer-uri-supported",
    "printer-more-info", "color-supported", "document-format-supported",
    "marker-names", "marker-levels", "marker-colors",
]

# Common IPP paths, tried in order
PATHS = ["/ipp/print", "/ipp", "/ipp/printer", "/printer", "/"]

STATE = {3: "Ready", 4: "Busy printing", 5: "Stopped / needs attention"}


def _attr(tag: int, name: str, value: bytes) -> bytes:
    nb = name.encode()
    return struct.pack(">BH", tag, len(nb)) + nb + struct.pack(">H", len(value)) + value


def build_request(op: int, printer_uri: str, extra: bytes = b"", requested: list[str] | None = None,
                  request_id: int | None = None) -> bytes:
    rid = request_id if request_id is not None else random.randint(1, 2**31 - 1)
    body = struct.pack(">BBHI", 2, 0, op, rid)
    body += b"\x01"                                            # operation-attributes
    body += _attr(0x47, "attributes-charset", b"utf-8")
    body += _attr(0x48, "attributes-natural-language", b"en")
    body += _attr(0x45, "printer-uri", printer_uri.encode())
    if requested:
        body += _attr(0x44, "requested-attributes", requested[0].encode())
        for kw in requested[1:]:
            body += _attr(0x44, "", kw.encode())               # additional value
    body += extra
    body += b"\x03"                                            # end-of-attributes
    return body


def parse_response(data: bytes) -> tuple[int, dict[str, list]]:
    """Return (status_code, {attribute: [values]}). Unknown value types are kept as bytes."""
    if len(data) < 8:
        raise ValueError("Response too short to be IPP")
    status = struct.unpack(">H", data[2:4])[0]
    attrs: dict[str, list] = {}
    pos, last = 8, None
    n = len(data)
    while pos < n:
        tag = data[pos]
        pos += 1
        if tag == 0x03:                      # end-of-attributes
            break
        if tag < 0x10:                       # group delimiter
            continue
        if pos + 2 > n:
            break
        name_len = struct.unpack(">H", data[pos:pos + 2])[0]
        pos += 2
        name = data[pos:pos + name_len].decode("utf-8", "replace")
        pos += name_len
        val_len = struct.unpack(">H", data[pos:pos + 2])[0]
        pos += 2
        raw = data[pos:pos + val_len]
        pos += val_len
        value = _decode(tag, raw)
        if name:
            last = name
            attrs.setdefault(name, []).append(value)
        elif last is not None and tag not in (0x34, 0x37, 0x4A):
            attrs[last].append(value)
    return status, attrs


def _decode(tag: int, raw: bytes):
    if tag in (0x21, 0x23) and len(raw) == 4:          # integer, enum
        return struct.unpack(">i", raw)[0]
    if tag == 0x22 and len(raw) == 1:                  # boolean
        return raw != b"\x00"
    if tag in (0x35, 0x36) and len(raw) >= 4:          # text/name with language
        ll = struct.unpack(">H", raw[:2])[0]
        tl = struct.unpack(">H", raw[2 + ll:4 + ll])[0]
        return raw[4 + ll:4 + ll + tl].decode("utf-8", "replace")
    if 0x41 <= tag <= 0x49:                            # text, name, keyword, uri, ...
        return raw.decode("utf-8", "replace")
    return raw


def _post(host: str, port: int, path: str, body: bytes, timeout: float, use_tls: bool) -> bytes | None:
    try:
        if use_tls:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE        # printers use self-signed certificates
            conn = http.client.HTTPSConnection(host, port, timeout=timeout, context=ctx)
        else:
            conn = http.client.HTTPConnection(host, port, timeout=timeout)
        conn.request("POST", path, body=body, headers={"Content-Type": "application/ipp"})
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        if resp.status == 200 and data[:1] in (b"\x01", b"\x02"):
            return data
    except (OSError, http.client.HTTPException, ssl.SSLError):
        return None
    return None


def query(host: str, port: int = 631, path_hint: str | None = None, timeout: float = 3.0) -> dict | None:
    """Ask a printer about itself. Returns a simple dict or None if it isn't an IPP printer."""
    paths = ([path_hint] if path_hint else []) + [p for p in PATHS if p != path_hint]
    for use_tls in (False, True):
        for path in paths:
            uri = f"ipp://{host}:{port}{path}"
            data = _post(host, port, path, build_request(GET_PRINTER_ATTRIBUTES, uri, requested=WANTED),
                         timeout, use_tls)
            if not data:
                continue
            try:
                status, attrs = parse_response(data)
            except (ValueError, struct.error):
                continue
            if status >= 0x0400 and status != 0x0406:      # client error, except "not found"
                continue
            if not attrs.get("printer-make-and-model") and not attrs.get("printer-name"):
                continue
            return summarise(attrs, host, port, path, use_tls)
    return None


def summarise(attrs: dict, host: str, port: int, path: str, use_tls: bool) -> dict:
    def first(key, default=""):
        v = attrs.get(key)
        return v[0] if v and not isinstance(v[0], bytes) else default

    levels = []
    names = attrs.get("marker-names", [])
    vals = attrs.get("marker-levels", [])
    for nm, lv in zip(names, vals):
        if isinstance(lv, int) and lv >= 0:
            levels.append((str(nm), lv))

    scheme = "ipps" if use_tls else "ipp"
    return {
        "model": first("printer-make-and-model"),
        "name": first("printer-info") or first("printer-name"),
        "location": first("printer-location"),
        "state": STATE.get(first("printer-state", 0), "Unknown"),
        "color": bool(first("color-supported", False)),
        "uri": f"{scheme}://{host}:{port}{path}",
        "web_page": first("printer-more-info") or f"http://{host}/",
        "ink": levels,
        "driverless": any("pwg-raster" in str(f) or "urf" in str(f) or "pdf" in str(f)
                          for f in attrs.get("document-format-supported", [])),
    }


def http_title(host: str, timeout: float = 2.0) -> str:
    """Read the title of a device's built-in web page (helps name printers that don't speak IPP)."""
    for port in (80, 443):
        try:
            if port == 443:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                conn = http.client.HTTPSConnection(host, port, timeout=timeout, context=ctx)
            else:
                conn = http.client.HTTPConnection(host, port, timeout=timeout)
            conn.request("GET", "/")
            body = conn.getresponse().read(65536).decode("utf-8", "replace")
            conn.close()
            m = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
            if m:
                return re.sub(r"\s+", " ", m.group(1)).strip()[:80]
        except (OSError, http.client.HTTPException, ssl.SSLError):
            continue
    return ""
