"""
텔레그램 알림
- 기본: docs/data.json 을 alerts/rules.json 의 조건과 비교해, 새로 조건을 만족한 회차를 알린다.
- --failure: 수집 실패를 알린다(24시간에 한 번까지).

필요한 환경변수: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (없으면 아무것도 보내지 않고 상태도 바꾸지 않는다)
알린 회차는 alerts/state.json 에 기록해 같은 알림이 매시간 반복되지 않게 한다.
"""
import json, os, sys, html, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

DATA = "docs/data.json"
RULES = "alerts/rules.json"
STATE = "alerts/state.json"
KST = timezone(timedelta(hours=9))

def load(path, default):
    try:
        with open(path, encoding="utf-8") as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default

def save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")

def send(text):
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    body = urllib.parse.urlencode({
        "chat_id": chat, "text": text, "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body)
    with urllib.request.urlopen(req, timeout=20) as r:
        if json.load(r).get("ok") is not True:
            raise RuntimeError("텔레그램 전송 실패")

def matches(d, r):
    return ((not r.get("products") or d["product"] in r["products"])
            and (not r.get("status") or d["status"] == r["status"])
            and d["shipRate"] >= r.get("minShipRate", 0)
            and d["first"]    >= r.get("minFirst", 0)
            and d["second"]   >= r.get("minSecond", 0)
            and d["score"]    >= r.get("minScore", 0))

def check_rules(state):
    data = load(DATA, {}).get("data", [])
    rules = load(RULES, {}).get("rules", [])
    page = os.environ.get("PAGE_URL", "")

    current, lines = {}, []
    for r in rules:
        for d in data:
            if not matches(d, r): continue
            key = f'{r["name"]}|{d["product"]}|{d["round"]}'
            current[key] = True
            if key not in state.get("matched", {}):
                lines.append(
                    f'• <b>{html.escape(d["product"])} {d["round"]}회차</b> ({html.escape(r["name"])})\n'
                    f'  입고율 {d["shipRate"]:g}% · 1등 잔여 {d["first"]}/{d.get("firstTotal", "?")}매 · 2등 잔여 {d["second"]}/{d.get("secondTotal", "?")}매'
                )

    if lines:
        text = "🎯 <b>스피또 알림 조건 충족</b>\n\n" + "\n".join(lines)
        text += "\n\n※ 잔여 = 아직 청구되지 않은 수량이며, 당첨을 보장하지 않습니다."
        if page: text += f'\n<a href="{html.escape(page)}">분석기 열기</a>'
        send(text)
        print(f"[알림] {len(lines)}건 전송")
    else:
        print("[알림] 새로 조건을 만족한 회차 없음")

    # 조건에서 벗어났다가 다시 만족하면 또 알리도록, 현재 만족 중인 것만 기억한다
    state["matched"] = current
    state.pop("fail_notified_at", None)  # 수집이 다시 성공했으므로 실패 알림 리셋

def notify_failure(state):
    last = state.get("fail_notified_at")
    now = datetime.now(KST)
    if last and now - datetime.fromisoformat(last) < timedelta(hours=24):
        print("[실패 알림] 24시간 내 이미 알림 — 생략")
        return
    run = os.environ.get("RUN_URL", "")
    text = "⚠️ <b>스피또 데이터 수집 실패</b>\n사이트 구조 변경이나 접속 차단일 수 있습니다."
    if run: text += f'\n<a href="{html.escape(run)}">실행 로그 보기</a>'
    send(text)
    state["fail_notified_at"] = now.isoformat(timespec="seconds")
    print("[실패 알림] 전송")

def main():
    if not (os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID")):
        print("[알림] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 가 없어 건너뜀")
        return
    state = load(STATE, {})
    if "--failure" in sys.argv:
        notify_failure(state)
    else:
        check_rules(state)
    save(STATE, state)

if __name__ == "__main__":
    main()
