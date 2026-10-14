"""
동행복권 스피또 발행내역 수집 스크립트
GitHub Actions에서 매시간 실행 → docs/data.json 에 저장

발행내역 페이지(https://www.dhlottery.co.kr/st/pblcnDsctn)가 내부적으로 부르는 JSON API를 읽는다.
- 수집에 실패하면(0건) 기존 data.json 을 건드리지 않고 종료코드 1로 끝낸다.
- 데이터 내용이 바뀌었을 때만 data.json 을 다시 쓴다(불필요한 커밋 방지).
"""
import json, os, re, sys, time, urllib.request
from datetime import datetime, timezone, timedelta

API = "https://www.dhlottery.co.kr/st/selectPblcnDsctn.do"
PAGE = "https://www.dhlottery.co.kr/st/pblcnDsctn"
OUT = "docs/data.json"
HISTORY = "docs/history.json"
IMG_BASE = "https://www.dhlottery.co.kr"
KST = timezone(timedelta(hours=9))
PER_PAGE = 100

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": PAGE,
}

# ── 점수 계산 ─────────────────────────────────────────────
# 당첨 확률이 아니라 "주목도" 지표다. 화면 범례(docs/index.html)와 같이 유지할 것.
def score(ship, first, second):
    return int(ship * 0.5 + min(first * 20, 40) + min(second * 3, 9))

def ratio(s):
    """'4매/10매' → (4, 10)"""
    m = re.match(r"\s*([\d,]+)\D+([\d,]+)", str(s or ""))
    if not m: return 0, 0
    return int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))

def fetch(page_num):
    qs = f"?gdsType=&gdsPrice=&gdsStatus=&pageNum={page_num}&recordCountPerPage={PER_PAGE}&_={int(time.time()*1000)}"
    req = urllib.request.Request(API + qs, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def fetch_all():
    for attempt in range(1, 4):
        try:
            rows, rank_dates, page_num, total = [], [], 1, None
            while True:
                data = (fetch(page_num) or {}).get("data") or {}
                total = data.get("total", 0)
                rows += data.get("list") or []
                rank_dates += data.get("stRnkDate") or []
                if len(rows) >= total or not data.get("list"): break
                page_num += 1
            print(f"[API] total={total}, 받은 행={len(rows)}")
            return rows, rank_dates
        except Exception as e:
            print(f"[시도 {attempt}] {type(e).__name__}: {str(e)[:200]}")
            if attempt < 3: time.sleep(15)
    return [], []

def parse(rows, rank_dates):
    # 등수별 잔여수량 기준일: (상품코드, 회차, 등수) → 'YY-MM-DD'
    rdate = {(d.get("stGmTypeCd"), d.get("ltEpsd"), d.get("wnSqNo")): d.get("dataChgDt", "")
             for d in rank_dates}
    items = []
    for r in rows:
        try:
            if r.get("stExpsrYn", "Y") != "Y": continue
            first, first_total = ratio(r.get("stRnk1Rt"))
            second, second_total = ratio(r.get("stRnk2Rt"))
            third, third_total = ratio(r.get("stRnk3Rt"))
            code, rnd = r.get("stGmTypeCd"), int(r.get("stEpsd") or 0)
            price = r.get("stNtslAmt")
            img = r.get("stMainImgStrgPathNm") or ""
            item = {
                "id":          f"{code}-{rnd}",
                "code":        code,
                "status":      r.get("ntslStatus", ""),
                "product":     re.sub(r"\s+", "", r.get("stGmTypeNm", "")),
                "round":       rnd,
                "shipRate":    float(r.get("stSpmtRt") or 0),
                "first":       first,
                "firstTotal":  first_total,
                "second":      second,
                "secondTotal": second_total,
                "third":       third,
                "thirdTotal":  third_total,
                "price":       f"{int(price):,}원" if price else "",
                "prize":       r.get("rnk1Atm", ""),
                "salesEnd":    r.get("stNtslEndDt", ""),
                "claimEnd":    r.get("stGiveEndDt", ""),
                "baseDate":    r.get("dataChgDt", ""),
                "firstDate":   rdate.get((code, rnd, 1), ""),
                "secondDate":  rdate.get((code, rnd, 2), ""),
                "image":       (IMG_BASE + img) if img.startswith("/") else img,
            }
            if not item["product"] or not rnd: continue
            item["score"] = score(item["shipRate"], first, second)
            items.append(item)
        except Exception as e:
            print(f"[WARN] 파싱오류 {r}: {e}")
    items.sort(key=lambda x: (0 if x["status"] == "판매중" else 1, -x["score"]))
    return items

def update_history(data, now):
    """회차별 입고율·잔여 수량 변화 이력. 값이 바뀐 날에만 한 점을 추가한다.
    형식: {"SP2000-69": [["2026-10-13", 입고율, 1등잔여, 2등잔여, 3등잔여], ...]}

    soldOut: 1등 잔여가 1 이상 → 0 으로 바뀌는 것을 직접 본 회차의 그 순간 입고율.
    이력 수집 전에 이미 0이던 회차는 그 시점 값을 알 수 없어 기록하지 않는다.
    형식: {"SP2000-69": {"seen": "2026-10-20", "shipRate": 97.0, "firstDate": "26-10-19"}}"""
    try:
        with open(HISTORY, encoding="utf-8") as f: hist = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        hist = {}
    series = hist.setdefault("series", {})
    sold_out = hist.setdefault("soldOut", {})
    today = now.strftime("%Y-%m-%d")
    for d in data:
        point = [today, d["shipRate"], d["first"], d["second"], d["third"]]
        s = series.setdefault(d["id"], [])
        if s and s[-1][1:] == point[1:]: continue
        if s and s[-1][2] > 0 and d["first"] == 0 and d["id"] not in sold_out:
            sold_out[d["id"]] = {"seen": today, "shipRate": d["shipRate"], "firstDate": d["firstDate"]}
            print(f"[1등 소진] {d['id']} 입고율 {d['shipRate']}%")
        if s and s[-1][0] == today: s[-1] = point   # 같은 날 여러 번 바뀌면 마지막 값만
        else: s.append(point)
    hist["fields"] = ["date", "shipRate", "first", "second", "third"]
    with open(HISTORY, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, separators=(",", ":"))

def main():
    rows, rank_dates = fetch_all()
    data = parse(rows, rank_dates)
    if not data:
        print("\n[FAIL] 수집된 항목이 없습니다. 기존 data.json 을 유지합니다.")
        sys.exit(1)

    old = {}
    if os.path.exists(OUT):
        try:
            with open(OUT, encoding="utf-8") as f: old = json.load(f)
        except Exception:
            pass
    if old.get("data") == data:
        print(f"\n[SKIP] 데이터 변화 없음 ({len(data)}개 항목)")
        return

    now = datetime.now(KST)
    update_history(data, now)
    output = {
        "data": data,
        "updated_at": now.strftime("%Y-%m-%d %H:%M KST"),
        "updated_at_iso": now.isoformat(timespec="seconds"),
        "total": len(data),
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n[DONE] {OUT} 저장 — {len(data)}개 항목")

if __name__ == "__main__":
    main()
