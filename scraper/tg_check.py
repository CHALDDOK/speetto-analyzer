"""임시: 텔레그램 설정 점검. 공개 로그이므로 ID 값 자체는 출력하지 않는다."""
import json, os, re, urllib.request
token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
def call(m):
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/{m}", timeout=20) as r:
        return json.load(r)
me = call("getMe")["result"]
print("봇 이름:", "@" + me.get("username", "?"))
print("입력한 CHAT_ID 형식: 길이", len(chat),
      "| 숫자만:", bool(re.fullmatch(r"-?\d+", chat)),
      "| @포함:", "@" in chat, "| ':'포함(토큰?):", ":" in chat,
      "| 봇 자신의 ID와 같음:", chat == str(me.get("id")))
chats = {}
for u in call("getUpdates").get("result", []):
    c = (u.get("message") or u.get("my_chat_member") or u.get("channel_post") or {}).get("chat")
    if c: chats[str(c["id"])] = c.get("type")
print("봇이 받은 대화 수:", len(chats), "| 종류:", sorted(set(chats.values())))
print("입력한 CHAT_ID가 그 중 하나와 일치:", chat in chats)
