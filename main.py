import os
import time
import feedparser
from google import genai # הספרייה החדשה
from supabase import create_client
import urllib.parse
from datetime import datetime, timedelta
import random
import requests

# --- הגדרות מערכת ---
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

# אתחול הלקוח החדש של גוגל
client_ai = genai.Client(api_key=GEMINI_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ... (שאר הקוד נשאר דומה, רק הפונקציה של הניתוח משתנה) ...

def analyze_item(item, collected_intel):
    if any(c['title'] == item.title for c in collected_intel): return
    try:
        existing = supabase.table('news').select("id").eq('title', item.title).execute()
        if existing.data: return
    except: pass

    print(f"   ✨ Analyzing: {item.title[:50]}...")
    time.sleep(2) 

    prompt = f"""
    Act as a senior fashion analyst. Analyze this news: {item.title}
    1. Summarize in HEBREW (2-3 sentences, executive and professional tone).
    2. Categorize as: 'TRENDS', 'MARKET', 'TECH', 'LOGISTICS', or 'REGULATION'.
    Format:
    Category: [CATEGORY]
    Summary: [HEBREW TEXT]
    """
    
    try:
        # שימוש במודל החדש והיציב
        res = client_ai.models.generate_content(
            model="gemini-2.0-flash", # שדרוג לגרסה הכי חדישה ומהירה
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

        collected_intel.append({
            "title": item.title,
            "content": content.replace("**", "").strip(),
            "category": category,
            "source_url": item.link,
            "likes": 0,
            "is_public": True
        })
        print(f"      ✅ Success!")
    except Exception as e:
        print(f"      ❌ AI Error: {e}")

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
