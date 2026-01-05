import requests

WEBHOOK_URL = "https://discord.com/api/webhooks/1456765063250837737/hHgALznytcMEMnuMypAmW7SAk2zyig1YCfRPak4hLh1MGuOSN5qYsUHfxn9gF63FD6X-"

data = {
    "content": "✅ Webhook test successful"
}

r = requests.post(WEBHOOK_URL, json=data)
print(r.status_code)
