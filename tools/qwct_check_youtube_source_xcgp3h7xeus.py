"""Read-only provenance check of ONE user-supplied YouTube Live video.

No sign-in/cookies, no video download, no auto-chapter invention.
Metadata and presence/absence of publicly accessible captions only.
"""
import json
import re
from urllib.request import Request, urlopen
from urllib.parse import quote
from urllib.error import HTTPError, URLError

VIDEO_ID = "xcgp3h7xeus"
URL = "https://www.youtube.com/watch?v=" + VIDEO_ID
USER_AGENT = "Mozilla/5.0 (compatible; QWCT-Video-Provenance/1.0)"


def read(url, byte_cap=800_000):
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=18) as response:
        return (response.status, response.geturl(),
                response.read(byte_cap).decode("utf-8", "replace"))


def check_oembed():
    url = "https://www.youtube.com/oembed?format=json&url=" + quote(URL, safe="")
    try:
        status, endpoint, body = read(url, 80_000)
        parsed = json.loads(body)
        return {"http_status": status, "title": parsed.get("title"),
                "author_name": parsed.get("author_name"),
                "author_url": parsed.get("author_url"),
                "type": parsed.get("type")}
    except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
        return {"error": type(exc).__name__,
                "http_status": getattr(exc, "code", None)}


def check_transcript_mirror():
    uri = "https://prepublish.ai/youtube-transcript/" + VIDEO_ID
    try:
        status, endpoint, body = read(uri)
        title = re.search(r"<title>([^<]{1,300})</title>", body, re.I)
        return {"http_status": status, "page_title": title.group(1) if title else None,
                "has_timecode_sections": bool(re.search(r"\bTranscript\b", body, re.I)),
                "bytes_previewed": len(body)}
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        return {"error": type(exc).__name__,
                "http_status": getattr(exc, "code", None)}


if __name__ == "__main__":
    print("QWCT 5.5 USER_VIDEO_ID", VIDEO_ID, flush=True)
    print("QWCT 5.5 YOUTUBE_OEMBED",
          json.dumps(check_oembed(), ensure_ascii=False), flush=True)
    print("QWCT 5.5 PUBLIC_CAPTION_MIRROR",
          json.dumps(check_transcript_mirror(), ensure_ascii=False), flush=True)
    print("QWCT 5.5 METADATA_ONLY NOT_VIEWED_NOT_TRANSCRIBED NO_ORDERS", flush=True)
