"""
동행복권 스피또 발행내역 수집 스크립트
GitHub Actions에서 매시간 실행 → docs/data.json 에 저장
"""
import json, asyncio, re, os
from datetime import datetime
from playwright.async_api import async_playwright

try:
    from playwright_stealth import stealth_async
    USE_STEALTH = True
except ImportError:
    USE_STEALTH = False

# ── 점수 계산 ─────────────────────────────────────────────
def score(ship, first, second):
    return min(100, int(ship * 0.5 + min(first * 20, 40) + min(second * 3, 9)))

def num(s, f=False):
    c = re.sub(r"[^0-9.]", "", str(s))
    if not c: return 0.0 if f else 0
    return float(c) if f else int(float(c))

def parse_row(cells):
    if len(cells) < 6: return None
    try:
        item = {
            "status":   str(cells[0]).strip(),
            "product":  str(cells[1]).strip(),
            "round":    num(cells[2]),
            "shipRate": num(cells[3], f=True),
            "first":    num(cells[4]),
            "second":   num(cells[5]) if len(cells) > 5 else 0,
            "price":    str(cells[6]).strip() if len(cells) > 6 else "",
            "prize":    str(cells[7]).strip() if len(cells) > 7 else "",
            "deadline": str(cells[8]).strip() if len(cells) > 8 else "",
        }
        if not item["product"]: return None
        item["score"] = score(item["shipRate"], item["first"], item["second"])
        return item
    except Exception as e:
        print(f"[WARN] 파싱오류: {e}")
        return None

# ── 메인 스크래퍼 ─────────────────────────────────────────
async def scrape():
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox", "--disable-setuid-sandbox",
                "--disable-dev-shm-usage", "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
            viewport={"width": 1280, "height": 900},
            extra_http_headers={
                "Accept-Language": "ko-KR,ko;q=0.9",
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            },
        )

        page = await context.new_page()
        if USE_STEALTH:
            await stealth_async(page)
            print("[INFO] stealth 모드 ON")

        # webdriver 속성 숨기기
        await context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )

        # JSON API 응답 가로채기
        api_hits = {}
        async def on_resp(resp):
            try:
                if "json" in resp.headers.get("content-type","") \
                        and "dhlottery" in resp.url:
                    data = await resp.json()
                    api_hits[resp.url] = data
                    print(f"[API] {resp.url}\n  └ {str(data)[:120]}")
            except: pass
        page.on("response", on_resp)

        # ── 3번 시도 ────────────────────────────────────────
        for attempt in range(1, 4):
            print(f"\n[시도 {attempt}] https://www.dhlottery.co.kr/st/pblcnDsctn")
            try:
                await page.goto(
                    "https://www.dhlottery.co.kr/st/pblcnDsctn",
                    wait_until="networkidle", timeout=45000,
                )
                title = await page.title()
                body  = await page.evaluate(
                    "() => document.body?.innerText?.slice(0,400)||''"
                )
                print(f"  제목: {title}")
                print(f"  본문: {body[:200]}")

                if "차단" in body:
                    print("  [ERROR] IP 차단 확인됨 — 재시도 중단")
                    break

                if "대기" in body:
                    print("  [WARN] 대기열 감지 → 30초 후 재시도")
                    await asyncio.sleep(30)
                    continue

                # 테이블 로딩 대기
                try:
                    await page.wait_for_selector(
                        "table tbody tr td", timeout=20000
                    )
                    print("  [OK] 테이블 발견!")
                    break
                except:
                    dom = await page.evaluate("""()=>({
                        tables:document.querySelectorAll('table').length,
                        trs:document.querySelectorAll('tr').length,
                        tds:document.querySelectorAll('td').length,
                        snippet:document.body?.innerHTML?.slice(0,300)||''
                    })""")
                    print(f"  [DEBUG] DOM 상태: tables={dom['tables']}, trs={dom['trs']}, tds={dom['tds']}")
                    print(f"  [DEBUG] HTML snippet: {dom['snippet'][:200]}")
                    if attempt < 3:
                        await asyncio.sleep(15)

            except Exception as e:
                print(f"  [ERROR] {e}")
                if attempt < 3: await asyncio.sleep(15)

        # ── 데이터 추출 ─────────────────────────────────────
        rows = await page.evaluate("""()=>{
            let r = document.querySelectorAll('table tbody tr');
            if(!r.length) r = document.querySelectorAll('tbody tr');
            return Array.from(r).map(row=>
                Array.from(row.querySelectorAll('td'))
                    .map(td=>td.innerText?.trim()||'')
            ).filter(r=>r.length>=4);
        }""")

        print(f"\n[DOM] {len(rows)}개 행 발견")
        for r in rows[:3]: print(f"  {r}")

        for row in rows:
            item = parse_row(row)
            if item: results.append(item)

        print(f"[API 인터셉트] {len(api_hits)}개 API 응답 캡처")
        for u in api_hits: print(f"  {u}")

        await browser.close()

    results.sort(key=lambda x:(0 if x["status"]=="판매중" else 1, -x["score"]))
    return results


# ── 실행 진입점 ───────────────────────────────────────────
async def main():
    data = await scrape()
    os.makedirs("docs", exist_ok=True)
    output = {
        "data": data,
        "updated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "total": len(data),
    }
    with open("docs/data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n[DONE] docs/data.json 저장 완료 — {len(data)}개 항목")

if __name__ == "__main__":
    asyncio.run(main())
