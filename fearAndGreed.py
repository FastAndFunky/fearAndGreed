import requests
import re
from lxml import html
from datetime import datetime, timezone

# ---------------- URLs ----------------
CNN_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
CMC_URL = "https://coinmarketcap.com/charts/fear-and-greed-index/"

# ---------------- Headers ----------------
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/",
}

# ---------------- Telegram Config ----------------

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send_telegram(msg: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg}
    try:
        r = requests.post(url, json=payload)
        r.raise_for_status()
    except Exception as e:
        print("Telegram send error:", e)

# ---------------- CNN ----------------
def get_cnn_fng():
    try:
        r = requests.get(CNN_URL, headers=HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return {"ok": False, "error": f"Fetch/JSON error: {e}"}

    fng = data.get("fear_and_greed") or data.get("fear-and-greed") or data.get("fearAndGreed")
    if not fng:
        return {"ok": False, "error": "Could not find 'fear_and_greed' in CNN JSON."}

    score = fng.get("score")
    rating = fng.get("rating") or fng.get("state")
    ts = fng.get("timestamp")
    ts_iso = None
    try:
        if isinstance(ts, (int, float)):
            # convert ms -> seconds if > 1e12
            if ts > 1e12:
                ts_dt = datetime.fromtimestamp(ts/1000, tz=timezone.utc)
            else:
                ts_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            ts_iso = ts_dt.strftime("%Y-%m-%dT%H:%M:%SZ")  # UTC ISO with Z
    except:
        ts_iso = None

    return {"ok": True, "score": score, "rating": rating, "timestamp_iso": ts_iso}

# ---------------- CoinMarketCap ----------------
def extract_from_tree(tree: html.HtmlElement):
    nodes = tree.xpath("//span[@data-test='fear-greed-index-num']")
    if nodes:
        text = nodes[0].text_content().strip()
        m = re.search(r"\b([0-9]{1,3})\b", text)
        if m:
            val = int(m.group(1))
            if 0 <= val <= 100:
                return val
    # fallback: base-text class
    nodes = tree.xpath("//span[contains(@class,'base-text')]")
    for n in nodes:
        txt = n.text_content().strip()
        m = re.search(r"\b([0-9]{1,3})\b", txt)
        if m:
            val = int(m.group(1))
            if 0 <= val <= 100:
                return val
    return None

def extract_by_comment_aware_regex(html_text: str):
    m = re.search(r"\b([0-9]{1,3})\b\s*(?:<!--.*?-->\s*)*/\s*(?:<!--.*?-->\s*)*100", html_text, flags=re.S)
    if m:
        val = int(m.group(1))
        if 0 <= val <= 100:
            return val
    return None

def get_cmc_fng():
    try:
        r = requests.get(CMC_URL, headers=HEADERS, timeout=12)
        r.raise_for_status()
        html_text = r.text
        tree = html.fromstring(r.content)
    except Exception as e:
        return {"ok": False, "error": f"Fetch error: {e}"}

    v = extract_from_tree(tree)
    if v is not None:
        return {"ok": True, "score": v, "method": "tree-data-test/class"}

    v2 = extract_by_comment_aware_regex(html_text)
    if v2 is not None:
        return {"ok": True, "score": v2, "method": "comment-aware-regex"}

    return {"ok": False, "error": "No value found (CMC may render JS)"}

# ---------------- Main ----------------
def main():
    cnn = get_cnn_fng()
    cmc = get_cmc_fng()

    # Print
    if cnn.get("ok"):
        print(f"CNN: {cnn['score']} ({cnn['rating']}) at {cnn['timestamp_iso']}")
    else:
        print("CNN ERROR:", cnn.get("error"))

    if cmc.get("ok"):
        print(f"CMC: {cmc['score']} (method: {cmc['method']})")
    else:
        print("CMC ERROR:", cmc.get("error"))

    # Check thresholds
    for source, data in [("Cable News Network CNN", cnn), ("Coin Market Cap (CMC) Crypto", cmc)]:
        if data.get("ok") and isinstance(data.get("score"), int):
            score = data["score"]
            if score >= 75 or score <= 40:
                msg = f"⚠️ {source} Fear & Greed Alert! Score={score}"
                if source == "CNN":
                    msg += f" ({data.get('rating')})"
                send_telegram(msg)
                print("Notification sent:", msg)

if __name__ == "__main__":
    main()
