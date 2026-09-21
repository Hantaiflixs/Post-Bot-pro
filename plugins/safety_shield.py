# -*- coding: utf-8 -*-
import __main__
import requests
import logging
import re

logger = logging.getLogger(__name__)

# --- API Keys ---
# আপনার নতুন পার্সোনাল API Key (সবচেয়ে সিকিউর)
IMGBB_API_KEY = "572f39fe6a8752d562dcfa1d2360d1be"
IMGUR_CLIENT_ID = "546c25a59c58ad7"
FREEIMAGE_API_KEY = "6d207e02198a847aa98d0a2a901485a5"

# ==========================================
# ১. মেইন সার্ভার: ImgBB (Personal API - Most Secure)
# ==========================================
def upload_to_imgbb(file_content):
    try:
        url = "https://api.imgbb.com/1/upload"
        data = {"key": IMGBB_API_KEY}
        files = {"image": ("poster.png", file_content)}
        resp = requests.post(url, data=data, files=files, timeout=20)
        if resp.status_code == 200:
            return resp.json()['data']['url']
    except Exception as e:
        logger.warning(f"[!] ImgBB Error: {e}")
    return None

# ==========================================
# ২. ব্যাকআপ ১: Postimages (Browser Mimicking Trick - 100% Free)
# ==========================================
def upload_to_postimages(file_content):
    try:
        session = requests.Session()
        # বটকে ক্রোম ব্রাউজার হিসেবে সাজানো হলো যাতে সার্ভার ব্লক না করে
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        })
        
        # প্রথমে ডাইনামিক Token কালেক্ট করা হচ্ছে
        resp = session.get('https://postimages.org/', timeout=15)
        token = ""
        match = re.search(r'name="token" value="([^"]+)"', resp.text)
        if match:
            token = match.group(1)
            
        # এবার ছবি আপলোড করা হচ্ছে
        url = "https://postimages.org/json/rr"
        data = {'token': token, 'upload_session': '', 'numfiles': '1', 'gallery': '', 'ui': '__5__', 'optsize': '0'}
        files = {'file': ('poster.png', file_content, 'image/png')}
        
        res = session.post(url, data=data, files=files, timeout=20)
        if res.status_code == 200:
            return res.json().get('url')
    except Exception as e:
        logger.warning(f"[!] Postimages Error: {e}")
    return None

# ==========================================
# ৩. ব্যাকআপ ২: Imgur (Restored)
# ==========================================
def upload_to_imgur(file_content):
    try:
        url = "https://api.imgur.com/3/image"
        headers = {"Authorization": f"Client-ID {IMGUR_CLIENT_ID}"}
        files = {"image": ("poster.png", file_content, "image/png")}
        resp = requests.post(url, headers=headers, files=files, timeout=15)
        if resp.status_code == 200:
            return resp.json()['data']['link']
    except Exception as e:
        logger.warning(f"[!] Imgur Error: {e}")
    return None

# ==========================================
# ৪. ব্যাকআপ ৩: Freeimage (Last Resort)
# ==========================================
def upload_to_freeimage(file_content):
    try:
        url = "https://freeimage.host/api/1/upload"
        data = {"key": FREEIMAGE_API_KEY}
        files = {"source": ("poster.png", file_content)}
        resp = requests.post(url, data=data, files=files, timeout=20)
        if resp.status_code == 200:
            return resp.json()['image']['url']
    except Exception as e:
        logger.warning(f"[!] Freeimage Error: {e}")
    return None


# ==========================================
# 🚀 ব্রেইন / ফলব্যাক কন্ট্রোলার (The Core)
# ==========================================
def smart_upload_core(file_content):
    """এটি পর্যায়ক্রমে ৪টি সার্ভারে চেষ্টা করবে (ImgBB -> Postimages -> Imgur -> Freeimage)"""
    
    # Step 1: ImgBB (Primary)
    img_url = upload_to_imgbb(file_content)
    if img_url:
        logger.info("✅ Uploaded via ImgBB")
        return img_url
        
    # Step 2: Postimages
    logger.info("⚠️ ImgBB Failed! Trying Postimages...")
    img_url = upload_to_postimages(file_content)
    if img_url:
        logger.info("✅ Uploaded via Postimages")
        return img_url
        
    # Step 3: Imgur
    logger.info("⚠️ Postimages Failed! Trying Imgur...")
    img_url = upload_to_imgur(file_content)
    if img_url:
        logger.info("✅ Uploaded via Imgur")
        return img_url
        
    # Step 4: Freeimage
    logger.info("⚠️ Imgur Failed! Trying Freeimage...")
    img_url = upload_to_freeimage(file_content)
    if img_url:
        logger.info("✅ Uploaded via Freeimage")
        return img_url
    
    # যদি সব ফেইল করে
    logger.error("❌ All Image Servers are DOWN!")
    return None


# ==========================================
# প্লাগিন রিপ্লেসমেন্ট ফাংশন
# ==========================================
def patched_upload_to_catbox(file_path):
    with open(file_path, "rb") as f:
        return smart_upload_core(f.read())

def patched_upload_to_catbox_bytes(img_bytes):
    if hasattr(img_bytes, 'read'):
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
    
    print("🚀 [PLUGIN] Ultimate 4-Layer Backup Engine (ImgBB -> Postimages -> Imgur -> Freeimage) Activated!")
