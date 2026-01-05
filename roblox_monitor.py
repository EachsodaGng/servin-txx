import requests
import json
import os
from langdetect import detect

# 🔗 PUT YOUR DISCORD WEBHOOK HERE
WEBHOOK_URL = "MTQ1Njc3NTE1NDE1NDYwNjcyNQ.GtwZBO.c10z2PHo4Y_ww2uGAc9E_kxmCOtUlELtTQCuTI"

# ✅ NEW WORKING ROBLOX API
API_URL = "https://create.roblox.com/apis/marketplace-items/v1/items"

PARAMS = {
    "itemType": "Asset",
    "assetType": "Audio",
    "sortOrder": "Desc",
    "limit": 100
}

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

SEEN_FILE = "seen_audio.json"

if os.path.exists(SEEN_FILE):
    with open(SEEN_FILE, "r", encoding="utf-8") as f:
        seen = set(json.load(f))
else:
    seen = set()

def detect_language(text):
    try:
        return detect(text)
    except:
        return "unknown"

def send_to_discord(name, asset_id, lang):
    is_non_english = lang != "en"
    emoji = "🌍" if is_non_english else "🇺🇸"

    payload = {
        "embeds": [
            {
                "title": f"{emoji} {'NON-ENGLISH AUDIO' if is_non_english else 'English Audio'}",
                "color": 15158332 if is_non_english else 3447003,
                "fields": [
                    {"name": "Name", "value": name, "inline": False},
                    {"name": "Language", "value": lang, "inline": True},
                    {"name": "Asset ID", "value": str(asset_id), "inline": True},
                    {
                        "name": "Link",
                        "value": f"https://create.roblox.com/store/asset/{asset_id}",
                        "inline": False
                    }
                ]
            }
        ]
    }

    requests.post(WEBHOOK_URL, json=payload)

def main():
    r = requests.get(API_URL, headers=HEADERS, params=PARAMS)
    r.raise_for_status()

    items = r.json().get("items", [])
    sent = 0

    for item in items:
        asset = item.get("asset", {})
        asset_id = str(asset.get("assetId"))
        name = asset.get("name", "").strip()

        if not name or asset_id in seen:
            continue

        lang = detect_language(name)
        send_to_discord(name, asset_id, lang)

        seen.add(asset_id)
        sent += 1

    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen), f, indent=2)

    print(f"✅ Sent {sent} audios to Discord.")

if __name__ == "__main__":
    main()
