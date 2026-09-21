# -*- coding: utf-8 -*-
import __main__
import requests
import logging
import base64
import re

logger = logging.getLogger(__name__)

# --- API Keys ---
IMGBB_API_KEY = "572f39fe6a8752d562dcfa1d2360d1be"
FREEIMAGE_API_KEY = "6d207e02198a847aa98d0a2a901485a5"
IMGUR_CLIENT_ID = "546c25a59c58ad7"

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
}


# ==========================================
# ১. মেইন সার্ভার: ImgBB (Direct File Mode - Fixed)
# ==========================================
def upload_to_imgbb(file_content):
    try:
        # API Key সরাসরি URL-এ দেওয়া হলো, Base64 রিমুভ করা হয়েছে
        url = f"https://api.imgbb.com/1/upload?key={IMGBB_API_KEY}"
        files = {"image": ("poster.png", file_content, "image/png")}
        
        resp = requests.post(url, files=files, headers=COMMON_HEADERS, timeout=25)
        
        if resp.status_code == 200:
            data = resp.json()
            url_out = data.get("data", {}).get("url")
            if url_out:
                return url_out
            logger.warning(f"⚠️ ImgBB responded 200 but no url: {resp.text[:300]}")
        else:
            logger.warning(f"⚠️ ImgBB API Error [{resp.status_code}]: {resp.text[:300]}")
    except requests.exceptions.RequestException as e:
        logger.warning(f"[!] ImgBB Network Error: {e}")
    except Exception as e:
        logger.warning(f"[!] ImgBB Unexpected Error: {e}")
    return None


# ==========================================
# ২. ব্যাকআপ: Postimages (token scrape, multipart)
# ==========================================
def upload_to_postimages(file_content):
    try:
        session = requests.Session()
        session.headers.update(COMMON_HEADERS)

        resp = session.get("https://postimages.org/", timeout=15)
        match = re.search(r'name="token"\s+value="([^"]+)"', resp.text)
        if not match:
            logger.warning("⚠️ Postimages: token not found (site structure may have changed)")
            return None
        token = match.group(1)

        url = "https://postimages.org/json/rr"
        data = {
            "token": token, "upload_session": "", "numfiles": "1",
            "gallery": "", "ui": "__5__", "optsize": "0",
        }
        files = {"file": ("poster.png", file_content, "image/png")}
        res = session.post(url, data=data, files=files, timeout=25)
        if res.status_code == 200:
            url_out = res.json().get("url")
            if url_out:
                return url_out
            logger.warning(f"⚠️ Postimages: no url in response: {res.text[:300]}")
        else:
            logger.warning(f"⚠️ Postimages API Error [{res.status_code}]: {res.text[:300]}")
    except requests.exceptions.RequestException as e:
        logger.warning(f"[!] Postimages Network Error: {e}")
    except Exception as e:
        logger.warning(f"[!] Postimages Unexpected Error: {e}")
    return None


# ==========================================
# ৩. ব্যাকআপ: Freeimage (multipart)
# ==========================================
def upload_to_freeimage(file_content):
    try:
        url = "https://freeimage.host/api/1/upload"
        data = {"key": FREEIMAGE_API_KEY, "format": "json"}
        files = {"source": ("poster.png", file_content, "image/png")}
        resp = requests.post(url, data=data, files=files, headers=COMMON_HEADERS, timeout=25)
        if resp.status_code == 200:
            result = resp.json()
            url_out = result.get("image", {}).get("url")
            if url_out:
                return url_out
            logger.warning(f"⚠️ Freeimage: no url in response: {resp.text[:300]}")
        else:
            logger.warning(f"⚠️ Freeimage API Error [{resp.status_code}]: {resp.text[:300]}")
    except requests.exceptions.RequestException as e:
        logger.warning(f"[!] Freeimage Network Error: {e}")
    except Exception as e:
        logger.warning(f"[!] Freeimage Unexpected Error: {e}")
    return None


# ==========================================
# ৪. ব্যাকআপ: Imgur (ফিরিয়ে আনা হলো)
# ==========================================
def upload_to_imgur(file_content):
    try:
        url = "https://api.imgur.com/3/image"
        headers = {**COMMON_HEADERS, "Authorization": f"Client-ID {IMGUR_CLIENT_ID}"}
        files = {"image": ("poster.png", file_content, "image/png")}
        resp = requests.post(url, headers=headers, files=files, timeout=25)
        if resp.status_code == 200:
            data = resp.json()
            url_out = data.get("data", {}).get("link")
            if url_out:
                return url_out
            logger.warning(f"⚠️ Imgur responded 200 but no link: {resp.text[:300]}")
        else:
            logger.warning(f"⚠️ Imgur API Error [{resp.status_code}]: {resp.text[:300]}")
    except requests.exceptions.RequestException as e:
        logger.warning(f"[!] Imgur Network Error: {e}")
    except Exception as e:
        logger.warning(f"[!] Imgur Unexpected Error: {e}")
    return None


# ==========================================
# ৫. ব্যাকআপ: Catbox.moe (কোনো key লাগে না)
# ==========================================
def upload_to_catbox_service(file_content):
    try:
        url = "https://catbox.moe/user/api.php"
        data = {"reqtype": "fileupload"}
        files = {"fileToUpload": ("poster.png", file_content, "image/png")}
        resp = requests.post(url, data=data, files=files, headers=COMMON_HEADERS, timeout=25)
        if resp.status_code == 200 and resp.text.startswith("http"):
            return resp.text.strip()
        logger.warning(f"⚠️ Catbox API Error [{resp.status_code}]: {resp.text[:300]}")
    except requests.exceptions.RequestException as e:
        logger.warning(f"[!] Catbox Network Error: {e}")
    except Exception as e:
        logger.warning(f"[!] Catbox Unexpected Error: {e}")
    return None


# ==========================================
# ৬. ব্যাকআপ: 0x0.st (কোনো key লাগে না, শেষ ভরসা)
# ==========================================
def upload_to_0x0(file_content):
    try:
        url = "https://0x0.st"
        files = {"file": ("poster.png", file_content, "image/png")}
        resp = requests.post(url, files=files, headers=COMMON_HEADERS, timeout=25)
        if resp.status_code == 200 and resp.text.startswith("http"):
            return resp.text.strip()
        logger.warning(f"⚠️ 0x0.st API Error [{resp.status_code}]: {resp.text[:300]}")
    except requests.exceptions.RequestException as e:
        logger.warning(f"[!] 0x0.st Network Error: {e}")
    except Exception as e:
        logger.warning(f"[!] 0x0.st Unexpected Error: {e}")
    return None


# ==========================================
# 🚀 ব্রেইন / ফলব্যাক কন্ট্রোলার (The Core)
# ==========================================
UPLOAD_CHAIN = [
    ("ImgBB", upload_to_imgbb),
    ("Postimages", upload_to_postimages),
    ("Freeimage", upload_to_freeimage),
    ("Imgur", upload_to_imgur),
    ("Catbox", upload_to_catbox_service),
    ("0x0.st", upload_to_0x0),
]


def smart_upload_core(file_content):
    """একটার পর একটা সার্ভারে চেষ্টা করবে যতক্ষণ না কোনোটা সফল হয়।"""
    if not file_content:
        logger.error("❌ smart_upload_core called with empty file_content")
        return None

    for name, func in UPLOAD_CHAIN:
        logger.info(f"➡️ Trying {name}...")
        result = func(file_content)
        if result:
            logger.info(f"✅ Uploaded via {name}")
            return result
        logger.info(f"⚠️ {name} Failed! Moving to next...")

    logger.error("❌ All Image Servers are DOWN! (উপরের WARNING লগে আসল কারণ দেখো)")
    return None


# ==========================================
# প্লাগিন রিপ্লেসমেন্ট ফাংশন
# ==========================================
def patched_upload_to_catbox(file_path):
    with open(file_path, "rb") as f:
        return smart_upload_core(f.read())


def patched_upload_to_catbox_bytes(img_bytes):
    if hasattr(img_bytes, "read"):
        img_bytes.seek(0)
        return smart_upload_core(img_bytes.read())
    return smart_upload_core(img_bytes)


# =======================================================
# 🚀 PLUGIN REGISTER
# =======================================================
async def register(bot):
    __main__.upload_to_catbox = patched_upload_to_catbox
    __main__.upload_to_catbox_bytes = patched_upload_to_catbox_bytes
    __main__.upload_image_core = smart_upload_core

    chain_names = " -> ".join(name for name, _ in UPLOAD_CHAIN)
    print(f"🚀 [PLUGIN] V3 Pro 6-Layer Backup Engine ({chain_names}) Activated!")
