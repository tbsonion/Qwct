"""QWCT source discovery: tiny PUBLIC-only Gerchik file-ID probe.

Checks 20 adjacent user-provided IDs. One request per ID, one-second
delay, no authentication, no crawling linked resources, no saved files.
No private, account-gated or HTTP 403/429 sources are pursued.
"""
from __future__ import annotations
from time import sleep
from urllib.request import Request, urlopen
from urllib.parse import unquote
from urllib.error import HTTPError, URLError
import json
import sys

URL = "https://gerchik.co/file/{}"
IDS = tuple(range(5537, 5517, -1))
TIMEOUT_S = 12


def inspect(file_id):
    u = URL.format(file_id)
    request = Request(
        u,
        headers={"User-Agent": "QWCT-PublicSourceResearch/1.0 (read-only)"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=TIMEOUT_S) as response:
            status = response.status
            mime = response.headers.get("Content-Type", "unknown").split(";")[0]
            disp = response.headers.get("Content-Disposition", "")
            length = response.headers.get("Content-Length", "")
            # Read up to 16 bytes only to distinguish HTML vs PDF vs ZIP.
            signature = response.read(16)
            kind = ("PDF" if signature.startswith(b"%PDF-") else
                    "ZIP" if signature.startswith(b"PK\\x03\\x04") else
                    "HTML" if b"<" in signature[:2] else
                    "UNKNOWN")
            result = dict(id=file_id, status=status,
                          final_url=response.geturl(),
                          mime=mime, kind=kind,
                          content_length=length,
                          filename_header=unquote(disp[:120]))
    except HTTPError as exc:
        result = dict(id=file_id, status=exc.code,
                      error=f"HTTP_{exc.code}", blocked=exc.code in (401,403,429))
    except (URLError,TimeoutError,OSError) as exc:
        result = dict(id=file_id,status="CONNECTION_FAILED",
                      error=type(exc).__name__+" "+str(exc)[:90])
    print("QWCT GERCHIK FILE",json.dumps(result,ensure_ascii=False),flush=True)
    return result


def main():
    for index,file_id in enumerate(IDS):
        if index:
            sleep(1)
        result=inspect(file_id)
        if result.get("blocked"):
            print("QWCT GERCHIK STOP AUTH_OR_RATE_LIMIT NO_BYPASS",flush=True)
            break


if __name__=="__main__":
    main()
