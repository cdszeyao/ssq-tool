#!/usr/bin/env python3
"""
fetch_ssq.py - 双色球历史数据抓取脚本
500.com 主源，cwl.gov.cn 备选，失败保留旧文件。
"""
import json, re, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

CST = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "history.json"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def fetch_500(limit=90):
    url = "https://datachart.500.com/ssq/history/history.shtml"
    req = Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*", "Referer": "https://datachart.500.com/"}, method="GET")
    resp = urlopen(req, timeout=25)
    html = resp.read().decode("gbk", errors="replace")
    html = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    row_re = re.compile(r'<tr class="t_tr1">(.*?)</tr>', re.S)
    recs = []
    for m in row_re.finditer(html):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", m.group(1), re.S)
        cells = [re.sub(r"<[^>]+>", "", c).replace("&nbsp;", "").strip() for c in cells]
        if len(cells) < 16: continue
        try:
            issue = int(cells[0])
            reds = [int(cells[i]) for i in range(1, 7)]
            blue = int(cells[7])
        except (ValueError, TypeError): continue
        if len(reds) != 6 or not (1 <= blue <= 16): continue
        date_str = cells[15] if re.match(r"\d{4}-\d{2}-\d{2}", cells[15]) else ""
        # 5位 issue 升 6 位 (26079 -> 2026079)
        if 0 < issue < 100000:
            issue = 2000000 + issue
        recs.append({"issue": issue, "reds": sorted(reds), "blue": blue, "date": date_str})
    if not recs: raise RuntimeError("500.com: no rows parsed")
    recs.sort(key=lambda r: r["issue"], reverse=True)
    return recs[:limit]


def fetch_cwl(limit=60):
    url = f"https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice?name=ssq&issueCount={limit}"
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/json, text/plain, */*", "Referer": "https://www.cwl.gov.cn/ygkj/wqkjgg/ssq/"}, method="GET")
    resp = urlopen(req, timeout=20)
    raw = resp.read().decode("utf-8", errors="replace")
    obj = json.loads(raw)
    if obj.get("state") != 0:
        raise RuntimeError(f"cwl: state={obj.get('state')}")
    rows = obj.get("result") or []
    recs = []
    for row in rows:
        if row.get("name") != "双色球":
            continue
        code = (row.get("code") or "").strip()
        reds_str = (row.get("red") or "").strip()
        blue_str = (row.get("blue") or "").strip()
        if not code or not reds_str or not blue_str:
            continue
        try:
            reds = [int(x) for x in reds_str.split(",")]
            blue = int(blue_str)
            issue = int(code)
        except (ValueError, TypeError):
            continue
        if len(reds) != 6 or not (1 <= blue <= 16):
            continue
        date_raw = (row.get("date") or "").strip()
        date_str = date_raw[:10] if len(date_raw) >= 10 else ""
        if 0 < issue < 100000:
            issue = 2000000 + issue
        recs.append({"issue": issue, "reds": sorted(reds), "blue": blue, "date": date_str})
    if not recs:
        raise RuntimeError("cwl: empty result")
    recs.sort(key=lambda r: r["issue"], reverse=True)
    return recs[:limit]


def merge_with_existing(new_recs):
    if not OUT.exists():
        return new_recs
    try:
        old = json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        return new_recs
    by_issue = {r["issue"]: r for r in old.get("data", [])}
    for r in new_recs:
        by_issue[r["issue"]] = r
    merged = sorted(by_issue.values(), key=lambda r: r["issue"], reverse=True)
    return merged[:90]


def main():
    now = datetime.now(CST).isoformat(timespec="seconds")
    print(f"[{now}] fetch_ssq start", flush=True)
    new = None
    for src, fn in (("500.com", fetch_500), ("cwl.gov.cn", fetch_cwl)):
        try:
            new = fn(limit=60)
            print(f"OK fetched from {src}: latest issue {new[0]['issue']}", flush=True)
            break
        except Exception as e: print(f"FAIL {src}: {e}", file=sys.stderr, flush=True)
    if new is None:
        if OUT.exists():
            print("All sources failed, keep existing history.json", flush=True)
            return 0
        sys.exit(1)

    merged = merge_with_existing(new)
    payload = {"updated": now, "count": len(merged), "data": merged}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK wrote {len(merged)} records, latest issue {merged[0]['issue']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
