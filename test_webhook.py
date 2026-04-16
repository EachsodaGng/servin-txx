import os
import requests

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
if not WEBHOOK_URL:
    raise RuntimeError("DISCORD_WEBHOOK_URL environment variable is not set")

data = {
    "content": "✅ Webhook test successful"
}

r = requests.post(WEBHOOK_URL, json=data)
print(r.status_code)
