"""
스피또 데이터 수집 모듈 (scraper.py)
=====================================
동행복권 발행내역 페이지에서 스피또 데이터를 자동 수집합니다.
- 대상 URL: https://www.dhlottery.co.kr/st/pblcnDsctn
- 수집 항목: 판매상태, 회차, 입고율, 1등/2등 잔여수량, 판매기한 등
"""

import re
import asyncio
from playwright.async_api import async_playwright


# ── 점수 계산 공식 ─────────────────────────────────────────
def calculate_score(ship_rate: float, first: int, second: int) -> int:
    """
    유리도 종합점수 (0~100점)
    ┌─────────────────────────────────────────┐
    │ 입고율   → 최대 50점  (입고율 × 0.5)    │
    │ 1등 잔여 → 매당 20점  (최대 40점)       │
    │ 2등 잔여 → 매당 3점   (최대  9점)       │
    └─────────────────────────────────────────┘
    """
    base         = ship_rate * 0.5
    first_bonus  = min(first * 20, 40)
    second_bonus = min(second * 3, 9)
    return min(100, int(base + first_bonus + second_bonus))


# ── 셀 파싱 헬퍼 ───────────────────────────────────────────
def _to_int(s: str, default: int = 0) -> int:
    cleaned = re.sub(r"[^0-9]", "", s)
    return int(cleaned) if cleaned else default


def _to_float(s: str, default: float = 0.0) -> float:
    cleaned = re.sub(r"[^0-9.]", "", s)
    try:
        return float(cleaned) if cleaned else default
    except ValueError:
        return default


def parse_row(cells: list[str]) -> dict | None:
    """
    테이블 행(cells 배열)을 딕셔너리로 파싱합니다.
    예상 컬럼 순서:
      [0] 판매상태  [1] 상품명   [2] 회차
      [3] 입고율   [4] 1등잔여  [5] 2등잔여
      [6] 판매가격  [7] 1등당첨금 [8] 판매기한  [9] 지급기한
    """
    if len(cells) < 6:
        return None

    try:
        status   = cells[0].strip()
        product  = cells[1].strip()
        round_no = _to_int(cells[2])
        ship_rate= _to_float(cells[3])
        first    = _to_int(cells[4])
        second   = _to_int(cells[5]) if len(cells) > 5 else 0
        price    = cells[6].strip() if len(cells) > 6 else ""
        prize    = cells[7].strip() if len(cells) > 7 else ""
        deadline = cells[8].strip() if len(cells) > 8 else ""

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
        print(f"[WARN] 행 파싱 오류: {e} | cells={cells}")
        return None


# ── 메인 스크래퍼 ──────────────────────────────────────────
async def scrape_speitto_data() -> list[dict]:
    """
    동행복권 스피또 발행내역 3종(500/1000/2000)을 수집합니다.
    반환값: 정렬된 딕셔너리 리스트
    """
    product_codes = ["st2000", "st1000", "st500"]
    all_results: list[dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--single-process",        # 메모리 절약 (Render 무료 티어)
            ],
        )

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
        )
        page = await context.new_page()

        # 이미지·폰트·CSS 차단 → 속도 3~5배 향상
        await page.route(
            "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,eot,ico}",
            lambda route: route.abort(),
        )

        for code in product_codes:
            url = f"https://www.dhlottery.co.kr/st/pblcnDsctn?stGmTypeCd={code}"
            print(f"[INFO] 수집 중: {url}")

            try:
                await page.goto(url, wait_until="networkidle", timeout=40000)

                # 테이블 데이터가 화면에 나타날 때까지 대기
                try:
                    await page.wait_for_selector(
                        "table tbody tr td", timeout=20000
                    )
                except Exception:
                    print(f"[WARN] {code}: 테이블 데이터 없음 (타임아웃)")
                    continue

                # JavaScript로 테이블 전체 행 추출
                rows: list[list[str]] = await page.evaluate(
                    """
                    () => {
                        const rows = document.querySelectorAll('table tbody tr');
                        return Array.from(rows).map(row => {
                            const cells = row.querySelectorAll('td');
                            return Array.from(cells).map(td => td.innerText.trim());
                        }).filter(row => row.length >= 6);
                    }
                    """
                )

                parsed = [parse_row(r) for r in rows]
                items  = [x for x in parsed if x is not None]
                print(f"[INFO] {code}: {len(items)}개 수집")
                all_results.extend(items)

            except Exception as e:
                print(f"[ERROR] {code} 수집 실패: {e}")
                continue

        await browser.close()

    # 정렬: 판매중 우선 → 종합점수 내림차순
    all_results.sort(
        key=lambda x: (0 if x["status"] == "판매중" else 1, -x["score"])
    )
    return all_results
