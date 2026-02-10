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

# --- הגדרות בטיחות (Safe Mode) ---
# 12 ידיעות לריצה = כ-500 ידיעות ביום (בטוח מאוד בחבילה החינמית)
MAX_ITEMS_PER_RUN = 12 
RUN_INTERVAL_MINUTES = 30 

# --- רשימת נושאים: שילוב של ביזנס + עיצוב וקריאייטיב ---
ALL_TOPICS = [
    # === DESIGN & CREATIVITY (החלק החדש) ===
    "Fashion Design Trends 2026",
    "Haute Couture Industry News",
    "Textile Design Innovation",
    "Runway Fashion Analysis",
    "Sustainable Design Techniques Fashion",
    "Color Trends Fashion Forecast",
    "Avant-Garde Fashion News",
    "Fashion Illustration and Art Trends",
    "Emerging Fashion Designers News",
    "Conceptual Fashion Trends",
    "Digital Fashion Design Metaverse",
    "Fabric Manipulation Techniques",
    
    # === BUSINESS & MARKET ===
    "Global Fashion Retail Market",
    "Luxury Fashion Market Trends",
    "Streetwear Market Analysis",
    "Sportswear Industry News",
    "Fashion Supply Chain Updates",
    "Textile Raw Material Prices",
    
    # === TECH & INNOVATION ===
    "AI in Fashion Design",
    "3D Printing in Fashion",
    "Smart Fabrics Technology",
    "Sustainable Textile Materials",
    
    # === EVENTS ===
    "Fashion Week Highlights Global",
    "Textile Trade Shows News",
    "Fashion Design Awards"
]

def get_google_news_url(query):
    encoded = urllib.parse.quote(query)
    # חזרנו ל-7 ימים כדי להבטיח שיש תוצאות גם בנושאי נישה
    return f"https://news.google.com/rss/search?q={encoded}+when:7d&hl=en-US&gl=US&ceid=US:en"

def analyze_and_add(item, collected_intel):
    # הגנה מפני חריגה
    if len(collected_intel) >= MAX_ITEMS_PER_RUN: return

    print(f"   ⚡ Match Found: {item.title[:40]}...")
    time.sleep(3) # השהייה בטוחה

    # הנחיה ל-AI להתמקד גם בעיצוב ובאסתטיקה
    prompt = f"""
    Act as a fashion industry expert.
    Analyze this news: {item.title} ({item.link})
    
    Task:
    1. Summarize in HEBREW (2 sentences). If it's about design, focus on aesthetics/materials. If business, focus on impact.
    2. Categorize: 'TRENDS' (for design/style), 'LOGISTICS', 'MARKET', 'TECH', 'REGULATION'.
    
    Format:
    Category: [CATEGORY]
    Summary: [HEBREW TEXT]
    """
    
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        res = model.generate_content(prompt)
        
        text = res.text
        category = "TRENDS" # ברירת מחדל לנושאי עיצוב
        content = text
        
        if "Category:" in text:
            parts = text.split("Summary:")
            if len(parts) > 1:
                category = parts[0].replace("Category:", "").strip()
                content = parts[1].strip()
            else:
                content = text.replace("Category:", "").replace("Summary:", "")
        
        content = content.replace("**", "").replace("*", "").strip()

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
        print(f"   ⚠️ AI Error: {e}")
        time.sleep(5)

def run_bot():
    print(f"🚀 StyleMe PRO: Design & Business Scanner Started at {datetime.now()}")
    
    scan_queue = ALL_TOPICS.copy()
    random.shuffle(scan_queue)
    
    collected_intel = [] 
    
    print("--- Phase 1: Harvesting Intel ---")
    
    for topic in scan_queue:
        if len(collected_intel) >= MAX_ITEMS_PER_RUN:
            print("🛑 Max safe limit reached.")
            break
            
        url = get_google_news_url(topic)
        print(f"🔎 Scanning: {topic}...")
        
        try:
            feed = feedparser.parse(url)
            if not feed.entries: 
                print("   No entries.")
                continue
            
            found_new_for_topic = False
            
            # סורקים עד שמוצאים ידיעה חדשה אחת לנושא
            for item in feed.entries: 
                if found_new_for_topic: break 
                if len(collected_intel) >= MAX_ITEMS_PER_RUN: break

                # בדיקת כפילות
                if any(c['title'] == item.title for c in collected_intel): continue 
                try:
                    existing = supabase.table('news').select("id").eq('title', item.title).execute()
                    if existing.data and len(existing.data) > 0: continue 
                except: continue

                analyze_and_add(item, collected_intel)
                found_new_for_topic = True 
            
        except Exception as e:
            print(f"   ❌ Error: {e}")

    # --- רשת ביטחון: אם לא מצאנו מספיק, מחפשים כללי ---
    if len(collected_intel) < 3:
        print("⚠️ Low intel count. Running BROAD Creative Scan...")
        # חיפוש רחב מאוד שיביא תוצאות בוודאות
        broad_topics = ["Fashion Design News", "Global Fashion Trends", "Textile Industry News"]
        
        for topic in broad_topics:
            if len(collected_intel) >= MAX_ITEMS_PER_RUN: break
            try:
                url = get_google_news_url(topic)
                feed = feedparser.parse(url)
                for item in feed.entries[:5]: # בודקים את ה-5 הראשונים
                    if len(collected_intel) >= MAX_ITEMS_PER_RUN: break
                    if any(c['title'] == item.title for c in collected_intel): continue
                    try:
                        existing = supabase.table('news').select("id").eq('title', item.title).execute()
                        if existing.data: continue
                    except: continue
                    
                    analyze_and_add(item, collected_intel)
            except: continue

    # שלב ב': תזמון
    total_items = len(collected_intel)
    
    if total_items == 0:
        print("😴 No new intel found (Checked specific + broad topics).")
        return

    print(f"--- Phase 2: Distributing {total_items} items ---")
    
    interval_minutes = 0
    if total_items > 1:
        interval_minutes = RUN_INTERVAL_MINUTES / total_items
    
    base_time = datetime.utcnow() - timedelta(minutes=1)
    
    for i, news_item in enumerate(collected_intel):
        delay = i * interval_minutes
        publish_time = base_time + timedelta(minutes=delay)
        news_item['created_at'] = publish_time.isoformat()
        
        try:
            supabase.table('news').insert(news_item).execute()
            print(f"   ✅ Scheduled: {publish_time.strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"   ❌ DB Error: {e}")

if __name__ == "__main__":
    run_bot()
