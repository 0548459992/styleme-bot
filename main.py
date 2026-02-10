import os
import time
import feedparser
import google.generativeai as genai
from supabase import create_client
import urllib.parse
from datetime import datetime, timedelta
import random

# --- הגדרות מערכת ---
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

genai.configure(api_key=GEMINI_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- הגדרות הפצה חכמה ---
# מקסימום ידיעות לאיסוף בריצה אחת (כדי לא להעמיס על ה-API והקוראים)
# 30 ידיעות ב-30 דקות = ידיעה כל דקה. זה קצב אש מטורף.
MAX_ITEMS_PER_RUN = 30 
RUN_INTERVAL_MINUTES = 29 # משאירים דקה ספייר לביטחון

ALL_TOPICS = [
    "Global Cotton Market Prices Trends",
    "Textile Raw Material Shortage News",
    "Synthetic Fibers Market Analysis",
    "Global Shipping Freight Rates Textile Industry",
    "Fashion Supply Chain Disruption News",
    "Apparel Manufacturing Hubs Vietnam Bangladesh Turkey",
    "On-Demand Fashion Manufacturing Market",
    "Textile Industry Automation AI Robotics",
    "Digital Fashion & 3D Knitting Technology",
    "Micro-Factory Fashion Manufacturing Trends",
    "EU Strategy for Sustainable Textiles",
    "Fashion Industry Carbon Footprint Regulations",
    "Textile Recycling Technology Innovation",
    "Digital Product Passport Textiles EU",
    "Fast Fashion Supply Chain Strategy Analysis",
    "Ultra Fast Fashion Environmental Impact Market",
    "Global Apparel Market Economic Outlook",
    "Luxury Fashion Market Economics",
    "Textile Import Export Tariffs Trade War",
    "Gen Z Fashion Consumer Behavior",
    "Smart Fabrics Wearables Technology",
    "Virtual Fitting Room Technology Market",
    "Fashion Industry Business News",
    "Global Textile Market Trends"
]

def get_google_news_url(query):
    encoded = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={encoded}+when:1d&hl=en-US&gl=US&ceid=US:en"

def run_bot():
    print(f"🚀 StyleMe Pulse Engine Started at {datetime.now()}")
    
    # שלב א': איסוף הידיעות (Harvesting Phase)
    # -----------------------------------------
    scan_queue = ALL_TOPICS.copy()
    random.shuffle(scan_queue)
    
    collected_intel = [] # רשימה זמנית בזיכרון
    
    print("--- Phase 1: harvesting Intel ---")
    
    for topic in scan_queue:
        # אם הגענו למכסה המקסימלית לריצה זו - עוצרים את האיסוף
        if len(collected_intel) >= MAX_ITEMS_PER_RUN:
            print("🛑 Max items limit reached for this run.")
            break
            
        url = get_google_news_url(topic)
        print(f"🔎 Scanning: {topic}...")
        
        try:
            feed = feedparser.parse(url)
            if not feed.entries: continue
            
            item = feed.entries[0]

            # בדיקה האם הידיעה כבר קיימת בדאטה בייס או ברשימה הנוכחית
            # (כדי לא לאסוף פעמיים את אותה כתבה מנושאים שונים)
            is_duplicate = False
            for collected in collected_intel:
                if collected['title'] == item.title:
                    is_duplicate = True
                    break
            
            if is_duplicate:
                print("   Skipping duplicate in batch.")
                continue

            existing = supabase.table('news').select("id").eq('title', item.title).execute()
            if existing.data:
                print(f"   Skipping existing in DB.")
                continue

            print(f"   ⚡ Match Found! Analyzing with AI...")
            time.sleep(2) # השהייה טכנית

            # ניתוח AI
            prompt = f"""
            Act as a senior business analyst for the fashion & textile industry.
            Analyze this news: {item.title} ({item.link})
            1. Summarize in HEBREW (2-3 sentences, executive tone, interesting).
            2. Categorize: 'LOGISTICS', 'MARKET', 'TECH', 'REGULATION', 'TRENDS'.
            Format:
            Category: [CATEGORY]
            Summary: [HEBREW TEXT]
            """
            
            try:
                model = genai.GenerativeModel('gemini-1.5-flash')
                res = model.generate_content(prompt)
            except:
                model = genai.GenerativeModel('gemini-pro')
                res = model.generate_content(prompt)

            text = res.text
            category = "GLOBAL"
            content = text
            if "Category:" in text:
                parts = text.split("Summary:")
                category = parts[0].replace("Category:", "").strip()
                content = parts[1].strip()

            # הוספה לרשימה הזמנית (עדיין לא שומרים לדאטה בייס!)
            collected_intel.append({
                "title": item.title,
                "content": content,
                "category": category,
                "source_url": item.link,
                "likes": 0,
                "is_public": True
            })
            print(f"   📥 Added to queue. Total: {len(collected_intel)}")
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
            time.sleep(1)

    # שלב ב': תזמון חכם והפצה (Smart Scheduling Phase)
    # ------------------------------------------------
    total_items = len(collected_intel)
    
    if total_items == 0:
        print("😴 No new intel found in this run.")
        return

    print(f"--- Phase 2: Distributing {total_items} items over {RUN_INTERVAL_MINUTES} minutes ---")
    
    # חישוב המרווח בדקות בין כל ידיעה
    # אם יש 10 ידיעות ו-30 דקות -> המרווח הוא 3 דקות.
    # אם יש ידיעה אחת -> המרווח הוא 0 (פרסום מיידי).
    interval_minutes = 0
    if total_items > 1:
        interval_minutes = RUN_INTERVAL_MINUTES / total_items
    
    base_time = datetime.utcnow()
    
    for i, news_item in enumerate(collected_intel):
        # חישוב זמן הפרסום המדויק לידיעה הזו
        delay = i * interval_minutes
        publish_time = base_time + timedelta(minutes=delay)
        
        # הוספת זמן הפרסום לאובייקט
        news_item['created_at'] = publish_time.isoformat()
        
        # שמירה לדאטה בייס
        try:
            supabase.table('news').insert(news_item).execute()
            print(f"   ✅ Scheduled item {i+1}/{total_items} for {publish_time.strftime('%H:%M:%S')} (Delay: {delay:.1f}m)")
        except Exception as e:
            print(f"   ❌ DB Error: {e}")

    print(f"✨ Session Complete. {total_items} items queued for drip feed.")

if __name__ == "__main__":
    run_bot()
