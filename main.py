import sys
import time
import os
import json
import random
import re
import urllib.parse
import feedparser
import requests
from datetime import datetime, timedelta
from supabase import create_client
from google import genai
from google.genai import types

# --- בדיקת משתני סביבה ---
try:
    SUPABASE_URL = os.environ["SUPABASE_URL"]
    SUPABASE_KEY = os.environ["SUPABASE_KEY"]
    GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
except KeyError as e:
    print(f"❌ CRITICAL ERROR: Missing Secret Key: {e}")
    sys.exit(1)

# אתחול קליינטים
try:
    client_ai = genai.Client(api_key=GEMINI_API_KEY)
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"❌ Connection Error: {e}")
    sys.exit(1)

# --- הגדרות תוכן ---
LANG_CODES = ["he", "en", "it", "fr", "es", "de", "jp"]

DIRECT_FEEDS = [
    "https://www.businessoffashion.com/feeds/rss/",
    "https://www.voguebusiness.com/feed",
    "https://wwd.com/feed/",
    "https://www.fashionunited.com/rss-feed",
    "https://www.fashionnetwork.com/rss/feed.xml"
]

ALL_TOPICS = [
    "Avant-Garde Fashion Design Trends", "Sustainable Couture Techniques", 
    "Runway Color Forecast 2026", "Womenswear Silhouette Innovation",
    "Footwear Sculpture & Design", "Luxury Bridal Market Trends",
    "Experimental Accessories Design", "Streetwear Subculture Research",
    "Textile Pattern Design Trends", "Gender-Neutral Fashion Design",
    "Smart Fabrics & Electronic Textiles", "Biodegradable Synthetic Fibers",
    "Recycled Ocean Plastic Textiles", "Mycelium & Mushroom Leather",
    "Carbon Fiber Apparel Applications", "Waterless Dyeing Technology",
    "Denim Indigo Weaving Innovations", "Digital Inkjet Textile Printing",
    "Generative AI in Apparel Design", "3D Body Modeling & Fit Tech",
    "Virtual Try-On UX Innovation", "Metaverse Luxury Collections",
    "Blockchain for Luxury Authentication", "NFT Fashion Assets Regulation",
    "Digital Product Passports Textiles", "Big Data in Fashion Retail",
    "Artificial Intelligence Style Curators", "Fashion E-commerce Algorithm Trends",
    "Predictive Analytics for Fashion Trends", "Global Fashion Retail Growth 2026",
    "Luxury Sector Financial Outlook", "Apparel Supply Chain Resilience",
    "Resale & Circular Economy Growth", "Clothing Rental Subscription Models",
    "Direct-to-Consumer Strategy News", "Luxury Market in Southeast Asia",
    "Post-Fast Fashion Business Models", "EU EPR Legislation for Textiles",
    "Fashion Carbon Footprint Metrics", "Regenerative Cotton Farming News",
    "Zero-Waste Pattern Making Tech", "Fashion Intellectual Property Law",
    "Global Fashion Week Highlights", "Iconic Designer Retrospectives"
]

def extract_json_smart(text):
    """מחלץ JSON נקי ומסנן רעשי רקע"""
    try:
        return json.loads(text)
    except:
        try:
            start = text.find('{')
            end = text.rfind('}') + 1
            if start != -1 and end != -1:
                return json.loads(text[start:end])
            return None
        except: return None

def analyze_turtle_mode(item_title):
    """ניתוח במצב צב - איטי ובטוח"""
    prompt = f"""
    Act as a Fashion Editor. Analyze this news title: "{item_title}".
    Return a JSON object ONLY with:
    1. "category": One specific fashion category.
    2. "titles": Translated title in {LANG_CODES}.
    3. "summaries": A 2-sentence summary in {LANG_CODES}.
    Return JSON only.
    """
    
    model = "gemini-2.0-flash"
    
    try:
        print(f"🐢 Analyzing (Slowly)...")
        response = client_ai.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        return extract_json_smart(response.text)
            
    except Exception as e:
        # טיפול בשגיאות עומס
        err_msg = str(e).lower()
        if "429" in err_msg or "quota" in err_msg:
            print("🛑 Quota hit! Sleeping 120s (2 mins)...")
            time.sleep(120) 
            return None # מוותרים הפעם, ננסה בריצה הבאה
        else:
            print(f"⚠️ Error: {e}")
            return None

def run_archive_and_cleanup():
    print("🧹 Maintenance...")
    try:
        now = datetime.utcnow()
        # מחיקת טיוטות ישנות
        limit = (now - timedelta(hours=12)).isoformat()
        supabase.table('news').delete().eq('needs_full_translation', True).lt('created_at', limit).execute()
    except: pass

def run_bot():
    print(f"🚀 StyleMe TURTLE Engine Active 🐢")
    run_archive_and_cleanup()

    tasks = []
    # לוקחים דגימות קטנות מאוד
    rss_samples = random.sample(DIRECT_FEEDS, 3) 
    for f in rss_samples: tasks.append((f, "RSS"))
        
    topic_samples = random.sample(ALL_TOPICS, 3)
    for t in topic_samples: tasks.append((t, "TOPIC"))
        
    random.shuffle(tasks)
    
    # --- המגבלה הקריטית ---
    # רק 3 כתבות לכל הפעלה של הבוט!
    MAX_ARTICLES_PER_RUN = 3
    items_published = 0

    for source, s_type in tasks:
        if items_published >= MAX_ARTICLES_PER_RUN: 
            print("🛑 Batch limit reached. Bye!")
            break 
        
        url = source if s_type == "RSS" else f"https://news.google.com/rss/search?q={urllib.parse.quote(source)}&hl=en-US&gl=US&ceid=US:en"
        
        try:
            print(f"📥 Fetching source...")
            resp = requests.get(url, timeout=10)
            feed = feedparser.parse(resp.content)
            
            # רק כתבה אחת ממקור זה
            for entry in feed.entries[:1]:
                if items_published >= MAX_ARTICLES_PER_RUN: break
                
                exists = supabase.table('news').select("id").eq('source_url', entry.link).execute()
                if exists.data:
                    print("🔹 Exists.")
                    continue

                ai_data = analyze_turtle_mode(entry.title)
                
                if ai_data:
                    item = {
                        "source_url": entry.link,
                        "category": ai_data.get('category', 'General'),
                        "titles": ai_data.get('titles', {}),
                        "summaries": ai_data.get('summaries', {}),
                        "needs_full_translation": False,
                        "is_public": True,
                        "created_at": datetime.utcnow().isoformat()
                    }
                    supabase.table('news').insert(item).execute()
                    print(f"✅ Published: {entry.title[:20]}...")
                    items_published += 1
                    
                    # --- ההפסקה הגדולה ---
                    # דקה שלמה של מנוחה בין הצלחות
                    print("💤 Cooling down for 60s...")
                    time.sleep(60) 
                
        except Exception:
            continue

if __name__ == "__main__":
    run_bot()
