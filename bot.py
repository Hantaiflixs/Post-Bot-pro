# -*- coding: utf-8 -*-

# 🔥 PYTHON 3.13 ASYNCIO FIX (MAGIC BYPASS) 🔥
import asyncio
if not hasattr(asyncio, 'coroutine'):
    asyncio.coroutine = lambda f: f

import os
import io
import re
import importlib
import pkgutil
import json
import time
import logging
import random
import string
import base64
import datetime
import aiohttp
import requests 
import urllib3 
import numpy as np 
import cv2 
from threading import Thread

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, Message,
    CallbackQuery
)
from flask import Flask
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient 

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

# ---- CONFIGURATION ----
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")

MONGO_URL = os.getenv("MONGO_URL") 
OWNER_ID = int(os.getenv("OWNER_ID", 0)) 
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "admin") 
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "-1003834633374"))
DB_CHANNEL_ID = int(os.getenv("DB_CHANNEL_ID", "-1004387130022")) 

worker_client = None

if not all([BOT_TOKEN, API_ID, API_HASH, TMDB_API_KEY, MONGO_URL]):
    logger.critical("❌ FATAL ERROR: Variables missing in .env file!")
    exit(1)

# ====================================================================
# 🔥 DATABASE CONNECTION
# ====================================================================
try:
    mongo_client = AsyncIOMotorClient(MONGO_URL)
    db = mongo_client["movie_bot_db"]
    users_col = db["users"]
    settings_col = db["settings"]
    user_settings_col = db["user_settings"]
    posts_col = db["posts"] 
    logger.info("✅ MongoDB Connected Successfully!")
except Exception as e:
    logger.critical(f"❌ MongoDB Connection Failed: {e}")
    exit(1)

DEFAULT_OWNER_AD_LINKS = ["https://www.google.com", "https://www.bing.com"]
DEFAULT_USER_AD_LINKS = ["https://www.google.com", "https://www.bing.com"] 

user_conversations = {}
upload_semaphore = asyncio.Semaphore(2)

# ---- DATABASE FUNCTIONS ----
async def add_user(user_id, name):
    if not await users_col.find_one({"_id": user_id}):
        await users_col.insert_one({"_id": user_id, "name": name, "authorized": False, "banned": False, "joined_date": datetime.datetime.now()})

async def is_authorized(user_id):
    if user_id == OWNER_ID: return True
    user = await users_col.find_one({"_id": user_id})
    if not user: return False
    return user.get("authorized", False) and not user.get("banned", False)

async def is_banned(user_id):
    user = await users_col.find_one({"_id": user_id})
    return user and user.get("banned", False)

async def get_owner_ads():
    data = await settings_col.find_one({"_id": "main_config"})
    return data.get("owner_ads", DEFAULT_OWNER_AD_LINKS) if data else DEFAULT_OWNER_AD_LINKS

async def set_owner_ads_db(links):
    await settings_col.update_one({"_id": "main_config"}, {"$set": {"owner_ads": links}}, upsert=True)

async def get_auto_delete_timer():
    data = await settings_col.find_one({"_id": "main_config"})
    return data.get("auto_delete_seconds", 600) if data else 600

async def set_auto_delete_timer_db(seconds):
    await settings_col.update_one({"_id": "main_config"}, {"$set": {"auto_delete_seconds": int(seconds)}}, upsert=True)

async def auto_delete_task(client, chat_id, message_ids, delay):
    if delay <= 0: return
    await asyncio.sleep(delay)
    try: await client.delete_messages(chat_id, message_ids)
    except: pass

async def get_admin_share():
    data = await settings_col.find_one({"_id": "main_config"})
    return data.get("admin_share_percent", 20) if data else 20

async def set_admin_share_db(percent):
    await settings_col.update_one({"_id": "main_config"}, {"$set": {"admin_share_percent": int(percent)}}, upsert=True)

async def get_user_ads(user_id):
    data = await user_settings_col.find_one({"_id": user_id})
    return data.get("ad_links", DEFAULT_USER_AD_LINKS) if data else DEFAULT_USER_AD_LINKS

async def save_user_ads(user_id, links):
    await user_settings_col.update_one({"_id": user_id}, {"$set": {"ad_links": links}}, upsert=True)

async def get_all_users_count(): return await users_col.count_documents({})

async def get_worker_session():
    data = await settings_col.find_one({"_id": "worker_config"})
    return data.get("session_string") if data else None

async def set_worker_session_db(session_string):
    await settings_col.update_one({"_id": "worker_config"}, {"$set": {"session_string": session_string}}, upsert=True)

async def start_worker():
    global worker_client
    session = await get_worker_session()
    if session:
        try:
            worker_client = Client("worker_session", session_string=session, api_id=int(API_ID), api_hash=API_HASH)
            await worker_client.start()
            logger.info("✅ Worker Session Started!")
        except Exception as e:
            logger.error(f"❌ Worker Error: {e}")
            worker_client = None

async def get_server_api(server_name):
    data = await settings_col.find_one({"_id": "api_keys"})
    return data.get(server_name) if data else None

async def set_server_api(server_name, api_key):
    await settings_col.update_one({"_id": "api_keys"}, {"$set": {server_name: api_key}}, upsert=True)

def generate_short_id(): return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

async def save_post_to_db(post_data, links):
    pid = post_data.get("post_id")
    if not pid:
        pid = generate_short_id()
        post_data["post_id"] = pid
    
    save_data = {"_id": pid, "details": post_data, "links": links, "updated_at": datetime.datetime.now()}
    await posts_col.replace_one({"_id": pid}, save_data, upsert=True)
    return pid

URL_FONT = "https://raw.githubusercontent.com/mahabub81/bangla-fonts/master/Kalpurush.ttf"
URL_MODEL = "https://raw.githubusercontent.com/opencv/opencv/master/data/haarcascades/haarcascade_frontalface_default.xml"

async def fetch_url(url, method="GET", data=None, headers=None, json_data=None):
    async with aiohttp.ClientSession() as session:
        try:
            if method == "GET":
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200: return await resp.json() if "application/json" in resp.headers.get("Content-Type", "") else await resp.read()
            elif method == "POST":
                async with session.post(url, data=data, json=json_data, headers=headers, ssl=False, timeout=15) as resp:
                    return await resp.text()
        except: return None
    return None

# ====================================================================
# 🔥 MULTI-SERVER DUMMY FUNCTIONS (REQUIRED TO PREVENT PLUGIN CRASHES)
# ====================================================================
async def upload_to_gofile(file_path): return None
async def upload_to_fileditch(file_path): return None
async def upload_to_tmpfiles(file_path): return None
async def upload_to_pixeldrain(file_path): return None
async def upload_to_doodstream(file_path): return None
async def upload_to_streamtape(file_path): return None
async def upload_to_filemoon(file_path): return None
async def upload_to_mixdrop(file_path): return None

# ---- FLASK KEEP-ALIVE ----
app = Flask(__name__)

@app.route('/')
def home(): return "🤖 Ultimate SPA Bot Running (With Telegram Direct Forwarding)"

def run_flask(): app.run(host='0.0.0.0', port=8080)

def keep_alive_pinger():
    while True:
        try: requests.get("http://localhost:8080"); time.sleep(600)
        except: time.sleep(600)

def setup_resources():
    if not os.path.exists("kalpurush.ttf"):
        try: open("kalpurush.ttf", "wb").write(requests.get(URL_FONT).content)
        except: pass
    if not os.path.exists("haarcascade_frontalface_default.xml"):
        try: open("haarcascade_frontalface_default.xml", "wb").write(requests.get(URL_MODEL).content)
        except: pass

setup_resources()

def get_font(size=60, bold=False):
    try:
        if os.path.exists("kalpurush.ttf"): return ImageFont.truetype("kalpurush.ttf", size)
        return ImageFont.load_default()
    except: return ImageFont.load_default()

def upload_image_core(file_content):
    try:
        url = "https://catbox.moe/user/api.php"
        response = requests.post(url, data={"reqtype": "fileupload", "userhash": ""}, files={"fileToUpload": ("image.png", file_content, "image/png")}, headers={"User-Agent": "Mozilla/5.0"}, timeout=10, verify=False)
        if response.status_code == 200: return response.text.strip()
    except: pass
    return None

def upload_to_catbox_bytes(img_bytes):
    try:
        if hasattr(img_bytes, 'read'): img_bytes.seek(0); data = img_bytes.read()
        else: data = img_bytes
        return upload_image_core(data)
    except: return None

def upload_to_catbox(file_path):
    try:
        with open(file_path, "rb") as f: return upload_image_core(f.read())
    except: return None

def extract_tmdb_id(text):
    tmdb_match = re.search(r'themoviedb\.org/(movie|tv)/(\d+)', text)
    if tmdb_match: return tmdb_match.group(1), tmdb_match.group(2)
    imdb_id_match = re.search(r'(tt\d{6,})', text)
    if imdb_id_match: return "imdb", imdb_id_match.group(1)
    return None, None

async def search_tmdb(query):
    try:
        match = re.search(r'(.+?)\s*\(?(\d{4})\)?$', query)
        name = match.group(1).strip() if match else query.strip()
        year = match.group(2) if match else None
        url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={name}&include_adult=true"
        if year: url += f"&year={year}"
        data = await fetch_url(url)
        return [r for r in data.get("results", []) if r.get("media_type") in ["movie", "tv"]][:15] if data else []
    except: return []

async def get_tmdb_details(media_type, media_id):
    url = f"https://api.themoviedb.org/3/{media_type}/{media_id}?api_key={TMDB_API_KEY}&append_to_response=credits,similar,images,videos&include_image_language=en,null"
    return await fetch_url(url)

async def create_paste_link(content):
    if not content: return None
    url = "https://dpaste.com/api/"
    link = await fetch_url(url, method="POST", data={"content": content, "syntax": "html", "expiry_days": 14, "title": "Movie Post Code"}, headers={'User-Agent': 'Mozilla/5.0'})
    if link and "dpaste.com" in link: return link.strip()
    return None

def get_smart_badge_position(pil_img):
    try:
        cv_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        if not os.path.exists("haarcascade_frontalface_default.xml"): return int(pil_img.height * 0.40) 
        faces = cv2.CascadeClassifier("haarcascade_frontalface_default.xml").detectMultiScale(gray, 1.1, 4)
        if len(faces) > 0:
            lowest_y = max([y + h for (x, y, w, h) in faces])
            target_y = lowest_y + 40 
            return 80 if target_y > (pil_img.height - 130) else target_y
        return int(pil_img.height * 0.40) 
    except: return 200

def apply_badge_to_poster(poster_bytes, text):
    try:
        base_img = Image.open(io.BytesIO(poster_bytes)).convert("RGBA")
        width, height = base_img.size
        font = get_font(size=70) 
        pos_y = get_smart_badge_position(base_img)
        draw = ImageDraw.Draw(base_img)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        
        padding_x, padding_y = 40, 20
        box_w = text_w + (padding_x * 2)
        box_h = text_h + (padding_y * 2)
        pos_x = (width - box_w) // 2
        
        overlay = Image.new('RGBA', base_img.size, (0, 0, 0, 0))
        ImageDraw.Draw(overlay).rectangle([pos_x, pos_y, pos_x + box_w, pos_y + box_h], fill=(0, 0, 0, 150))
        base_img = Image.alpha_composite(base_img, overlay)
        
        draw = ImageDraw.Draw(base_img)
        cx, cy = pos_x + padding_x, pos_y + padding_y - 12
        words = text.split()
        if len(words) >= 2:
            draw.text((cx, cy), words[0], font=font, fill="#FFEB3B")
            draw.text((cx + draw.textlength(words[0], font=font) + 15, cy), " ".join(words[1:]), font=font, fill="#FF5722")
        else:
            draw.text((cx, cy), text, font=font, fill="#FFEB3B")

        img_buffer = io.BytesIO()
        base_img.save(img_buffer, format="PNG")
        img_buffer.seek(0)
        return img_buffer
    except: return io.BytesIO(poster_bytes)

# ============================================================================
# 🔥 ADVANCED HTML GENERATOR (NEW 2-STEP UI WITH AD-BLOCK DETECT & PUSH)
# ============================================================================
def generate_html_code(data, links, user_ad_links_list, owner_ad_links_list, admin_share_percent=20):
    title = data.get("title") or data.get("name")
    overview = data.get("overview", "No plot available.")
    poster = data.get('manual_poster_url') or f"https://image.tmdb.org/t/p/w500{data.get('poster_path')}"
    BTN_TELEGRAM = "https://i.ibb.co/kVfJvhzS/photo-2025-12-23-12-38-56-7587031987190235140.jpg"

    is_adult = data.get('adult', False) or data.get('force_adult', False)

    theme = data.get("theme", "netflix")
    if theme == "netflix": root_css = "--bg-color: #0f0f13; --box-bg: #1a1a24; --text-main: #ffffff; --text-muted: #d1d1d1; --primary: #E50914; --accent: #00d2ff; --border: #2a2a35; --btn-grad: linear-gradient(90deg, #E50914 0%, #ff5252 100%); --btn-shadow: 0 5px 15px rgba(229, 9, 20, 0.4);"
    elif theme == "prime": root_css = "--bg-color: #0f171e; --box-bg: #1b2530; --text-main: #ffffff; --text-muted: #8197a4; --primary: #00A8E1; --accent: #00A8E1; --border: #2c3e50; --btn-grad: linear-gradient(90deg, #00A8E1 0%, #00d2ff 100%); --btn-shadow: 0 5px 15px rgba(0, 168, 225, 0.4);"
    else: root_css = "--bg-color: #f4f4f9; --box-bg: #ffffff; --text-main: #333333; --text-muted: #555555; --primary: #6200ea; --accent: #6200ea; --border: #dddddd; --btn-grad: linear-gradient(90deg, #6200ea 0%, #b388ff 100%); --btn-shadow: 0 5px 15px rgba(98, 0, 234, 0.4);"

    lang_str = data.get('custom_language', 'Dual Audio').strip()
    if data.get('is_manual'):
        genres_str, year, rating, runtime_str, cast_names = "Custom / Unknown", "N/A", "0.0", "N/A", "N/A"
    else:
        genres_list =[g['name'] for g in data.get('genres',[])]
        genres_str = ", ".join(genres_list) if genres_list else "Movie"
        year = str(data.get("release_date") or data.get("first_air_date") or "----")[:4]
        rating = f"{data.get('vote_average', 0):.1f}"
        runtime = data.get('runtime') or (data.get('episode_run_time',[0])[0] if data.get('episode_run_time') else "N/A")
        runtime_str = f"{runtime} min" if runtime != "N/A" else "N/A"
        cast_list = data.get('credits', {}).get('cast',[])
        cast_names = ", ".join([c['name'] for c in cast_list[:4]]) if cast_list else "Unknown"

    # 🔥 GENERATE SERVER LIST (RGB BUTTONS)
    server_list_html = ""
    if not links:
        server_list_html = '<div style="color: #ff5252; text-align: center; padding: 15px; background: rgba(255,0,0,0.1); border-radius: 8px;">⚠️ দুঃখিত! ডাটাবেসে সেভ না হওয়ায় লিংক তৈরি হয়নি।</div>'
    else:
        grouped_links = {}
        for link in links:
            lbl = link.get('label', 'Download Link')
            if lbl not in grouped_links: grouped_links[lbl] = []
            grouped_links[lbl].append(link)

        for lbl, grp in grouped_links.items():
            server_list_html += f'<div class="quality-title">📺 {lbl}</div>\n<div class="server-grid">\n'
            for link in grp:
                if link.get("is_grouped") and link.get("tg_url"):
                    tg_b64 = base64.b64encode(link['tg_url'].encode('utf-8')).decode('utf-8')
                    server_list_html += f'''
                    <div class="rgb-btn-wrapper">
                        <button class="rgb-btn" onclick="goToLink('{tg_b64}')">
                            <div style="font-size:14px; font-weight:bold; color:var(--text-main); margin-bottom:3px;">⬇️ Download {lbl}</div>
                            <div style="font-size:11px; color:var(--text-muted); text-transform:uppercase; background:rgba(0,0,0,0.5); border-radius:4px; padding:2px 5px; display:inline-block;">Telegram Server</div>
                        </button>
                    </div>'''
                else:
                    url_str = link.get('url', '')
                    if url_str:
                        encoded_url = base64.b64encode(url_str.encode('utf-8')).decode('utf-8')
                        server_list_html += f'''
                        <div class="rgb-btn-wrapper">
                            <button class="rgb-btn" onclick="goToLink('{encoded_url}')">
                                <div style="font-size:14px; font-weight:bold; color:var(--text-main); margin-bottom:3px;">⬇️ Direct Link</div>
                                <div style="font-size:11px; color:var(--text-muted); text-transform:uppercase; background:rgba(0,0,0,0.5); border-radius:4px; padding:2px 5px; display:inline-block;">Direct Server</div>
                            </button>
                        </div>'''
            server_list_html += '</div>\n'

    # 🔥 REVENUE SHARE LOGIC 🔥
    weighted_ad_list =[]
    if not user_ad_links_list: weighted_ad_list = owner_ad_links_list if owner_ad_links_list else["https://google.com"]
    elif not owner_ad_links_list: weighted_ad_list = user_ad_links_list
    else:
        for _ in range(int(admin_share_percent)): weighted_ad_list.append(random.choice(owner_ad_links_list))
        for _ in range(100 - int(admin_share_percent)): weighted_ad_list.append(random.choice(user_ad_links_list))
    random.shuffle(weighted_ad_list) 

    # Clean description for JSON-LD
    clean_desc = overview.replace('"', "'").replace('\n', ' ')

    return f"""
    <!-- Hidden tags for Blogger SEO -->
    <div style="height:0px;width:0px;overflow:hidden;visibility:hidden;display:none;float:left;">
        <img src="{poster}" alt="{title} Thumbnail" />
    </div>
    <div style="display:none;font-size:1px;color:rgba(0,0,0,0);line-height:1px;max-height:0px;max-width:0px;opacity:0;overflow:hidden;">
        🎬 {title} - {clean_desc[:100]}... Download now.
    </div>

    <!-- Schema.org Data -->
    <script type="application/ld+json">
    {{
      "@context": "https://schema.org",
      "@type": "Movie",
      "name": "{title}",
      "image": "{poster}",
      "description": "{clean_desc[:150]}"
    }}
    </script>
    <script type="application/ld+json">
    {{
      "@context": "https://schema.org",
      "@type": "Movie",
      "name": "{title}",
      "image": "{poster}",
      "description": "{clean_desc[:150]}",
      "aggregateRating": {{
        "@type": "AggregateRating",
        "ratingValue": 0,
        "bestRating": "10",
        "ratingCount": "150"
      }}
    }}
    </script>

    <script>
    async function detectAdBlock() {{
      let adBlockEnabled = false;
      const googleAdUrl = 'https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js';
      try {{ await fetch(new Request(googleAdUrl)).catch(_ => adBlockEnabled = true); }} catch (e) {{ adBlockEnabled = true; }}
      if (adBlockEnabled) {{
        document.body.innerHTML = `
        <div style="position:fixed;top:0;left:0;width:100%;height:100%;background:#0f0f13;z-index:99999;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#fff;font-family:sans-serif;text-align:center;padding:20px;">
            <h1 style="color:#ff5252;font-size:50px;">🚫</h1>
            <h2>Ad-Blocker Detected!</h2>
            <p style="color:#aaa;max-width:400px;">আমাদের সার্ভার খরচ চালানোর জন্য বিজ্ঞাপনের প্রয়োজন। দয়া করে আপনার <b>Ad-Blocker</b> বন্ধ করে পেজটি রিফ্রেশ দিন।</p>
            <button onclick="window.location.reload()" style="background:#E50914;color:#fff;border:none;padding:12px 25px;border-radius:5px;cursor:pointer;font-weight:bold;margin-top:20px;font-size:16px;">আমি বন্ধ করেছি, রিফ্রেশ দিন!</button>
        </div>`;
      }}
    }}
    window.onload = function() {{ detectAdBlock(); }};
    </script>

    <link href="https://fonts.googleapis.com/css2?family=Oswald:wght@500&family=Poppins:wght@300;400;600&display=swap" rel="stylesheet">
    <style>
        :root {{ {root_css} }}
        body {{ margin: 0; padding: 0; background: var(--bg-color) !important; background-image: linear-gradient(to bottom, rgba(5,6,10,0.85), var(--bg-color)), url('{poster}') !important; background-attachment: fixed !important; background-size: cover !important; background-position: center !important; font-family: 'Poppins', sans-serif; }}
        
        .app-wrapper {{ max-width: 800px; margin: 20px auto; background: var(--box-bg); border-radius: 17px; padding: 25px; color: var(--text-main); border: 1px solid var(--border); box-shadow: 0 10px 30px rgba(0,0,0,0.9); position: relative; overflow: visible !important; }}
        
        .movie-title {{ font-family: 'Oswald', sans-serif; font-size: 30px; color: var(--text-main); text-align: center; text-transform: uppercase; margin-bottom: 20px; background: linear-gradient(to right, #fff 20%, #777 80%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; letter-spacing: 1px; }}
        
        .info-box {{ display: flex; gap: 20px; margin-bottom: 25px; background: rgba(255,255,255,0.03) !important; border-radius: 20px !important; padding: 25px !important; backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.05) !important; }}
        .info-poster img {{ width: 150px; border-radius: 12px; box-shadow: 0 8px 20px rgba(0,0,0,0.6); border: 2px solid rgba(255,255,255,0.1) !important; transition: 0.5s; }}
        .info-poster img:hover {{ transform: scale(1.05) translateY(-10px); box-shadow: 0 10px 30px rgba(229, 9, 20, 0.4) !important; }}
        
        .info-text {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; width: 100%; }}
        .info-text div {{ background: rgba(0,0,0,0.1); padding: 10px; border-radius: 8px; border-left: 3px solid var(--primary); font-size: 13px; color: var(--text-main); border: 1px solid var(--border); margin-bottom: 8px !important; }}
        .info-text span {{ display: block; color: var(--primary); font-size: 10px; text-transform: uppercase; font-weight: 600; margin-bottom: 3px; letter-spacing: 1px; }}
        
        @media (max-width: 500px) {{ .info-box {{ flex-direction: column; align-items: center; text-align: center; }} .info-poster img {{ width: 140px; }} }}
        
        .section-title {{ font-size: 16px; color: var(--text-main); margin: 25px 0 15px; border-bottom: 2px solid var(--primary); display: inline-block; padding-bottom: 4px; font-weight: 600; text-transform: uppercase; }}
        .plot-box {{ background: rgba(0,0,0,0.1); padding: 15px; border-radius: 8px; font-size: 13px; line-height: 1.7; color: var(--text-muted); border: 1px solid var(--border); text-align: justify; }}
        
        .guide-box {{ background: rgba(0,0,0,0.1); border: 1px dashed var(--primary); padding: 15px; border-radius: 10px; margin-top: 25px; margin-bottom: 20px; }}
        
        .step-container {{ background: rgba(0,0,0,0.2); padding: 25px; border-radius: 12px; text-align: center; border: 1px solid var(--border); position: relative; overflow: hidden; }}
        .step-title {{ color: var(--primary); font-size: 14px; font-weight: 600; letter-spacing: 1px; margin-bottom: 15px; text-transform: uppercase; }}
        .unlock-btn {{ background: var(--primary); color: #fff; border: none; padding: 15px 20px; border-radius: 8px; font-size: 16px; font-weight: bold; cursor: pointer; transition: 0.3s; width: 100%; box-shadow: var(--btn-shadow); }}
        .unlock-btn:disabled {{ background: #555 !important; filter: brightness(0.8); cursor: not-allowed; box-shadow: none; }}
        
        #glow-bar {{ position: absolute; bottom: 0; left: 0; height: 100%; width: 0%; background: rgba(255, 255, 255, 0.2); box-shadow: inset 0 0 20px rgba(255,255,255,0.5); transition: width 5s linear; z-index: 1; }}

        .quality-title {{ background: rgba(0,0,0,0.2); border-left: 4px solid var(--primary); border-radius: 4px; padding: 8px 15px; font-size: 13px; font-weight: 600; color: var(--text-main); margin-top: 25px; text-transform: uppercase; border: 1px solid var(--border); background: linear-gradient(90deg, #E50914, transparent) !important; color: #fff !important; border: none !important; }}
        .server-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin-top: 15px; }} 
        
        .rgb-btn-wrapper {{ position: relative; border-radius: 8px; padding: 2px; background: linear-gradient(45deg, #ff0000, #ff7300, #fffb00, #48ff00, #00ffd5, #002bff, #7a00ff, #ff00c8, #ff0000); background-size: 400%; animation: glowing 20s linear infinite; }}
        .rgb-btn {{ background: #1a1c22 !important; width: 100%; height: 100%; border: none; border-radius: 6px; padding: 15px; cursor: pointer; transition: 0.3s; display: flex; flex-direction: column; align-items: center; justify-content: center; }}
        .rgb-btn:hover {{ background: #E50914 !important; filter: brightness(1.2); transform: translateY(-5px); box-shadow: 0 10px 20px rgba(229, 9, 20, 0.3) !important; }}
        
        @keyframes glowing {{ 0% {{ background-position: 0 0; }} 50% {{ background-position: 400% 0; }} 100% {{ background-position: 0 0; }} }}
        
        .media-badges {{ display: flex; gap: 8px; justify-content: center; margin-bottom: 15px; flex-wrap: wrap; }}
        .badge {{ background: var(--primary); color: #fff; font-size: 11px; padding: 4px 12px; border-radius: 20px; font-weight: 600; text-transform: uppercase; box-shadow: var(--btn-shadow); border: 1px solid rgba(255,255,255,0.2); }}
        .nsfw-blur {{ filter: blur(25px) !important; }}
    </style>

    <div class="app-wrapper">
        <div id="view-details">
            <div class="media-badges">
                <div class="badge">{lang_str}</div>
                <div class="badge">⭐ {rating}/10</div>
                <div class="badge">{year}</div>
                <div class="badge">HEVC</div>
            </div>
            
            <div class="movie-title">{title}</div>
            
            <div class="info-box">
                <div class="info-poster">
                    <img src="{poster}" alt="Poster" class="{'nsfw-blur' if is_adult else ''}">
                </div>
                <div class="info-text">
                    <div><span>⭐ Rating:</span> {rating}/10</div>
                    <div><span>🎭 Genre:</span> {genres_str}</div>
                    <div><span>🗣️ Language:</span> {lang_str}</div>
                    <div><span>⏱️ Runtime:</span> {runtime_str}</div>
                    <div><span>📅 Release:</span> {year}</div>
                    <div><span>👥 Cast:</span> {cast_names}</div>
                </div>
            </div>
            
            <div class="section-title">📖 Storyline</div>
            <div class="plot-box">{overview}</div>

            <div class="guide-box">
                <div style="color:var(--primary); font-weight:bold; font-size:15px; margin-bottom:8px;">🎬 কিভাবে ডাউনলোড করবেন?</div>
                <div style="font-size:13px; color:var(--text-muted); line-height:1.6;">
                    ১. নিচের <b>STEP 1</b> বাটনে ক্লিক করুন এবং ৫ সেকেন্ড অপেক্ষা করুন।<br>
                    ২. এরপর বাটনটি সবুজ হয়ে <b>STEP 2</b> লেখা আসবে, সেখানে ক্লিক করে আবার ৫ সেকেন্ড অপেক্ষা করুন।<br>
                    ৩. ব্যাস! মুভি দেখার এবং ডাউনলোড করার আসল লিংক পেয়ে যাবেন।
                </div>
            </div>

            <div class="step-container" id="step-box">
                <div class="step-title" id="st-txt">STEP 1: VERIFICATION</div>
                <button class="unlock-btn" id="st-btn" onclick="processUnlock()">🔓 UNLOCK LINK (STEP 1)</button>
            </div>
        </div>

        <div id="view-links" style="display:none;">
            <div style="text-align:center; color:#00e676; font-size:15px; font-weight:bold; margin-bottom:25px; border:1px solid rgba(0,230,118,0.3); padding:15px; border-radius:8px; background:rgba(0,230,118,0.05);">✅ ALL LINKS UNLOCKED SUCCESSFULLY!</div>
            
            {server_list_html}
            
            <div style="text-align: center; margin-top: 30px;">
                <a href="https://t.me/koreandrama006" target="_blank">
                    <img src="{BTN_TELEGRAM}" style="width: 100%; max-width: 300px; border-radius: 20px; border: 1px solid var(--border);">
                </a>
            </div>
        </div>
    </div>

    <!-- OneSignal SDK for Push Notifications -->
    <script src="https://cdn.onesignal.com/sdks/web/v16/OneSignalSDK.page.js" defer></script>
    <script>
      window.OneSignalDeferred = window.OneSignalDeferred || [];
      OneSignalDeferred.push(async function(OneSignal) {{
        await OneSignal.init({{
          appId: "d8b008a1-623d-495d-b10d-8def7460f2ea",
        }});
      }});
    </script>

    <script>
    const AD_LINKS = {json.dumps(weighted_ad_list)};
    let currentStep = 1;

    function processUnlock() {{
        let btn = document.getElementById('st-btn');
        let title = document.getElementById('st-txt');
        
        let randomAd = AD_LINKS[Math.floor(Math.random() * AD_LINKS.length)];
        window.open(randomAd, '_blank');
        
        if (currentStep === 1) {{
            btn.disabled = true;
            btn.style.position = 'relative';
            btn.style.overflow = 'hidden';
            btn.innerHTML = `<span style="position:relative; z-index:2;">⏳ Verifying... Please Wait 5s</span><div id="glow-bar"></div>`;
            
            setTimeout(() => {{ let bar = document.getElementById('glow-bar'); if(bar) bar.style.width = '100%'; }}, 50);
            
            setTimeout(() => {{
                currentStep = 2;
                btn.disabled = false;
                btn.style.background = "#00e676";
                btn.style.boxShadow = "0 5px 15px rgba(0, 230, 118, 0.4)";
                btn.innerHTML = "🔓 FINAL UNLOCK (STEP 2)";
                title.innerHTML = "STEP 2: FINAL VERIFICATION";
                title.style.color = "#00e676";
            }}, 5000);
            
        }} else if (currentStep === 2) {{
            btn.disabled = true;
            btn.innerHTML = `<span style="position:relative; z-index:2;">⏳ Finalizing Request...</span><div id="glow-bar"></div>`;
            setTimeout(() => {{ let bar = document.getElementById('glow-bar'); if(bar) bar.style.width = '100%'; }}, 50);
            
            setTimeout(() => {{
                document.getElementById('view-details').style.display = 'none';
                document.getElementById('view-links').style.display = 'block';
                window.scrollTo({{top: 0, behavior: 'smooth'}});
            }}, 5000);
        }}
    }}
    function goToLink(e) {{ window.location.href = atob(e); }}
    </script>
    """

def generate_formatted_caption(data, pid=None):
    title = data.get("title") or data.get("name") or "N/A"
    is_adult = data.get('adult', False) or data.get('force_adult', False)
    
    if data.get('is_manual'): year, rating, genres, language = "Custom", "⭐ N/A", "Custom", "N/A"
    else:
        year = (data.get("release_date") or data.get("first_air_date") or "----")[:4]
        rating = f"⭐ {data.get('vote_average', 0):.1f}/10"
        genres = ", ".join([g["name"] for g in data.get("genres",[])] or["N/A"])
        language = data.get('custom_language', '').title()
    
    overview = data.get("overview", "No plot available.")
    caption = f"🎬 **{title} ({year})**\n"
    if pid: caption += f"🆔 **ID:** `{pid}` (Use to Edit)\n\n"
    if is_adult: caption += "⚠️ **WARNING: 18+ Content.**\n_Suitable for mature audiences only._\n\n"
    if not data.get('is_manual'): caption += f"**🎭 Genres:** {genres}\n**🗣️ Language:** {language}\n**⭐ Rating:** {rating}\n\n"
    caption += f"**📝 Plot:** _{overview[:300]}..._\n\n⚠️ _Disclaimer: Informational post only._"
    return caption

def generate_image(data):
    try:
        poster_url = data.get('manual_poster_url') or (f"https://image.tmdb.org/t/p/w500{data['poster_path']}" if data.get('poster_path') else None)
        if not poster_url: return None, None
            
        poster_bytes = requests.get(poster_url, timeout=10, verify=False).content
        is_adult = data.get('adult', False) or data.get('force_adult', False)
        if data.get('badge_text'): poster_bytes = apply_badge_to_poster(poster_bytes, data['badge_text']).getvalue()

        poster_img = Image.open(io.BytesIO(poster_bytes)).convert("RGBA").resize((400, 600))
        if is_adult: poster_img = poster_img.filter(ImageFilter.GaussianBlur(20))

        bg_img = Image.new('RGBA', (1280, 720), (10, 10, 20))
        backdrop = poster_img.resize((1280, 720))
        if data.get('backdrop_path') and not data.get('is_manual'):
            try: backdrop = Image.open(io.BytesIO(requests.get(f"https://image.tmdb.org/t/p/w1280{data['backdrop_path']}", timeout=10, verify=False).content)).convert("RGBA").resize((1280, 720))
            except: pass
            
        bg_img = Image.alpha_composite(backdrop.filter(ImageFilter.GaussianBlur(10)), Image.new('RGBA', (1280, 720), (0, 0, 0, 150))) 
        bg_img.paste(poster_img, (50, 60), poster_img)
        draw = ImageDraw.Draw(bg_img)
        
        title = data.get("title") or data.get("name")
        year = "" if data.get('is_manual') else (data.get("release_date") or data.get("first_air_date") or "----")[:4]
        draw.text((480, 80), f"{title} {year}", font=get_font(36, True), fill="white", stroke_width=1, stroke_fill="black")
        
        if not data.get('is_manual'):
            draw.text((480, 140), f"⭐ {data.get('vote_average', 0):.1f}/10", font=get_font(24), fill="#00e676")
            if is_adult: draw.text((480, 180), "⚠️ RESTRICTED CONTENT", font=get_font(18), fill="#FF5252")
            else: draw.text((480, 180), " | ".join([g["name"] for g in data.get("genres",[])]), font=get_font(18), fill="#00bcd4")
        
        overview = data.get("overview", "")
        y_text = 250
        for line in [overview[i:i+80] for i in range(0, len(overview), 80)][:6]:
            draw.text((480, y_text), line, font=get_font(24), fill="#E0E0E0")
            y_text += 30
            
        img_buffer = io.BytesIO()
        img_buffer.name = "poster.png"
        bg_img.save(img_buffer, format="PNG")
        img_buffer.seek(0)
        return img_buffer, poster_bytes 
    except: return None, None

try: bot = Client("moviebot", api_id=int(API_ID), api_hash=API_HASH, bot_token=BOT_TOKEN)
except Exception as e: logger.critical(f"Bot Init Error: {e}"); exit(1)

@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    uid = message.from_user.id
    name = message.from_user.first_name
    await add_user(uid, name) 
    
    if len(message.command) > 1:
        payload = message.command[1]
        if payload.startswith("get-"):
            if await is_banned(uid): return await message.reply_text("🚫 **Access Denied:** You are banned.")
            try:
                msg_id = int(payload.split("-")[1])
                temp_msg = await message.reply_text("🔍 **Searching File...**")
                
                post = await posts_col.find_one({"links.tg_url": {"$regex": f"get-{msg_id}"}})
                if not post: post = await posts_col.find_one({"links.url": {"$regex": f"get-{msg_id}"}})
                    
                final_caption = generate_file_caption(post["details"]) if post and "details" in post else f"🎥 **Here is your file!**\n\n🤖 Powered by {client.me.mention}"
                file_msg = await client.copy_message(chat_id=uid, from_chat_id=DB_CHANNEL_ID, message_id=msg_id, caption=final_caption, protect_content=False)
                await temp_msg.delete()

                timer = await get_auto_delete_timer()
                if timer > 0:
                    time_str = f"{timer//60} মিনিট" if timer >= 60 else f"{timer} সেকেন্ড"
                    warning_msg = await message.reply_text(f"⚠️ **সতর্কবার্তা:** কপিরাইট এড়াতে এই ফাইলটি **{time_str}** পর ডিলিট হয়ে যাবে!\n\n📥 দয়া করে এখনই ফাইলটি Save করে রাখুন।", quote=True)
                    asyncio.create_task(auto_delete_task(client, uid,[file_msg.id, warning_msg.id], timer))
                return 
            except Exception as e: return await message.reply_text("❌ **File Not Found!**")

    user_conversations.pop(uid, None)
    if not await is_authorized(uid): return await message.reply_text("⚠️ **অ্যাক্সেস নেই**\n\nএই বটটি ব্যবহার করতে এডমিনের অনুমতির প্রয়োজন।", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💬 Contact Admin", url=f"https://t.me/{OWNER_USERNAME}")]]))

    welcome_text = (
        f"👋 **স্বাগতম {name}!**\n\n"
        "🎬 **Movie & Series Bot (v42 Advanced)**-এ আপনাকে স্বাগতম।\n"
        "📌 **কিভাবে ব্যবহার করবেন?**\n"
        "👉 `/post <নাম>` - অটোমেটিক পোস্ট করতে\n"
        "👉 `/manual` - ম্যানুয়াল পোস্ট করতে\n"
        "👉 `/setapi <server> <key>` - আর্নিং সাইট সেট করতে (Only Admin)\n"
        "👉 `/setadlink <লিংক>` - নিজের অ্যাড লিংক সেট করতে\n"
        "👉 `/mysettings` - নিজের সেটিংস ও লিংক দেখতে\n"
        "👉 `/cancel` - কোনো কাজ বাতিল করতে\n"
        "👉 `/edit <নাম বা ID>` - পোস্ট এডিট করতে"
    )
    await message.reply_text(welcome_text)

@bot.on_message(filters.command("cancel") & filters.private)
async def cancel_cmd(client, message):
    uid = message.from_user.id
    if uid in user_conversations:
        user_conversations.pop(uid, None)
        await message.reply_text("✅ সব চলমান প্রসেস বাতিল করা হয়েছে। নতুন কমান্ড দিন।")
    else: await message.reply_text("⚠️ বাতিল করার মতো কোনো কাজ চলমান নেই।")

@bot.on_message(filters.command("auth") & filters.user(OWNER_ID))
async def auth_user(client, message):
    try: await users_col.update_one({"_id": int(message.command[1])}, {"$set": {"authorized": True, "banned": False}}, upsert=True); await message.reply_text(f"✅ User {message.command[1]} is now AUTHORIZED.")
    except: await message.reply_text("❌ Usage: `/auth 123456789`")

@bot.on_message(filters.command("ban") & filters.user(OWNER_ID))
async def ban_user(client, message):
    try: await users_col.update_one({"_id": int(message.command[1])}, {"$set": {"banned": True}}); await message.reply_text(f"🚫 User {message.command[1]} is now BANNED.")
    except: await message.reply_text("❌ Usage: `/ban 123456789`")

@bot.on_message(filters.command("setownerads") & filters.user(OWNER_ID))
async def set_owner_ads_cmd(client, message):
    if len(message.command) > 1:
        raw_links = message.text.split(None, 1)[1].split()
        valid =[l if l.startswith("http") else "https://" + l for l in raw_links]
        if valid: await set_owner_ads_db(valid); await message.reply_text(f"✅ Owner Ads Updated! ({len(valid)} links)")
        else: await message.reply_text("❌ No valid links found.")
    else: await message.reply_text("⚠️ Usage: `/setownerads link1 link2`")

@bot.on_message(filters.command("setshare") & filters.user(OWNER_ID))
async def set_share_cmd(client, message):
    try:
        percent = int(message.command[1])
        if 0 <= percent <= 100: await set_admin_share_db(percent); await message.reply_text(f"✅ Share Updated: Admin **{percent}%**")
    except: await message.reply_text("⚠️ Usage: `/setshare 20`")

@bot.on_message(filters.command("setdel") & filters.user(OWNER_ID))
async def set_auto_delete_cmd(client, message):
    try: await set_auto_delete_timer_db(int(message.command[1])); await message.reply_text(f"✅ Timer Updated: **{message.command[1]} seconds**")
    except: await message.reply_text("⚠️ Usage: `/setdel 600`")

@bot.on_message(filters.command("broadcast") & filters.user(OWNER_ID))
async def broadcast_msg(client, message):
    if not message.reply_to_message: return await message.reply_text("⚠️ Reply to a message.")
    msg = await message.reply_text("⏳ Broadcasting...")
    count = 0
    async for user in users_col.find({}):
        try: await message.reply_to_message.copy(user["_id"]); count += 1; await asyncio.sleep(0.1) 
        except: pass
    await msg.edit_text(f"✅ Broadcast Sent to **{count}** users.")

@bot.on_message(filters.command("setapi") & filters.user(OWNER_ID))
async def set_api_command(client, message):
    try:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3: return await message.reply_text("⚠️ **Format:** `/setapi <server_name> <api_key>`\n**Supported Servers:** `doodstream`, `streamtape`, `filemoon`, `mixdrop`\nFor Streamtape & MixDrop use format: `email:api_key`")
        server_name, api_key = parts[1].lower(), parts[2].strip()
        if server_name not in["doodstream", "streamtape", "filemoon", "mixdrop"]: return await message.reply_text("❌ Unsupported server.")
        await set_server_api(server_name, api_key)
        await message.reply_text(f"✅ **{server_name.title()}** API Key Saved successfully!")
    except Exception as e: await message.reply_text(f"❌ Error: {e}")

@bot.on_message(filters.command("setworker") & filters.user(OWNER_ID))
async def set_worker_cmd(client, message):
    global worker_client
    if len(message.command) < 2: return await message.reply_text("⚠️ **Format:** `/setworker SESSION_STRING`")
    session_string = message.text.split(None, 1)[1]
    await set_worker_session_db(session_string)
    await message.reply_text("⏳ সেশন সেভ হয়েছে, ওয়ার্কার রিস্টার্ট হচ্ছে...")
    if worker_client:
        try: await worker_client.stop()
        except: pass
    try:
        worker_client = Client("worker_session", session_string=session_string, api_id=int(API_ID), api_hash=API_HASH)
        await worker_client.start()
        await message.reply_text("✅ **Worker Session** সফলভাবে কানেক্ট হয়েছে!")
    except Exception as e: await message.reply_text(f"❌ কানেকশন ফেইলড: {e}")

@bot.on_message(filters.command("workerinfo") & filters.user(OWNER_ID))
async def worker_info(client, message):
    if worker_client and worker_client.is_connected:
        me = await worker_client.get_me()
        await message.reply_text(f"🤖 **Worker Status:** Active\n👤 **Name:** {me.first_name}\n🆔 **ID:** `{me.id}`")
    else: await message.reply_text("❌ Worker Session কানেক্টেড নেই।")

@bot.on_message(filters.command("stats") & filters.user(OWNER_ID))
async def bot_stats(client, message):
    total, total_posts, admin_share = await get_all_users_count(), await posts_col.count_documents({}), await get_admin_share()
    await message.reply_text(f"📊 **BOT STATS**\n👥 Users: {total}\n📁 Posts: {total_posts}\n💰 Admin Share: {admin_share}%")

@bot.on_message(filters.command("mysettings") & filters.private)
async def my_settings_cmd(client, message):
    uid = message.from_user.id
    if not await is_authorized(uid): return await message.reply_text("🚫 **অ্যাক্সেস নেই**")
    user_ads = await get_user_ads(uid)
    ads_text = "\n".join([f"🔗 {ad}" for ad in user_ads]) if user_ads else "❌ কোনো লিংক সেট করা নেই। (Owner Ads ব্যবহার হচ্ছে)"
    await message.reply_text(f"⚙️ **Your Settings**\n\n👤 **Name:** {message.from_user.first_name}\n🆔 **ID:** `{uid}`\n\n📢 **Your Ad Links:**\n{ads_text}\n\n💡 _Use /setadlink to update your ads._", disable_web_page_preview=True)

@bot.on_message(filters.command("setadlink") & filters.private)
async def set_ad(client, message):
    uid = message.from_user.id
    if not await is_authorized(uid): return
    if len(message.command) > 1:
        raw_links = message.text.split(None, 1)[1].split()
        valid_links =[l if l.startswith("http") else "https://" + l for l in raw_links]
        if valid_links: await save_user_ads(uid, valid_links); await message.reply_text("✅ Ad Links Saved!")
    else: await message.reply_text("⚠️ Usage: `/setadlink site.com`")

@bot.on_message(filters.command("manual") & filters.private)
async def manual_post_cmd(client, message):
    uid = message.from_user.id
    if not await is_authorized(uid): return
    user_conversations[uid] = {"details": {"is_manual": True, "manual_screenshots":[]}, "links":[], "state": "manual_title"}
    await message.reply_text("✍️ **Manual Post Started**\n\nপ্রথমে **টাইটেল (Title)** লিখুন:\n_(যেকোনো মুহূর্তে বাতিল করতে /cancel কমান্ড দিন)_")

@bot.on_message(filters.command("history") & filters.private)
async def history_cmd(client, message):
    uid = message.from_user.id
    if not await is_authorized(uid): return
    posts = await posts_col.find({}).sort("updated_at", -1).limit(10).to_list(10)
    if not posts: return await message.reply_text("❌ No history found.")
    text = "📜 **Last 10 Posts:**\n\n"
    for p in posts: text += f"🎬 {p['details'].get('title', 'Unknown')} (ID: `{p['_id']}`)\n"
    await message.reply_text(text)

@bot.on_message(filters.command("edit") & filters.private)
async def edit_post_cmd(client, message):
    uid = message.from_user.id
    if not await is_authorized(uid): return
    if len(message.command) < 2: return await message.reply_text("⚠️ Usage: `/edit <Name OR ID>`")
    
    query = message.text.split(" ", 1)[1].strip()
    msg = await message.reply_text("🔍 Searching...")
    post = await posts_col.find_one({"_id": query})
    if not post:
        results = await posts_col.find({"details.title": {"$regex": query, "$options": "i"}}).to_list(10)
        if not results: results = await posts_col.find({"details.name": {"$regex": query, "$options": "i"}}).to_list(10)
        if not results: return await msg.edit_text("❌ Not found.")
        if len(results) > 1:
            btns = [[InlineKeyboardButton(f"{r['details'].get('title')} ({r['_id']})", callback_data=f"forcedit_{r['_id']}_{uid}")] for r in results]
            return await msg.edit_text("👇 **Select Post:**", reply_markup=InlineKeyboardMarkup(btns))
        post = results[0] 
        
    await msg.delete() 
    await start_edit_session(uid, post, message)

async def start_edit_session(uid, post, message):
    user_conversations[uid] = {"details": post["details"], "links": post.get("links",[]), "state": "edit_mode", "post_id": post["_id"]}
    btns = [[InlineKeyboardButton("➕ Add New Link", callback_data=f"add_lnk_edit_{uid}")],[InlineKeyboardButton("✅ Generate New Code", callback_data=f"gen_edit_{uid}")]]
    txt = f"📝 **Editing:** {post['details'].get('title')}\n🆔 `{post['_id']}`\n\n👇 **What to do?**"
    if isinstance(message, Message): await message.reply_text(txt, reply_markup=InlineKeyboardMarkup(btns))
    else: await message.edit_text(txt, reply_markup=InlineKeyboardMarkup(btns))

@bot.on_callback_query(filters.regex("^forcedit_"))
async def force_edit_cb(client, cb):
    try: _, pid, uid = cb.data.split("_"); post = await posts_col.find_one({"_id": pid})
    except: return
    if post: await start_edit_session(int(uid), post, cb.message)

@bot.on_message(filters.command("post") & filters.private)
async def post_cmd(client, message):
    uid = message.from_user.id
    if not await is_authorized(uid): return
    if len(message.command) < 2: return await message.reply_text("⚠️ Usage:\n`/post Avatar`")
    
    query = message.text.split(" ", 1)[1].strip()
    msg = await message.reply_text(f"🔎 Processing `{query}`...")
    m_type, m_id = extract_tmdb_id(query)

    if m_type and m_id:
        if m_type == "imdb":
            data = await fetch_url(f"https://api.themoviedb.org/3/find/{m_id}?api_key={TMDB_API_KEY}&external_source=imdb_id")
            res = data.get("movie_results",[]) + data.get("tv_results",[])
            if res: m_type, m_id = res[0]['media_type'], res[0]['id']
            else: return await msg.edit_text("❌ IMDb ID not found.")
                
        details = await get_tmdb_details(m_type, m_id)
        if not details: return await msg.edit_text("❌ Details not found.")
        user_conversations[uid] = { "details": details, "links":[], "state": "wait_lang" }
        return await msg.edit_text(f"✅ Found: **{details.get('title') or details.get('name')}**\n\n🗣️ Enter **Language** (e.g. Hindi):")

    results = await search_tmdb(query)
    if not results: return await msg.edit_text("❌ No results found.")
    buttons = [[InlineKeyboardButton(f"{r.get('title') or r.get('name')} ({str(r.get('release_date','----'))[:4]})", callback_data=f"sel_{r['media_type']}_{r['id']}")] for r in results]
    await msg.edit_text("👇 **Select Content:**", reply_markup=InlineKeyboardMarkup(buttons))

@bot.on_callback_query(filters.regex("^sel_"))
async def on_select(client, cb):
    try:
        _, m_type, m_id = cb.data.split("_")
        details = await get_tmdb_details(m_type, m_id)
        if not details: return await cb.message.edit_text("❌ Details not found.")
        user_conversations[cb.from_user.id] = { "details": details, "links":[], "state": "wait_lang" }
        await cb.message.edit_text(f"✅ Selected: **{details.get('title') or details.get('name')}**\n\n🗣️ Enter **Language**:")
    except: pass

# 🔥 BACKGROUND ASYNC UPLOAD (WITH PROPER ERROR HANDLING)
async def process_file_upload(client, message, uid, temp_name):
    convo = user_conversations.get(uid)
    if not convo: return
    
    convo["pending_uploads"] = convo.get("pending_uploads", 0) + 1
    status_msg = await message.reply_text(f"🕒 **সারির অপেক্ষায়...**\n({temp_name})", quote=True)
    
    try:
        async with upload_semaphore:
            await status_msg.edit_text(f"⏳ **টেলিগ্রাম ডাটাবেসে সেভ হচ্ছে...**")
            copied_msg = await message.copy(chat_id=DB_CHANNEL_ID)
            
            bot_username = client.me.username if client.me else (await client.get_me()).username
            tg_link = f"https://t.me/{bot_username}?start=get-{copied_msg.id}"
            convo["links"].append({
                "label": temp_name, "tg_url": tg_link, "gofile_url": None, "fileditch_url": None, "tmpfiles_url": None, "pixel_url": None, "dood_url": None, "stape_url": None, "filemoon_url": None, "mixdrop_url": None, "is_grouped": True
            })
            await status_msg.edit_text(f"✅ **আপলোড সম্পন্ন:** {temp_name}")
            
    except Exception as e:
        logger.error(f"Upload Error: {e}")
        error_text = f"❌ **আপলোড ফেইল হয়েছে!**\nকারণ: `{e}`\n\n⚠️ **দয়া করে চেক করুন বটকে তোমার ডাটাবেস চ্যানেল ({DB_CHANNEL_ID}) এ Admin করা হয়েছে কিনা।**"
        await status_msg.edit_text(error_text)
    finally:
        convo["pending_uploads"] = max(0, convo.get("pending_uploads", 0) - 1)

@bot.on_message(filters.private & (filters.text | filters.video | filters.document | filters.photo) & ~filters.command(["start", "post", "cancel"]))
async def text_handler(client, message):
    uid = message.from_user.id
    if uid not in user_conversations: return
    
    convo = user_conversations[uid]
    state = convo.get("state")
    text = message.text.strip() if message.text else ""

    if state == "wait_lang":
        convo["details"]["custom_language"] = text
        convo["state"] = "wait_quality"
        await message.reply_text("💿 Enter **Quality**:")
        
    elif state == "wait_quality":
        convo["details"]["custom_quality"] = text
        convo["state"] = "ask_links"
        await message.reply_text("🔗 Add Download Links?", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ Add Links", callback_data=f"lnk_yes_{uid}"), InlineKeyboardButton("🏁 Finish", callback_data=f"lnk_no_{uid}")]]))
        
    elif state == "wait_link_name_custom":
        convo["temp_name"] = text
        convo["state"] = "wait_link_url"
        await message.reply_text(f"✅ নাম সেট: **{text}**\n\n🔗 এবার **URL** দিন অথবা **ভিডিও ফাইলটি** ফরোয়ার্ড করুন:")
        
    elif state == "wait_link_url":
        if message.video or message.document:
            asyncio.create_task(process_file_upload(client, message, uid, convo["temp_name"]))
            convo["state"] = "ask_links"
            await message.reply_text("✅ আপলোড সারিতে যোগ হয়েছে!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ Add Another", callback_data=f"lnk_yes_{uid}"), InlineKeyboardButton("🏁 Finish", callback_data=f"lnk_no_{uid}")]]))

        elif text.startswith("http"):
            convo["links"].append({"label": convo["temp_name"], "url": text, "is_grouped": False, "gofile_url": None, "fileditch_url": None, "tmpfiles_url": None, "pixel_url": None, "dood_url": None, "stape_url": None, "filemoon_url": None, "mixdrop_url": None})
            convo["state"] = "ask_links"
            await message.reply_text(f"✅ Saved!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ Add Another", callback_data=f"lnk_yes_{uid}"), InlineKeyboardButton("🏁 Finish", callback_data=f"lnk_no_{uid}")]]))
        else:
            await message.reply_text("⚠️ Invalid Input. URL or File required.")

    elif state == "wait_batch_files":
        if text.lower() == "/done":
            convo["state"] = "ask_links"
            await message.reply_text("✅ **Batch Accepted!**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏁 Finish", callback_data=f"lnk_no_{uid}")]]))
        elif message.video or message.document:
            file_name = getattr(message.video, "file_name", None) or getattr(message.document, "file_name", None) or f"Episode {len(convo.get('links',[]))+1}"
            asyncio.create_task(process_file_upload(client, message, uid, file_name))

    elif state == "wait_badge_text":
        convo["details"]["badge_text"] = text
        await message.reply_text("🛡️ **Safety Check:**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Safe", callback_data=f"safe_yes_{uid}"), InlineKeyboardButton("🔞 18+", callback_data=f"safe_no_{uid}")]]))

@bot.on_callback_query(filters.regex("^lnk_"))
async def link_cb(client, cb):
    uid = int(cb.data.rsplit("_", 1)[1])
    if cb.data.startswith("lnk_yes"):
        user_conversations[uid]["state"] = "wait_link_name"
        btns = [[InlineKeyboardButton("🎬 1080p", callback_data=f"setlname_1080p_{uid}"), InlineKeyboardButton("🎬 720p", callback_data=f"setlname_720p_{uid}")],[InlineKeyboardButton("✍️ Custom", callback_data=f"setlname_custom_{uid}"), InlineKeyboardButton("📁 Default", callback_data=f"setlname_telegram_{uid}")],[InlineKeyboardButton("📦 Batch Upload", callback_data=f"setlname_batch_{uid}")]]
        await cb.message.edit_text("👇 বাটনের ধরন সিলেক্ট করুন:", reply_markup=InlineKeyboardMarkup(btns))
    else:
        if user_conversations.get(uid, {}).get("pending_uploads", 0) > 0:
            return await cb.answer("⏳ ফাইল আপলোড শেষ হওয়া পর্যন্ত অপেক্ষা করুন...", show_alert=True)
        user_conversations[uid]["state"] = "wait_badge_text"
        await cb.message.edit_text("🖼️ **Badge Text?**\nলিখে পাঠান অথবা Skip করুন:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🚫 Skip", callback_data=f"skip_badge_{uid}")]]))

@bot.on_callback_query(filters.regex("^setlname_"))
async def set_lname_cb(client, cb):
    _, action, uid = cb.data.split("_")
    uid = int(uid)
    if action in["1080p", "720p", "480p"]:
        user_conversations[uid]["temp_name"] = action; user_conversations[uid]["state"] = "wait_link_url"
        await cb.message.edit_text(f"✅ Set: **{action}**\n🔗 **URL** বা **ফাইল** দিন:")
    elif action == "custom":
        user_conversations[uid]["state"] = "wait_link_name_custom"
        await cb.message.edit_text("📝 বাটনের নাম লিখুন:")
    elif action == "batch":
        user_conversations[uid]["state"] = "wait_batch_files"
        await cb.message.edit_text("📦 **Batch Mode:** সব ফাইল ফরোয়ার্ড করুন। শেষে `/done` লিখুন।")
    else:
        user_conversations[uid]["temp_name"] = "Telegram Files"; user_conversations[uid]["state"] = "wait_link_url"
        await cb.message.edit_text("✅ বাটন সেট। 🔗 **URL** বা **ফাইল** দিন:")

@bot.on_callback_query(filters.regex("^skip_badge_"))
async def skip_badge_cb(client, cb):
    uid = int(cb.data.split("_")[-1])
    if uid in user_conversations:
        user_conversations[uid]["details"]["badge_text"] = None
        await cb.message.edit_text("🛡️ **Safety Check:**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Safe", callback_data=f"safe_yes_{uid}"), InlineKeyboardButton("🔞 18+", callback_data=f"safe_no_{uid}")]]))

@bot.on_callback_query(filters.regex("^safe_"))
async def safety_cb(client, cb):
    action, uid = cb.data.rsplit("_", 1)
    user_conversations[int(uid)]["details"]["force_adult"] = (action == "safe_no")
    btns = [[InlineKeyboardButton("🔴 Netflix (Dark)", callback_data=f"theme_netflix_{uid}")],[InlineKeyboardButton("🔵 Prime (Blue)", callback_data=f"theme_prime_{uid}")],[InlineKeyboardButton("⚪ Anime (Light)", callback_data=f"theme_light_{uid}")]]
    await cb.message.edit_text("🎨 **ওয়েবসাইটের থিম (Theme):**", reply_markup=InlineKeyboardMarkup(btns))

@bot.on_callback_query(filters.regex("^theme_"))
async def theme_cb(client, cb):
    _, theme_name, uid = cb.data.split("_")
    uid = int(uid)
    user_conversations[uid]["details"]["theme"] = theme_name
    await generate_final_post(client, uid, cb.message)

async def generate_final_post(client, uid, message):
    convo = user_conversations.get(uid)
    if not convo: return await message.edit_text("❌ Session expired.")
    status_msg = await message.edit_text("⏳ **Generating Final Post...**")

    try:
        pid = await save_post_to_db(convo["details"], convo["links"])
        loop = asyncio.get_running_loop()
        img_io, poster_bytes = await loop.run_in_executor(None, generate_image, convo["details"])

        if convo["details"].get("badge_text") and poster_bytes:
            new_poster = await loop.run_in_executor(None, upload_to_catbox_bytes, poster_bytes)
            if new_poster: convo["details"]["manual_poster_url"] = new_poster 
        
        html = generate_html_code(convo["details"], convo["links"], await get_user_ads(uid), await get_owner_ads(), await get_admin_share())
        caption = generate_formatted_caption(convo["details"], pid)
        convo["final"] = {"html": html}
        
        btns = [[InlineKeyboardButton("📄 Get Blogger Code", callback_data=f"get_code_{uid}")]]
        if img_io: await client.send_photo(message.chat.id, img_io, caption=caption, reply_markup=InlineKeyboardMarkup(btns))
        else: await client.send_message(message.chat.id, caption, reply_markup=InlineKeyboardMarkup(btns))
        await status_msg.delete()
    except Exception as e: await status_msg.edit_text(f"❌ **Error:** `{e}`")

@bot.on_callback_query(filters.regex("^get_code_"))
async def get_code(client, cb):
    uid = int(cb.data.rsplit("_", 1)[1])
    data = user_conversations.get(uid)
    if not data or "final" not in data: return await cb.answer("Expired.", show_alert=True)
    await cb.answer("⏳ Generating Code...", show_alert=False)
    link = await create_paste_link(data["final"]["html"])
    
    if link: await cb.message.reply_text(f"✅ **Code Ready!**\n\n👇 Copy:\n{link}", disable_web_page_preview=True)
    else:
        file = io.BytesIO(data["final"]["html"].encode())
        file.name = "post.html"
        await client.send_document(cb.message.chat.id, file, caption="⚠️ Link failed. Download File.")

# --- PLUGIN LOADER ---
async def load_plugins():
    plugins_path = os.path.join(os.path.dirname(__file__), "plugins")
    if not os.path.exists(plugins_path): return
    for loader, module_name, is_pkg in pkgutil.iter_modules([plugins_path]):
        try:
            module = importlib.import_module(f"plugins.{module_name}")
            if hasattr(module, "register"): await module.register(bot)
        except Exception as e: logger.error(f"Failed to load {module_name}: {e}")

# --- MAIN ---
async def main():
    await bot.start()
    await load_plugins()
    await start_worker() 
    print("✅ Bot is Online with Tele-Only Uploads & Custom UI!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    Thread(target=keep_alive_pinger, daemon=True).start()
    asyncio.get_event_loop().run_until_complete(main())
