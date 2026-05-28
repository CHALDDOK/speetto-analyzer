"""
스피또 데이터 수집 모듈 v2 (scraper.py)
=========================================
개선사항:
- 네트워크 인터셉션으로 실제 API 엔드포인트 자동 탐지
- 봇 감지 대응 (stealth 헤더, 대기 처리)
- 상세 디버그 로그 (Render.com Logs 탭에서 확인 가능)
- API 직접 호출 → DOM 파싱 순서로 fallback
"""

import re
import json
import asyncio
from playwright.async_api import async_playwright


# ── 점수 계산 ──────────────────────────────────────────────
def calculate_score(ship_rate: float, first: int, second: int) -> int:
    base         = ship_rate * 0.5
    first_bonus  = min(first * 20, 40)
    second_bonus = min(second * 3, 9)
    return min(100, int(base + first_bonus + second_bonus))


def _to_int(s: str, default: int = 0) -> int:
    cleaned = re.sub(r"[^0-9]", "", str(s))
    return int(cleaned) if cleaned else default


def _to_float(s: str, default: float = 0.0) -> float:
    cleaned = re.sub(r"[^0-9.]", "", str(s))
    try:
        return float(cleaned) if cleaned else default
    except ValueError:
        return default


def parse_row(cells: list) -> dict | None:
    if len(cells) < 6:
        return None
    try:
        status    = str(cells[0]).strip()
        product   = str(cells[1]).strip()
        round_no  = _to_int(cells[2])
        ship_rate = _to_float(cells[3])
        first     = _to_int(cells[4])
        second    = _to_int(cells[5]) if len(cells) > 5 else 0
        price     = str(cells[6]).strip() if len(cells) > 6 else ""
        prize     = str(cells[7]).strip() if len(cells) > 7 else ""
        deadline  = str(cells[8]).strip() if len(cells) > 8 else ""

        if not product or not status:
            return None

        return {
            "status":   status,
            "product":  product,
            "round":    round_no,
            "shipRate": ship_rate,
            "first":    first,
            "second":   second,
            "price":    price,
            "prize":    prize,
            "deadline": deadline,
            "score":    calculate_score(ship_rate, first, second),
        }
    except Exception as e:
        print(f"[WARN] 행 파싱 오류: {e}")
        return None


def parse_api_json(data) -> list[dict]:
    """API JSON 응답에서 데이터 추출 시도 (구조가 파악되면 여기서 처리)"""
    results = []
    try:
        # 리스트 형태인 경우
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    # 동행복권 API 응답 키를 실제 확인 후 매핑 필요
                    # 아래는 추정 키명 - 로그에서 실제 키 확인 후 수정
                    status    = item.get('saleStts') or item.get('status') or item.get('판매상태', '')
                    product   = item.get('prdNm') or item.get('productName') or item.get('상품명', '')
                    round_no  = item.get('rtry') or item.get('round') or item.get('회차', 0)
                    ship_rate = item.get('entrPct') or item.get('shipRate') or item.get('입고율', 0)
                    first     = item.get('frstRmnd') or item.get('first') or item.get('1등잔여', 0)
                    second    = item.get('scndRmnd') or item.get('second') or item.get('2등잔여', 0)
                    price     = item.get('salePrc') or item.get('price', '')
                    prize     = item.get('frstWinAmnt') or item.get('prize', '')
                    deadline  = item.get('saleEndDt') or item.get('deadline', '')

                    if product:
                        results.append({
                            "status":   str(status),
                            "product":  str(product),
                            "round":    _to_int(str(round_no)),
                            "shipRate": _to_float(str(ship_rate)),
                            "first":    _to_int(str(first)),
                            "second":   _to_int(str(second)),
                            "price":    str(price),
                            "prize":    str(prize),
                            "deadline": str(deadline),
                            "score":    calculate_score(
                                            _to_float(str(ship_rate)),
                                            _to_int(str(first)),
                                            _to_int(str(second))
                                        ),
                        })

        # 딕셔너리 안에 리스트가 있는 경우
        elif isinstance(data, dict):
            for key, val in data.items():
                if isinstance(val, list) and len(val) > 0:
                    print(f"[API] 키 '{key}' 에서 리스트 발견 (길이 {len(val)}), 파싱 시도...")
                    sub = parse_api_json(val)
                    results.extend(sub)

    except Exception as e:
        print(f"[WARN] API JSON 파싱 오류: {e}")

    return results


# ── 메인 스크래퍼 ──────────────────────────────────────────
async def scrape_speitto_data() -> list[dict]:
    all_results: list[dict] = []
    found_via_api = False

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--single-process",
                "--disable-blink-features=AutomationControlled",  # 봇 감지 우회
            ],
        )

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
            viewport={"width": 1280, "height": 800},
            extra_http_headers={
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124"',
                "sec-ch-ua-platform": '"Windows"',
                "Referer": "https://www.dhlottery.co.kr/",
            },
        )

        # webdriver 속성 숨기기
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        page = await context.new_page()

        # ── 네트워크 인터셉션: 모든 JSON 응답 캡처 ──────────
        api_responses: dict[str, any] = {}

        async def handle_response(response):
            try:
                ct = response.headers.get("content-type", "")
                if "json" in ct and "dhlottery.co.kr" in response.url:
                    try:
                        data = await response.json()
                        api_responses[response.url] = data
                        print(f"[API 탐지] {response.url}")
                        print(f"  └ 데이터 미리보기: {str(data)[:200]}")
                    except Exception:
                        pass
            except Exception:
                pass

        page.on("response", handle_response)

        # ── 페이지 방문 (필터 없이 전체 조회) ────────────────
        target_url = "https://www.dhlottery.co.kr/st/pblcnDsctn"
        print(f"\n[INFO] 접속 시도: {target_url}")

        try:
            resp = await page.goto(target_url, wait_until="networkidle", timeout=45000)
            status_code = resp.status if resp else "없음"
            print(f"[INFO] HTTP 응답코드: {status_code}")

            # 페이지 제목 및 본문 확인
            title     = await page.title()
            body_text = await page.evaluate("() => document.body?.innerText?.slice(0,400) || ''")
            print(f"[INFO] 페이지 제목: {title}")
            print(f"[INFO] 본문 미리보기:\n{body_text[:300]}\n")

            # 봇 감지 / 대기열 처리
            if any(kw in body_text for kw in ["차단", "대기", "blocked", "queue"]):
                print("[WARN] 봇 감지 또는 대기열 감지! 30초 후 재시도...")
                await asyncio.sleep(30)
                await page.reload(wait_until="networkidle", timeout=45000)
                body_text = await page.evaluate("() => document.body?.innerText?.slice(0,400) || ''")
                print(f"[INFO] 재시도 후 본문:\n{body_text[:300]}\n")

            # 테이블 대기
            try:
                await page.wait_for_selector("table tbody tr td", timeout=20000)
                print("[INFO] ✅ 테이블 데이터 발견!")
            except Exception:
                print("[WARN] 테이블을 찾지 못했습니다. DOM 상태를 확인합니다...")
                debug_info = await page.evaluate("""
                    () => ({
                        tables:  document.querySelectorAll('table').length,
                        tbodies: document.querySelectorAll('tbody').length,
                        trs:     document.querySelectorAll('tr').length,
                        tds:     document.querySelectorAll('td').length,
                        html_snippet: document.body?.innerHTML?.slice(0, 500) || ''
                    })
                """)
                print(f"[DEBUG] DOM 상태: {json.dumps(debug_info, ensure_ascii=False, indent=2)}")

            # ── API 응답으로 데이터 파싱 시도 ──────────────────
            print(f"\n[INFO] 캡처된 API 응답 수: {len(api_responses)}")
            for url, data in api_responses.items():
                print(f"  [API] {url}")
                parsed = parse_api_json(data)
                if parsed:
                    print(f"  └ {len(parsed)}개 항목 파싱 성공!")
                    all_results.extend(parsed)
                    found_via_api = True

            # ── DOM 파싱 fallback ───────────────────────────────
            if not found_via_api:
                print("[INFO] API 직접 파싱 실패 → DOM에서 추출 시도...")
                rows = await page.evaluate("""
                    () => {
                        // 여러 가지 셀렉터 시도
                        let rows = document.querySelectorAll('table tbody tr');
                        if (rows.length === 0) rows = document.querySelectorAll('tbody tr');
                        if (rows.length === 0) rows = document.querySelectorAll('tr');

                        return Array.from(rows).map(row => {
                            const cells = row.querySelectorAll('td');
                            return Array.from(cells).map(td => td.innerText?.trim() || '');
                        }).filter(r => r.length >= 4);
                    }
                """)
                print(f"[INFO] DOM에서 {len(rows)}개 행 발견")

                if rows:
                    for r in rows:
                        print(f"  행 샘플: {r}")  # 첫 몇 개 출력해서 구조 파악
                    for row in rows:
                        item = parse_row(row)
                        if item:
                            all_results.append(item)

        except Exception as e:
            print(f"[ERROR] 페이지 접근 실패: {e}")

        await browser.close()

    # 정렬
    all_results.sort(key=lambda x: (0 if x["status"] == "판매중" else 1, -x["score"]))
    print(f"\n[RESULT] 최종 수집 항목: {len(all_results)}개")
    return all_results
