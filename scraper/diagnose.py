"""
임시 진단 스크립트: 발행내역 JSON API 응답 구조를 로그로 출력한다.
"""
import json, urllib.request

API = ("https://www.dhlottery.co.kr/st/selectPblcnDsctn.do"
       "?gdsType=&gdsPrice=&gdsStatus=&pageNum=1&recordCountPerPage=100")

req = urllib.request.Request(API, headers={
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.dhlottery.co.kr/st/pblcnDsctn",
})
with urllib.request.urlopen(req, timeout=30) as r:
    print("STATUS", r.status, r.headers.get("content-type"))
    raw = r.read().decode("utf-8")
j = json.loads(raw)
data = j.get("data") or {}
print("TOP KEYS", list(j.keys()), "DATA KEYS", list(data.keys()) if isinstance(data, dict) else type(data))
for k, v in (data.items() if isinstance(data, dict) else []):
    if isinstance(v, list):
        print(f"\n=== {k}: list[{len(v)}] ===")
        for it in v[:3]:
            print(json.dumps(it, ensure_ascii=False))
        if v and isinstance(v[0], dict):
            print("keys:", list(v[0].keys()))
    else:
        print(f"=== {k}: {json.dumps(v, ensure_ascii=False)[:300]}")
# 스피또2000 69회차(화면: 입고율 96%, 1등 4/10, 2등 6/30) 와 대조할 항목
for k, v in (data.items() if isinstance(data, dict) else []):
    if isinstance(v, list):
        for it in v:
            s = json.dumps(it, ensure_ascii=False)
            if '"ltEpsd": 69' in s or '"ltEpsd":69' in s:
                print(f"[69회차 in {k}]", s)
