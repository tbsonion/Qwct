"""QWCT 5.3: discover /file/<ID> image references only in PUBLIC pages.

Targets TWO public, explicitly Gerchik-attributed trade-review articles.
No credentials, no downloads of embedded images, no brute-force enumeration.
"""
from urllib.request import Request, urlopen
from urllib.parse import urljoin
from html import unescape
import json
import re

PAGES = (
"https://gerchik.co/ru/analytics/tehnicheskiy-analiz/razbor-sdelok-s-aleksandrom-gerchikom-08-07-2026",
"https://gerchik.co/ru/analytics/tehnicheskiy-analiz/razbor-sdelok-s-aleksandrom-gerchikom-19-08-2026",
)

def main():
    for page in PAGES:
        req=Request(page, headers={"User-Agent":"QWCT-PublicSourceResearch/1.0"})
        try:
            with urlopen(req,timeout=15) as r:
                if r.status != 200:
                    print("QWCT GERCHIK REVIEW_PAGE",page,"STATUS",r.status)
                    continue
                body=r.read(2_000_000).decode("utf-8","replace")
        except Exception as exc:
            print("QWCT GERCHIK REVIEW_ERROR",page,type(exc).__name__)
            continue
        # Public HTML may contain links as src, href, data-src and CSS urls.
        # Reporting ID and context only; no attempt to link images to author
        # trading timestamps without manually inspecting the source chart.
        found={}
        for m in re.finditer(r"(?:https?://(?:www\\.)?gerchik\\.co)?/file/(\\d{2,7})",body):
            file_id=int(m.group(1))
            if file_id not in found:
                surrounding=unescape(re.sub(r"<[^>]+>"," ",body[max(0,m.start()-180):m.end()+140]))
                found[file_id]=" ".join(surrounding.split())[:160]
        print("QWCT GERCHIK REVIEW_PAGE",json.dumps(
            dict(url=page,found_file_ids=len(found),
                 image_id_contexts=[{"id":k,"near_html":v}
                                    for k,v in list(found.items())[:50]]),
            ensure_ascii=False),flush=True)

if __name__=="__main__":
    main()
