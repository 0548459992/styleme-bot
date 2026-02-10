import os
import time
import feedparser
import google.generativeai as genai
from supabase import create_client
import urllib.parse
from datetime import datetime, timedelta
import random
import requests

# --- הגדרות מערכת ---
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

genai.configure(api_key=GEMINI_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# מקסימום ידיעות לריצה - העליתי ל-25 כדי שיהיה עשיר
MAX_ITEMS_PER_RUN = 25 
RUN_INTERVAL_MINUTES = 30 

# --- רשימת מקורות RSS ישירים (מגזינים מובילים) ---
DIRECT_FEEDS = [
    "https://www.businessoffashion.com/feeds/rss/",
    "https://www.voguebusiness.com/feed",
    "https://wwd.com/feed/",
    "https://www.fashionunited.com/rss-feed",
    "https://www.textileworld.com/feed/",
    "https://www.apparelresources.com/feed/",
    "https://www.fashionnetwork.com/rss/feed.xml"
]

# --- רשימת נושאים רחבה לחיפוש בגוגל (גיבוי) ---
ALL_TOPICS = [
    "Fashion Design Innovation 2026", "Haute Couture Trends", "Sustainable Fabrics Tech",
    "Textile Raw Materials Price", "Global Logistics Fashion", "Runway Fashion Analysis",
    "Digital Fashion NFT Metaverse", "3D Printing Textiles", "Smart Fabrics Wearables",
    "Circular Fashion Economy", "Apparel Manufacturing Robots", "Eco-friendly Dyeing Tech",
    "Fashion Week Global Highlights", "Textile Trade Shows 2026", "Apparel Market Forecast",
    "Luxury Retail Trends", "Supply Chain Transparency Fashion", "Garment Labor Standards",
    "Bio-engineered Silk Spider Silk", "Recycled Polyester Market", "Cotton Farming Tech"
]

def get_with_ua(url):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    try:
        response = requests.get(url, headers=headers, timeout=20)
        return response.content
    except: return None

def analyze_item(item, collected_intel):
    if any(c['title'] == item.title for c in collected_intel): return
    
    # בדיקת כפילות ב-DB
    try:
        existing = supabase.table('news').select("id").eq('title', item.title).execute()
        if existing.data: return
    except: pass

    print(f"   ✨ Analyzing: {item.title[:50]}...")
    time.sleep(3) # מנוחה קצרה ל-API החינמי

    prompt = f"""
    Act as a senior fashion analyst. Analyze this news: {item.title}
    1. Summarize in HEBREW (2-3 sentences, executive and professional tone).
    2. Categorize as: 'TRENDS', 'MARKET', 'TECH', 'LOGISTICS', or 'REGULATION'.
    Format:
    Category: [CATEGORY]
    Summary: [HEBREW TEXT]
    """
    
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        res = model.generate_content(prompt)
        text = res.text
        
        category = "TRENDS"
        content = text
        if "Category:" in text:
            parts = text.split("Summary:")
            if len(parts) > 1:
                category = parts[0].replace("Category:", "").strip()
                content = parts[1].strip()

        collected_intel.append({
            "title": item.title,
            "content": content.replace("**", "").strip(),
            "category": category,
            "source_url": item.link,
            "likes": 0,
            "is_public": True
        })
    except Exception as e:
        print(f"      AI Error: {e}")

def run_bot():
    print(f"🚀 StyleMe PRO Mega-Bot Started at {datetime.now()}")
    collected_intel = []

    # --- חלק 1: סריקת מגזינים ישירה ---
    print("--- Phase 1: Magazine RSS Feeds ---")
    for feed_url in DIRECT_FEEDS:
        if len(collected_intel) >= MAX_ITEMS_PER_RUN: break
        content = get_with_ua(feed_url)
        if content:
            feed = feedparser.parse(content)
            for item in feed.entries[:5]: # 5 מכל מגזין
                if len(collected_intel) >= MAX_ITEMS_PER_RUN: break
                analyze_item(item, collected_intel)

    # --- חלק 2: סריקת גוגל ניוז לפי נושאים ---
    print("--- Phase 2: Google News Deep Scan ---")
    random.shuffle(ALL_TOPICS)
    for topic in ALL_TOPICS:
        if len(collected_intel) >= MAX_ITEMS_PER_RUN: break
        encoded = urllib.parse.quote(topic)
        url = f"https://news.google.com/rss/search?q={encoded}+when:7d&hl=en-US&gl=US&ceid=US:en"
        content = get_with_ua(url)
        if content:
            feed = feedparser.parse(content)
            for item in feed.entries[:3]:
                if len(collected_intel) >= MAX_ITEMS_PER_RUN: break
                analyze_item(item, collected_intel)

    # --- שלב 3: הפצה ---
    if not collected_intel:
        print("🛑 No news found. System on standby.")
        return

    print(f"--- Phase 3: Publishing {len(collected_intel)} items ---")
    interval = RUN_INTERVAL_MINUTES / len(collected_intel) if len(collected_intel) > 1 else 1
    base_time = datetime.utcnow() - timedelta(minutes=2)

    for i, news in enumerate(collected_intel):
        news['created_at'] = (base_time + timedelta(minutes=i*interval)).isoformat()
        try:
            supabase.table('news').insert(news).execute()
            print(f"✅ Published: {news['title'][:40]}")
        except Exception as e: print(f"❌ DB Error: {e}")

if __name__ == "__main__":
    run_bot()
