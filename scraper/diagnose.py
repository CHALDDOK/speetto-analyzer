"""
임시 진단 스크립트: 발행내역 페이지의 실제 구조(테이블 헤더/행, XHR 요청)를 로그로 출력한다.
"""
import asyncio, json
from playwright.async_api import async_playwright

URL = "https://www.dhlottery.co.kr/st/pblcnDsctn"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
            locale="ko-KR",
        )
        page = await ctx.new_page()
        reqs = []
        async def on_resp(r):
            if r.request.resource_type in ("xhr", "fetch", "document"):
                body = ""
                try:
                    body = (await r.text())[:1500]
                except Exception:
                    pass
                reqs.append((r.request.method, r.url, r.status, r.headers.get("content-type", ""),
                             r.request.post_data, body))
        page.on("response", on_resp)

        resp = await page.goto(URL, wait_until="networkidle", timeout=60000)
        print("STATUS", resp.status if resp else None, "FINAL", page.url)
        print("TITLE", await page.title())
        await page.wait_for_timeout(5000)

        info = await page.evaluate("""() => ({
            text: document.body.innerText.slice(0, 3000),
            tables: Array.from(document.querySelectorAll('table')).map(t => ({
                cls: t.className, id: t.id,
                caption: t.caption ? t.caption.innerText : '',
                heads: Array.from(t.querySelectorAll('thead tr')).map(tr =>
                    Array.from(tr.children).map(c => c.innerText.trim() + (c.colSpan > 1 ? '[cs' + c.colSpan + ']' : '') + (c.rowSpan > 1 ? '[rs' + c.rowSpan + ']' : ''))),
                rows: Array.from(t.querySelectorAll('tbody tr')).slice(0, 8).map(tr =>
                    Array.from(tr.children).map(c => c.innerText.trim())),
                nrows: t.querySelectorAll('tbody tr').length,
            })),
            tabs: Array.from(document.querySelectorAll('button, a[role=tab], li a, select option'))
                .map(e => e.innerText.trim()).filter(s => /스피또|500|1000|2000/.test(s)).slice(0, 40),
            selects: Array.from(document.querySelectorAll('select')).map(s => ({
                name: s.name, id: s.id, opts: Array.from(s.options).map(o => o.value + '=' + o.text)})),
        })""")
        print("=== BODY TEXT ===\n" + info["text"])
        print("=== TABLES ===")
        print(json.dumps(info["tables"], ensure_ascii=False, indent=1))
        print("=== TABS ===", json.dumps(info["tabs"], ensure_ascii=False))
        print("=== SELECTS ===", json.dumps(info["selects"], ensure_ascii=False))
        print("=== REQUESTS ===")
        for m, u, s, ct, pd, body in reqs:
            print(f"{m} {s} {ct} {u}\n  post={pd}\n  body={body[:1500]!r}")
        html = await page.content()
        print("=== HTML (scripts mentioning ajax/url) ===")
        import re
        for m in re.findall(r"[\"'](/[A-Za-z0-9_/]+(?:\.do)?(?:\?[^\"']*)?)[\"']", html):
            if any(k in m.lower() for k in ("st", "pblc", "dsctn", "select", "list")):
                print(" ", m)
        await browser.close()

asyncio.run(main())
