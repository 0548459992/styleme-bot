import os
import time
import feedparser
from google import genai
from supabase import create_client
import urllib.parse
from datetime import datetime, timedelta
import random
import requests

# --- הגדרות מערכת ---
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

# אתחול הלקוחות
client_ai = genai.Client(api_key=GEMINI_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# הגדרות ריצה
MAX_ITEMS_PER_RUN = 20 
RUN_INTERVAL_MINUTES = 29

# --- מקורות RSS ישירים (מגזינים מובילים) ---
DIRECT_FEEDS = [
    "https://www.businessoffashion.com/feeds/rss/",
    "https://www.voguebusiness.com/feed",
    "https://wwd.com/feed/",
    "https://www.fashionunited.com/rss-feed",
    "https://www.textileworld.com/feed/",
    "https://www.apparelresources.com/feed/",
    "https://www.fashionnetwork.com/rss/feed.xml"
]

# --- רשימת נושאים רחבה (ללא שמות מותגים) ---
ALL_TOPICS = [
    "Fashion Design Innovation 2026", "Haute Couture Industry Trends", 
    "Sustainable Textile Technology", "Fabric Material Science News", 
    "Global Fashion Market Analysis", "Future of Sportswear Design",
    "Digital Fashion Trends Metaverse", "3D Printing in Apparel", 
    "Smart Fabrics and Wearables", "Circular Fashion Economy", 
    "Automated Garment Manufacturing", "Eco-friendly Dyeing Innovation",
    "Fashion Week Industry Highlights", "Global Textile Trade Shows", 
    "Apparel Retail Market Forecast", "Luxury Design Trends", 
    "Supply Chain Transparency Fashion", "New Textile Fiber Innovation",
    "Textile Recycling Advances", "Fashion Design Awards Winners"
]

def get_with_ua(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=20)
        return response.content
    except Exception as e:
        print(f"      ⚠️ Network error for {url[:30]}: {e}")
        return None

def analyze_item(item, collected_intel):
    if any(c['title'] == item.title for c in collected_intel): return
    
    try:
        existing = supabase.table('news').select("id").eq('title', item.title).execute()
        if existing.data: return
    except: pass

    print(f"   ✨ Analyzing: {item.title[:50]}...")
    time.sleep(3) 

    prompt = f"""
    Act as a senior fashion and textile industry analyst. Analyze this news title: {item.title}
    1. Summarize in HEBREW (2-3 sentences, professional and executive tone). 
       Focus on trends, design, technology, or market shifts.
    2. Categorize exactly as one of: 'TRENDS', 'MARKET', 'TECH', 'LOGISTICS', 'REGULATION'.
    Format:
    Category: [CATEGORY]
    Summary: [HEBREW TEXT]
    """
    
    try:
        # שימוש בספריה החדשה של גוגל
        res = client_ai.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        text = res.text
        
        category = "TRENDS"
        content = text
        if "Category:" in text:
            parts = text.split("Summary:")
            if len(parts) > 1:
                category = parts[0].replace("Category:", "").strip()
                content = parts[1].strip()
            else:
                content = text.replace("Category:", "").replace("Summary:", "")

        collected_intel.append({
            "title": item.title,
            "content": content.replace("**", "").strip(),
            "category": category.upper(),
            "source_url": item.link,
            "likes": 0,
            "is_public": True
        })
        print(f"      ✅ Added to queue.")
    except Exception as e:
        print(f"      ❌ AI Analysis Error: {e}")

def run_bot():
    print(f"🚀 StyleMe PRO: Mega-Bot Started at {datetime.now()}")
    collected_intel = []

    # שלב 1: סריקת מגזינים ישירה
    print("--- Phase 1: Magazine RSS Feeds ---")
    for feed_url in DIRECT_FEEDS:
        if len(collected_intel) >= MAX_ITEMS_PER_RUN: break
        print(f"📡 Fetching: {feed_url}")
        content = get_with_ua(feed_url)
        if content:
            feed = feedparser.parse(content)
            for item in feed.entries[:5]:
                if len(collected_intel) >= MAX_ITEMS_PER_RUN: break
                analyze_item(item, collected_intel)

    # שלב 2: סריקת גוגל ניוז
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

    # שלב 3: הפצה לדאטה-בייס
    if not collected_intel:
        print("🛑 No new items found to publish.")
        return

    print(f"--- Phase 3: Publishing {len(collected_intel)} items ---")
    interval = RUN_INTERVAL_MINUTES / len(collected_intel) if len(collected_intel) > 1 else 1
    base_time = datetime.utcnow() - timedelta(minutes=2)

    for i, news in enumerate(collected_intel):
        news['created_at'] = (base_time + timedelta(minutes=i*interval)).isoformat()
        try:
            supabase.table('news').insert(news).execute()
            print(f"   ✅ Published: {news['title'][:40]}")
        except Exception as e:
            print(f"   ❌ DB Insert Error: {e}")

if __name__ == "__main__":
    run_bot()
