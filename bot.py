
import time
import os
import requests
import feedparser
import hashlib
import html
import re
from collections import OrderedDict, deque

# -------------------
# Environment
# -------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    raise SystemExit("❌ Missing TELEGRAM_TOKEN or TELEGRAM_CHAT_ID")

# -------------------
# Subreddits
# -------------------
SUBREDDITS = [
    "CryptoCurrency","Bitcoin","ethereum","binance","CryptoMarkets",
    "CoinBase","Kraken","CoinbaseSupport","kucoin","Gemini",
    "Metamask","ledgerwallet","Trezor","trustwallet","cardano",
    "solana","dogecoin","Ripple","polkadot","UniSwap"
]

# -------------------
# Keywords
# -------------------
KEYWORDS = [
    "problem","issue","error","bug","glitch","crash","not working",
    "failed","lost","scammed","hacked","stolen","fraud",
    "phishing","locked","banned","kyc","login",
    "withdrawal","deposit","balance","urgent","wallet",
    "seed phrase","private key","network","outage","downtime",
    "exploit","attack","lawsuit","regulation"
]

# -------------------
# Settings
# -------------------
CHECK_INTERVAL = 120
SUB_DELAY = 2
HEARTBEAT_INTERVAL = 1800
MAX_SEEN = 3000

SEND_INTERVAL = 1.2
BACKOFF_START = 5
BACKOFF_MAX = 120

USER_AGENT = "railway-reddit-telegram-bot"

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})

keyword_regex = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in KEYWORDS) + r")\b",
    re.IGNORECASE
)

seen = OrderedDict()
queue = deque()
last_heartbeat = 0
last_send = 0
backoff = 0

# -------------------
# Helpers
# -------------------
def rss_url(sub):
    return f"https://www.reddit.com/r/{sub}/new/.rss"

def post_id(entry):
    return hashlib.sha256(
        (entry.get("id","") + entry.get("link","")).encode()
    ).hexdigest()

def safe(text):
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return html.escape(text)

def prune_seen():
    while len(seen) > MAX_SEEN:
        seen.popitem(last=False)

def enqueue(msg):
    queue.append(msg)

def send_worker():
    global last_send, backoff

    if not queue:
        return

    if backoff > 0:
        time.sleep(backoff)

    wait = SEND_INTERVAL - (time.time() - last_send)
    if wait > 0:
        time.sleep(wait)

    msg = queue.popleft()
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    try:
        r = session.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": msg[:4000],
                "parse_mode": "HTML",
                "disable_web_page_preview": False
            },
            timeout=10
        )

        if r.status_code == 429:
            backoff = min(backoff * 2 if backoff else BACKOFF_START, BACKOFF_MAX)
            queue.appendleft(msg)
            print(f"⚠️ Telegram rate limit hit. Backing off {backoff}s")
        else:
            backoff = 0
            last_send = time.time()

    except Exception as e:
        print("Telegram send failed:", e)
        queue.appendleft(msg)
        backoff = min(backoff * 2 if backoff else BACKOFF_START, BACKOFF_MAX)

# -------------------
# Startup
# -------------------
print("🚀 Bot started with queue + backoff")
enqueue("🚀 Reddit crypto monitoring bot started")

# -------------------
# Main loop
# -------------------
while True:
    now = time.time()

    if now - last_heartbeat > HEARTBEAT_INTERVAL:
        enqueue("🟢 Bot heartbeat: still running")
        last_heartbeat = now

    for sub in SUBREDDITS:
        try:
            feed = feedparser.parse(rss_url(sub))

            for e in feed.entries[:15]:
                pid = post_id(e)
                if pid in seen:
                    continue

                title = safe(e.get("title", ""))
                summary = safe(e.get("summary", ""))
                text = f"{title} {summary}"

                match = keyword_regex.search(text)
                if not match:
                    continue

                snippet = summary[:300] + ("..." if len(summary) > 300 else "")

                msg = (
                    f"🔔 <b>Keyword:</b> {safe(match.group(1))}\n"
                    f"<b>Subreddit:</b> r/{safe(sub)}\n"
                    f"<b>Title:</b> {title}\n"
                    f"<b>Snippet:</b> {snippet}\n"
                    f"<b>Link:</b> {e.get('link','')}"
                )

                enqueue(msg)
                seen[pid] = now
                prune_seen()

        except Exception as err:
            print(f"Error processing r/{sub}:", err)

        send_worker()
        time.sleep(SUB_DELAY)

    while queue:
        send_worker()

    time.sleep(CHECK_INTERVAL)
