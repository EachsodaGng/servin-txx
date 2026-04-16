import asyncio
import json
import os
import re
import requests
from langdetect import detect
from playwright.async_api import async_playwright, TimeoutError
import time
import shutil

# ================== CONFIG ==================
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
if not WEBHOOK_URL:
    raise RuntimeError("DISCORD_WEBHOOK_URL environment variable is not set")
TARGET_URL = "https://create.roblox.com/store/audio/discoverNewAudio/distrokid-hits"
PROFILE_DIR = "roblox_profile"
SEEN_FILE = "seen_audio.json"
DOWNLOAD_DIR = "downloads"
CHECK_INTERVAL = 1  # Faster monitoring
SCROLL_TIMES = 3  # Fewer scrolls
TAB_COUNT = 20  # Number of tabs to open
RESTART_INTERVAL = 999  # Restart the browser every 999 seconds
# ============================================

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ---------------- SEEN STORAGE ----------------
if os.path.exists(SEEN_FILE):
    with open(SEEN_FILE, "r", encoding="utf-8") as f:
        seen = set(json.load(f))
else:
    seen = set()

def save_seen():
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen), f, indent=2)

# ---------------- HELPERS ----------------
def detect_language(text):
    try:
        return detect(text)
    except Exception:
        return "unknown"

def download_audio(asset_id):
    if not re.fullmatch(r"\d+", str(asset_id)):
        print(f"Invalid asset ID (non-numeric): {asset_id}")
        return None
    url = f"https://assetdelivery.roblox.com/v1/asset?id={asset_id}"
    path = os.path.join(DOWNLOAD_DIR, f"{asset_id}.ogg")

    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        with open(path, "wb") as f:
            f.write(r.content)
    except requests.RequestException as e:
        print(f"Failed to download audio for {asset_id}: {e}")
        return None

    return path

def send_to_discord(name, asset_id, asset_url, lang, image_path, audio_path):
    emoji = "🌍" if lang != "en" else "🇺🇸"

    payload = {
        "content": (
            f"{emoji} **New Roblox Audio**\n"
            f"**Name:** {name}\n"
            f"**Language:** {lang}\n"
            f"**Asset ID:** `{asset_id}`\n"
            f"**URL:** {asset_url}"
        )
    }

    files = {}
    file_handles = []
    try:
        if os.path.exists(image_path):
            fh = open(image_path, "rb")
            file_handles.append(fh)
            files["screenshot"] = fh
        if os.path.exists(audio_path):
            fh = open(audio_path, "rb")
            file_handles.append(fh)
            files["audio"] = fh

        r = requests.post(WEBHOOK_URL, data=payload, files=files)
        if r.status_code not in (200, 204):
            print("⚠️ Discord webhook error:", r.status_code)
    except requests.RequestException as e:
        print(f"Failed to send data to Discord: {e}")
    finally:
        for fh in file_handles:
            fh.close()

# ---------------- BROWSER RUN FOR EACH TAB ----------------
async def run_browser_cycle(tab_num, context):
    try:
        print(f"✅ Tab {tab_num} - Opening page...")
        page = await context.new_page()

        await page.goto(TARGET_URL, timeout=30000)  # Reduced timeout
        await page.wait_for_timeout(2000)  # Shorter wait time

        for _ in range(SCROLL_TIMES):
            await page.mouse.wheel(0, 4000)
            await page.wait_for_timeout(1000)  # Shorter wait time between scrolls

        links = await page.query_selector_all("a[href^='/store/asset/']")
        print(f"🔍 Tab {tab_num}: Found {len(links)} assets")

        for link in links:
            href = await link.get_attribute("href")
            match = re.search(r"/asset/(\d+)", href or "")
            if not match:
                continue

            asset_id = match.group(1)
            if asset_id in seen:  # Skip asset if it's already in 'seen'
                continue

            name = (await link.inner_text()).split("\n")[0].strip()
            if not name:
                continue

            asset_url = f"https://create.roblox.com/store/asset/{asset_id}"

            await page.goto(asset_url, timeout=30000)  # Reduced timeout
            await page.wait_for_timeout(2000)  # Shorter wait time

            screenshot_path = os.path.join(DOWNLOAD_DIR, f"{asset_id}.png")
            await page.screenshot(path=screenshot_path, full_page=True)

            audio_path = download_audio(asset_id)
            if not audio_path:
                print(f"Skipping asset {asset_id} due to download failure.")
                continue

            lang = detect_language(name)

            send_to_discord(
                name,
                asset_id,
                asset_url,
                lang,
                screenshot_path,
                audio_path
            )

            seen.add(asset_id)
            save_seen()
            print(f"✅ Tab {tab_num}: Sent:", asset_id)

        await page.close()

    except TimeoutError:
        print(f"⏱ Tab {tab_num}: Timeout — retrying page")
    except Exception as e:
        print(f"💥 Tab {tab_num} failure:", e)

# ---------------- BROWSER CONTEXT MANAGER ----------------
async def launch_browser(p):
    try:
        print("🔄 Launching browser...")
        context = await p.chromium.launch_persistent_context(PROFILE_DIR, headless=False)
        return context
    except Exception as e:
        print(f"⚠️ Error launching persistent context: {e}")
        # Attempt to create a new profile if persistent context fails
        temp_profile_dir = os.path.join(PROFILE_DIR, "temp")
        if os.path.exists(temp_profile_dir):
            shutil.rmtree(temp_profile_dir)
        os.makedirs(temp_profile_dir)

        return await p.chromium.launch_persistent_context(temp_profile_dir, headless=False)

# ---------------- CONTEXT VALIDATION ----------------
async def ensure_valid_context(context, p):
    try:
        # Attempt to open a new page in the context to check validity
        await context.new_page()
        return True, context  # Context is valid, return True and the current context
    except Exception as e:
        print(f"⚠️ Context invalid: {e}")
        print("🔄 Reopening the browser context...")
        try:
            await context.close()  # Close invalid context
        except Exception as close_error:
            print(f"❌ Error closing context: {close_error}")
        # Recreate context
        context = await launch_browser(p)
        return False, context  # Return False and the newly created context

# ---------------- SUPERVISOR (IMMORTAL) ----------------
async def supervisor():
    async with async_playwright() as p:
        print("🚀 Launching persistent browser...")

        # Initial browser context
        context = await launch_browser(p)

        # Track time for browser restart
        start_time = time.time()

        while True:
            try:
                current_time = time.time()

                # Restart browser every RESTART_INTERVAL seconds
                if current_time - start_time >= RESTART_INTERVAL:
                    print("⏳ Restarting the browser...")
                    try:
                        await context.close()
                    except Exception as e:
                        print("Error closing context:", e)
                    context = await launch_browser(p)
                    start_time = current_time  # Reset start time

                # Ensure context is valid before opening tabs
                is_valid, context = await ensure_valid_context(context, p)

                if is_valid:
                    # Open multiple tabs
                    tasks = []
                    for tab_num in range(1, TAB_COUNT + 1):  # Corrected loop range
                        tasks.append(run_browser_cycle(tab_num, context))

                    # Run all tasks concurrently
                    await asyncio.gather(*tasks)

            except Exception as e:
                print("💥 Supervisor encountered an error:", e)
                print("🔄 Reopening browser context and continuing...")
                try:
                    await context.close()  # Close the existing context if it failed
                except Exception as close_error:
                    print("Error closing context during supervisor recovery:", close_error)

                # Attempt to reopen the browser context
                context = await launch_browser(p)

# ---------------- ENTRY ----------------
asyncio.run(supervisor())
