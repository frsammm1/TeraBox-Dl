import os
import re
import logging
import asyncio
import time
from pyrogram import Client, filters
from pyrogram.types import Message
from curl_cffi.requests import AsyncSession
from urllib.parse import urlparse
import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def format_bytes(size):
    # 2**10 = 1024
    power = 2**10
    n = 0
    power_labels = {0 : '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power:
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}B"

def format_time(seconds):
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"
    else:
        return f"{int(seconds // 3600)}h {int((seconds % 3600) // 60)}m"

# Initialize bot
app = Client(
    "terabox_bot",
    in_memory=True,
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN
)

def extract_surl(url: str):
    parsed = urlparse(url)
    if "surl=" in parsed.query:
        return parsed.query.split("surl=")[1].split("&")[0]

    match = re.search(r'/s/([a-zA-Z0-9_-]+)', parsed.path)
    if match:
        return match.group(1)
    return None

async def get_terabox_data(surl: str, override_ndus: str = None):
    try:
        short_url = surl[1:] if surl.startswith("1") else surl

        session = AsyncSession(impersonate="chrome110")
        ndus_to_use = override_ndus if override_ndus else config.NDUS_COOKIE
        cookies = {"ndus": ndus_to_use}
        session.cookies.update(cookies)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/145.0.0.0 Safari/537.36"
        }

        first_url = f"https://dm.terabox.app/sharing/link?surl={surl}"
        response = await session.get(first_url, headers=headers)

        match = re.search(r'fn%28%22(.*?)%22%29', response.text)
        if not match:
            return None, "Failed to extract jsToken"

        jsToken = match.group(1)
        api_url = "https://dm.terabox.app/share/list"

        params = {
            "app_id": "250528",
            "jsToken": jsToken,
            "site_referer": "https://www.terabox.app/",
            "shorturl": short_url,
            "root": "1"
        }

        api_headers = {
            "Host": "dm.terabox.app",
            "User-Agent": headers["User-Agent"],
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://dm.terabox.app/sharing/link?surl={short_url}&clearCache=1",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://dm.terabox.app"
        }

        api_response = await session.get(api_url, params=params, headers=api_headers)
        data = api_response.json()
        return data, None
    except Exception as e:
        logger.error(f"Error fetching terabox data: {e}")
        return None, str(e)


@app.on_message(filters.command("start"))
async def start_cmd(client: Client, message: Message):
    await message.reply_text("Hello! Send me a Terabox link and I will download it for you.")

@app.on_message(filters.text & filters.regex(r"https?://[^\s]+"))
async def handle_link(client: Client, message: Message):
    url = message.text.strip()

    # Check if it's a valid terabox domain
    allowed_domains = ["terabox.app", "teraboxshare.com", "terabox.com", "1024terabox.com", "teraboxlink.com"]
    is_terabox = any(domain in url for domain in allowed_domains)

    if not is_terabox:
        return

    surl = extract_surl(url)
    if not surl:
        await message.reply_text("Invalid Terabox URL or couldn't extract the file ID.")
        return

    status_msg = await message.reply_text("Processing your link...")

    data, err = await get_terabox_data(surl)

    if err or not data:
        await status_msg.edit_text(f"Error fetching data: {err}")
        return

    if "list" not in data or not data["list"]:
        await status_msg.edit_text("No files found in this link.")
        return

    first_item = data["list"][0]
    filename = first_item.get("server_filename", "downloaded_file")
    dlink = first_item.get("dlink")

    active_ndus = config.NDUS_COOKIE
    if not dlink:
        # If it failed to extract direct dlink, but extraction process succeeded, we just fall back immediately
        logger.info("Could not extract direct dlink initially, looking for alternative routes.")

    # Helper to create a progress bar
    def make_progress_bar(action, filename, current, total, start_time):
        if total == 0:
            return f"{action} **{filename}**...\n\nSize: {format_bytes(current)}"

        percent = current / total
        bar_len = 20
        filled = int(bar_len * percent)
        bar = "█" * filled + "░" * (bar_len - filled)

        elapsed_time = time.time() - start_time
        speed = current / elapsed_time if elapsed_time > 0 else 0

        eta_seconds = (total - current) / speed if speed > 0 else 0
        eta = format_time(eta_seconds)

        return (
            f"**{action}**\n\n"
            f"**File:** `{filename}`\n"
            f"[{bar}] {percent:.1%}\n"
            f"**Processed:** {format_bytes(current)} / {format_bytes(total)}\n"
            f"**Speed:** {format_bytes(speed)}/s\n"
            f"**ETA:** {eta}"
        )

    # We will use an external high-speed downloader for maximum speed.
    try:
        # Ensure unique file name to avoid collisions
        unique_id = f"{message.chat.id}_{message.id}"
        file_path = f"downloads/{unique_id}_{filename}"
        os.makedirs("downloads", exist_ok=True)

        # Resolving high-speed download route natively
        await status_msg.edit_text(f"Resolving high-speed download route for {filename}...")
        resolved_dlink = None

        # We need to run curl_cffi in a separate thread since it's blocking
        def resolve_dlink(surl, cookie):
            from curl_cffi import requests
            try:
                session = requests.Session(impersonate="chrome110")

                # Try primary cookie
                session.cookies.update({"ndus": cookie})
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/145.0.0.0 Safari/537.36"
                }
                first_url = f"https://dm.terabox.app/sharing/link?surl={surl}"

                response = session.get(first_url, headers=headers)
                match = re.search(r'fn%28%22(.*?)%22%29', response.text)

                # If primary cookie fails, immediately try fallback
                if not match:
                    fallback_cookie = "YuLuQdPpeHuiMGEQDXpWDu6K2P4-xInj8YGEzswD"
                    # CRITICAL: Create a brand new session to clear any expired cookie state!
                    session = requests.Session(impersonate="chrome110")
                    session.cookies.update({"ndus": fallback_cookie})
                    response = session.get(first_url, headers=headers)
                    match = re.search(r'fn%28%22(.*?)%22%29', response.text)
                    if not match:
                        return None

                jsToken = match.group(1)
                short_url = surl[1:] if surl.startswith("1") else surl

                api_url = "https://dm.terabox.app/share/list"
                params = {
                    "app_id": "250528",
                    "jsToken": jsToken,
                    "site_referer": "https://www.terabox.app/",
                    "shorturl": short_url,
                    "root": "1"
                }
                api_headers = {
                    "Host": "dm.terabox.app",
                    "User-Agent": headers["User-Agent"],
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "en-US,en;q=0.9",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": f"https://dm.terabox.app/sharing/link?surl={short_url}&clearCache=1",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": "https://dm.terabox.app"
                }

                api_response = session.get(api_url, params=params, headers=api_headers).json()
                if 'list' in api_response and api_response['list'] and 'dlink' in api_response['list'][0]:
                    return api_response['list'][0]['dlink']

                return None
            except Exception:
                return None

        # Execute blocking function in thread pool
        resolved_dlink = await asyncio.to_thread(resolve_dlink, surl, active_ndus)

        if not resolved_dlink:
            if dlink:
                resolved_dlink = dlink
            else:
                await status_msg.edit_text("Could not find direct download link. Your ndus cookie might be invalid or expired.")
                return

        await status_msg.edit_text(f"**Downloading {filename} at maximum speed...**")

        # Download with aria2c for parallel connections and ultra fast speeds
        cmd = [
            "aria2c",
            "--console-log-level=warn",
            "--summary-interval=5",
            "--download-result=hide",
            "-x", "16",
            "-s", "16",
            "-j", "16",
            "-k", "1M",
            "-R", "true",
            "--header", f"Cookie: ndus={active_ndus}",
            "--header", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/145.0.0.0 Safari/537.36",
            "--auto-file-renaming=false",
            "-d", "downloads",
            "-o", f"{unique_id}_{filename}",
            resolved_dlink
        ]

        aria_proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        last_dl_update = time.time()
        while True:
            line = await aria_proc.stdout.readline()
            if not line:
                break

            line_str = line.decode('utf-8', errors='ignore').strip()
            # Simple parser for aria2 summary interval output
            # Ex: [#22f011 25MiB/37MiB(67%) CN:16 DL:3.2MiB ETA:3s]
            if line_str.startswith("[#") and "]" in line_str:
                current_time = time.time()
                if current_time - last_dl_update > 5:
                    match = re.search(r'\[.*? ([\w.]+)/([\w.]+)\((.*?)\).*? DL:([\w.]+).*?\]', line_str)
                    if match:
                        dl_current, dl_total, dl_percent, dl_speed = match.groups()

                        bar_len = 20
                        try:
                            percent_val = float(dl_percent.replace('%', '')) / 100.0
                        except:
                            percent_val = 0

                        filled = int(bar_len * percent_val)
                        bar = "█" * filled + "░" * (bar_len - filled)

                        eta_match = re.search(r'ETA:([0-9a-zA-Z]+)', line_str)
                        eta_str = eta_match.group(1) if eta_match else "Unknown"

                        progress_str = (
                            f"**Downloading**\n\n"
                            f"**File:** `{filename}`\n"
                            f"[{bar}] {dl_percent}\n"
                            f"**Processed:** {dl_current} / {dl_total}\n"
                            f"**Speed:** {dl_speed}/s\n"
                            f"**ETA:** {eta_str}"
                        )
                        try:
                            await status_msg.edit_text(progress_str)
                            last_dl_update = current_time
                        except:
                            pass

        await aria_proc.wait()

        if not os.path.exists(file_path):
             await status_msg.edit_text(f"Download failed: Downloaded file not found.")
             return

        await status_msg.edit_text(f"**Uploading {filename}...**\nSpeeding up upload process.")

        upload_start_time = time.time()
        last_upload_update_time = time.time()
        last_upload_update_size = 0

        async def upload_progress(current, total):
            nonlocal last_upload_update_time, last_upload_update_size
            current_time = time.time()
            if (current_time - last_upload_update_time > 5) or (total > 0 and (current - last_upload_update_size) / total > 0.1):
                progress_text = make_progress_bar("Uploading", filename, current, total, upload_start_time)
                try:
                    await status_msg.edit_text(progress_text)
                    last_upload_update_time = current_time
                    last_upload_update_size = current
                except Exception as e:
                    pass

        # Upload to Telegram
        if filename.endswith((".mp4", ".mkv", ".webm")):
            await message.reply_video(video=file_path, caption=filename, progress=upload_progress)
        else:
            await message.reply_document(document=file_path, caption=filename, progress=upload_progress)

        await status_msg.delete()

    except Exception as e:
        logger.error(f"Error during download/upload: {e}")
        await status_msg.edit_text(f"An error occurred: {e}")
    finally:
        # Clean up
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)

if __name__ == "__main__":
    logger.info("Starting bot...")
    app.run()
