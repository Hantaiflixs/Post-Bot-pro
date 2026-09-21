# -*- coding: utf-8 -*-
import __main__
import requests
import logging
import time
import hashlib

logger = logging.getLogger(__name__)

# --- API Keys ---
IMGBB_API_KEY = "572f39fe6a8752d562dcfa1d2360d1be"
FREEIMAGE_API_KEY = "6d207e02198a847aa98d0a2a901485a5"

# Cloudinary Credentials
CLD_NAME = "edjglpjh"
CLD_API_KEY = "433556818816211"
CLD_API_SECRET = "Hh8ZHy0pjZYD_Fi_guY9lgmgoF8"

# Lensdump API Key (থাকলে এখানে বসাও, না থাকলে ফাঁকা রাখলে guest upload ট্রাই হবে)
LENSDUMP_API_KEY = ""

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/116.0.0.0 Safari/537.36",
}

# ==========================================
# ১. ১ম সার্ভার: ImgBB
# ==========================================
def upload_to_imgbb(file_content):
    try:
        url = f"https://api.imgbb.com/1/upload?key={IMGBB_API_KEY}"
        files = {"image": ("poster.png", file_content, "image/png")}
        resp = requests.post(url, files=files, headers=COMMON_HEADERS, timeout=20)
        if resp.status_code == 200:
            return resp.json().get("data", {}).get("url")
        logger.warning(f"⚠️ ImgBB Error [{resp.status_code}]: {resp.text[:200]}")
    except Exception as e:
        logger.warning(f"[!] ImgBB Error: {e}")
    return None

# ==========================================
# ২. ২য় সার্ভার: Freeimage
# ==========================================
def upload_to_freeimage(file_content):
    try:
        url = "https://freeimage.host/api/1/upload"
        data = {"key": FREEIMAGE_API_KEY, "format": "json"}
        files = {"source": ("poster.png", file_content, "image/png")}
        resp = requests.post(url, data=data, files=files, headers=COMMON_HEADERS, timeout=20)
        if resp.status_code == 200:
            return resp.json().get("image", {}).get("url")
        logger.warning(f"⚠️ Freeimage Error [{resp.status_code}]: {resp.text[:200]}")
    except Exception as e:
        logger.warning(f"[!] Freeimage Error: {e}")
    return None

# ==========================================
# ৩. ৩য় সার্ভার: Cloudinary
# ==========================================
def upload_to_cloudinary(file_content):
    try:
        timestamp = str(int(time.time()))
        string_to_sign = f"timestamp={timestamp}{CLD_API_SECRET}"
        signature = hashlib.sha1(string_to_sign.encode('utf-8')).hexdigest()

        url = f"https://api.cloudinary.com/v1_1/{CLD_NAME}/image/upload"
        data = {
            "api_key": CLD_API_KEY,
            "timestamp": timestamp,
            "signature": signature
        }
        files = {"file": ("poster.png", file_content, "image/png")}

        resp = requests.post(url, data=data, files=files, timeout=20)
        if resp.status_code == 200:
            return resp.json().get("secure_url")
        logger.warning(f"⚠️ Cloudinary Error [{resp.status_code}]: {resp.text[:200]}")
    except Exception as e:
        logger.warning(f"[!] Cloudinary Exception: {e}")
    return None

# ==========================================
# ৪. ৪র্থ সার্ভার: Lensdump (Fallback)
# ফিক্স: Lensdump আসল key হেডারে নেয় (X-API-Key), form-data-তে না।
# ==========================================
def upload_to_lensdump(file_content):
    try:
        url = "https://lensdump.com/api/1/upload"
        data = {"format": "json"}
        files = {"source": ("poster.png", file_content, "image/png")}

        headers = dict(COMMON_HEADERS)
        if LENSDUMP_API_KEY:
            headers["X-API-Key"] = LENSDUMP_API_KEY

        resp = requests.post(url, data=data, files=files, headers=headers, timeout=20)
        if resp.status_code == 200:
            return resp.json().get("image", {}).get("url")
        logger.warning(f"⚠️ Lensdump Error [{resp.status_code}]: {resp.text[:200]}")
    except Exception as e:
        logger.warning(f"[!] Lensdump Error: {e}")
    return None

# ==========================================
# 🚀 ব্রেইন / ফলব্যাক কন্ট্রোলার
# ==========================================
UPLOAD_CHAIN = [
    ("ImgBB", upload_to_imgbb),
    ("Freeimage", upload_to_freeimage),
    ("Cloudinary", upload_to_cloudinary),
    ("Lensdump", upload_to_lensdump)
]

def smart_upload_core(file_content):
    if not file_content:
        return None

    for name, func in UPLOAD_CHAIN:
        logger.info(f"➡️ Trying {name}...")
        result = func(file_content)
        if result:
            logger.info(f"✅ Uploaded successfully via {name}")
            return result
        logger.warning(f"⚠️ {name} Failed! Moving to next...")

    logger.error("❌ All Servers are DOWN!")
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
    print(f"🚀 [PLUGIN] V6 Ultimate 4-Layer Engine ({chain_names}) Activated!")
