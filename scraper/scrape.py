"""
동행복권 스피또 발행내역 수집 스크립트
GitHub Actions에서 매시간 실행 → docs/data.json 에 저장

- 표의 열 순서를 가정하지 않고 헤더 이름으로 열을 찾는다.
- 수집에 실패하면(0건) 기존 data.json 을 건드리지 않고 종료코드 1로 끝낸다.
- 데이터 내용이 바뀌었을 때만 data.json 을 다시 쓴다(불필요한 커밋 방지).
"""
import json, asyncio, re, os, sys
from datetime import datetime, timezone, timedelta
from playwright.async_api import async_playwright

try:
    from playwright_stealth import stealth_async
    USE_STEALTH = True
except ImportError:
    USE_STEALTH = False

URL = "https://www.dhlottery.co.kr/st/pblcnDsctn"
OUT = "docs/data.json"
KST = timezone(timedelta(hours=9))

# ── 점수 계산 ─────────────────────────────────────────────
# 당첨 확률이 아니라 "주목도" 지표다. 화면 범례(docs/index.html)와 같이 유지할 것.
def score(ship, first, second):
    return int(ship * 0.5 + min(first * 20, 40) + min(second * 3, 9))

def num(s, f=False):
    c = re.sub(r"[^0-9.]", "", str(s))
    if not c or c == ".": return 0.0 if f else 0
    return float(c) if f else int(float(c))

# ── 헤더 → 필드 매핑 ──────────────────────────────────────
# 순서가 중요하다: '1등 당첨금' 이 '1등' 잔여로 잡히지 않도록 당첨금을 먼저 본다.
HEADER_RULES = [
    ("prize",    lambda h: "당첨금" in h),
    ("first",    lambda h: "1등" in h),
    ("second",   lambda h: "2등" in h),
    ("shipRate", lambda h: "출고율" in h or "입고율" in h),
    ("round",    lambda h: "회차" in h),
    ("product",  lambda h: "상품" in h or "복권명" in h or h == "복권"),
    ("status",   lambda h: "상태" in h or "판매여부" in h or h == "판매"),
    ("price",    lambda h: "가격" in h or "판매가" in h or "금액" in h),
    ("deadline", lambda h: "마감" in h or "기한" in h or "기간" in h),
]
POSITIONAL = ["status", "product", "round", "shipRate", "first", "second", "price", "prize", "deadline"]

def map_headers(headers):
    cols = {}
    for i, h in enumerate(headers):
        h = re.sub(r"\s+", "", h)
        for field, rule in HEADER_RULES:
            if field not in cols and rule(h):
                cols[field] = i
                break
    return cols

def parse_table(headers, rows, default_product=""):
    cols = map_headers(headers)
    if not {"round", "first"} <= cols.keys():
        if headers:
            print(f"  [SKIP] 필요한 열(회차/1등)을 찾지 못함: {headers}")
            return []
        cols = {f: i for i, f in enumerate(POSITIONAL)}  # 헤더가 없으면 예전 열 순서로 시도
    print(f"  [MAP] {headers} → {cols}")

    def get(cells, f):
        i = cols.get(f)
        return cells[i].strip() if i is not None and i < len(cells) else ""

    items = []
    for cells in rows:
        try:
            product = get(cells, "product") or default_product
            rnd = num(get(cells, "round"))
            if not product or not rnd: continue
            prod_norm = re.sub(r"\s+", "", product)
            item = {
                "status":   get(cells, "status") or "판매중",
                "product":  prod_norm,
                "round":    rnd,
                "shipRate": num(get(cells, "shipRate"), f=True),
                "first":    num(get(cells, "first")),
                "second":   num(get(cells, "second")),
                "price":    get(cells, "price"),
                "prize":    get(cells, "prize"),
                "deadline": get(cells, "deadline"),
            }
            item["score"] = score(item["shipRate"], item["first"], item["second"])
            items.append(item)
        except Exception as e:
            print(f"  [WARN] 파싱오류 {cells}: {e}")
    return items

# 페이지의 모든 표를 헤더/행으로 꺼낸다. 표 근처의 제목(스피또2000 등)도 함께 가져온다.
EXTRACT_JS = r"""() => Array.from(document.querySelectorAll('table')).map(t => {
  const headRow = t.querySelector('thead tr:last-child') || t.querySelector('tr');
  const headers = headRow ? Array.from(headRow.querySelectorAll('th,td')).map(c => c.innerText.trim()) : [];
  const bodyRows = Array.from(t.querySelectorAll('tbody tr')).filter(tr => tr !== headRow);
  const rows = bodyRows.map(tr => Array.from(tr.querySelectorAll('td,th')).map(c => (c.innerText || '').trim()))
                       .filter(r => r.length >= 3);
  let title = t.caption ? t.caption.innerText : '';
  let el = t;
  for (let i = 0; i < 4 && !/스피또\s*\d+/.test(title) && el; i++) {
    let prev = el.previousElementSibling;
    while (prev && !/스피또\s*\d+/.test(prev.innerText || '')) prev = prev.previousElementSibling;
    if (prev) title = prev.innerText; else el = el.parentElement;
  }
  const m = (title || '').match(/스피또\s*\d+/);
  return { headers, rows, product: m ? m[0].replace(/\s+/g, '') : '' };
})"""

# ── 메인 스크래퍼 ─────────────────────────────────────────
async def scrape():
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage",
                  "--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
            locale="ko-KR",
            viewport={"width": 1280, "height": 900},
            extra_http_headers={"Accept-Language": "ko-KR,ko;q=0.9"},
        )
        await context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )
        page = await context.new_page()
        if USE_STEALTH:
            await stealth_async(page)

        # 진단용: 페이지가 부르는 XHR 기록
        xhrs = []
        page.on("response", lambda r: xhrs.append(f"{r.status} {r.url}")
                if r.request.resource_type in ("xhr", "fetch") else None)

        for attempt in range(1, 4):
            print(f"\n[시도 {attempt}] {URL}")
            try:
                await page.goto(URL, wait_until="networkidle", timeout=45000)
                body = await page.evaluate("() => document.body?.innerText?.slice(0,400)||''")
                print(f"  제목: {await page.title()}")
                if "차단" in body:
                    print("  [ERROR] 접속 차단 문구 감지 — 재시도 중단")
                    break
                if "대기" in body and not await page.query_selector("table tbody tr td"):
                    print("  [WARN] 대기열 감지 → 30초 후 재시도")
                    await asyncio.sleep(30)
                    continue
                await page.wait_for_selector("table tbody tr td", timeout=20000)
                print("  [OK] 표 발견")
                break
            except Exception as e:
                print(f"  [ERROR] {type(e).__name__}: {str(e)[:200]}")
                if attempt < 3: await asyncio.sleep(15)

        tables = await page.evaluate(EXTRACT_JS)
        print(f"\n[DOM] 표 {len(tables)}개")
        for t in tables:
            results += parse_table(t["headers"], t["rows"], t["product"])

        if not results:
            # 다음 수정을 위해 실제 페이지 상태를 로그로 남긴다.
            print("\n[DEBUG] 본문:", (await page.evaluate("() => document.body?.innerText||''"))[:1500])
            for t in tables[:5]:
                print("[DEBUG] 표:", t["headers"], t["rows"][:3])
            for x in xhrs[:30]:
                print("[DEBUG] XHR:", x)

        await browser.close()

    # 같은 상품·회차가 여러 표에 중복되면 하나만 남긴다
    uniq = {(d["product"], d["round"]): d for d in results}
    results = sorted(uniq.values(),
                     key=lambda x: (0 if x["status"] == "판매중" else 1, -x["score"]))
    return results


async def main():
    data = await scrape()
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
    asyncio.run(main())
