#!/usr/bin/env python3
"""
fetch_ssq.py - 双色球历史数据抓取脚本

策略：调 cwl.gov.cn 官方 GET 接口。
失败时保留旧文件不动，进程返回 0（不破更新）。

输出：data/history.json
"""
import json, re, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

CST = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "history.json"
SOURCE_URL = "https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice?name=ssq&issueCount=60"


def fetch_cwl(limit=60):
    url = f"https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice?name=ssq&issueCount={limit}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.cwl.gov.cn/ygkj/wqkjgg/ssq/",
    }
    req = Request(url, headers=headers, method="GET")
    resp = urlopen(req, timeout=20)
    raw = resp.read().decode("utf-8", errors="replace")
    obj = json.loads(raw)
    if obj.get("state") != 0:
        raise RuntimeError(f"cwl: state={obj.get('state')}, msg={obj.get('message')}")
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
        # date 形如 "2026-07-09(四)"
        date_raw = (row.get("date") or "").strip()
        date_str = date_raw[:10] if len(date_raw) >= 10 else ""
        recs.append({
            "issue": issue,
            "reds": sorted(reds),
            "blue": blue,
            "date": date_str,
        })
    if not recs:
        raise RuntimeError("cwl: empty result")
    recs.sort(key=lambda r: r["issue"], reverse=True)
    return recs[:limit]


def merge_with_existing(new_recs):
    if not OUT.exists(): return new_recs
    try: old = json.loads(OUT.read_text(encoding="utf-8"))
    except Exception: return new_recs
    by_issue = {r["issue"]: r for r in old.get("data", [])}
    for r in new_recs: by_issue[r["issue"]] = r
    merged = sorted(by_issue.values(), key=lambda r: r["issue"], reverse=True)
    return merged[:90]


def main():
    now = datetime.now(CST).isoformat(timespec="seconds")
    print(f"[{now}] fetch_ssq start", flush=True)
    try:
        new = fetch_cwl(limit=60)
    except Exception as e:
        print(f"FAIL primary source: {e}", file=sys.stderr, flush=True)
        if OUT.exists():
            print("Keep existing history.json", flush=True)
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
