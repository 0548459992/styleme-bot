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
MAX_ITEMS_PER_RUN = 25 # כמות יפה לריצה
RUN_INTERVAL_MINUTES = 30 # הפצה על פני חצי שעה

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
    # שינוי: מבקש עד 3 ימים אחורה כדי לוודא שיש "בשר" גם אם לא היו חדשות בשעה האחרונה
    return f"https://news.google.com/rss/search?q={encoded}+when:3d&hl=en-US&gl=US&ceid=US:en"

def run_bot():
    print(f"🚀 StyleMe Pulse Bulldozer Started at {datetime.now()}")
    
    # שלב א': איסוף הידיעות (Harvesting Phase)
    # -----------------------------------------
    scan_queue = ALL_TOPICS.copy()
    random.shuffle(scan_queue)
    
    collected_intel = [] 
    
    print("--- Phase 1: Deep Harvesting ---")
    
    for topic in scan_queue:
        # בדיקה גלובלית - אם מילאנו את המכסה, עוצרים הכל
        if len(collected_intel) >= MAX_ITEMS_PER_RUN:
            print("🛑 Max items limit reached for this run.")
            break
            
        url = get_google_news_url(topic)
        print(f"🔎 Scanning Topic: {topic}...")
        
        try:
            feed = feedparser.parse(url)
            if not feed.entries: 
                print("   No entries found for topic.")
                continue
            
            found_new_for_topic = False
            
            # --- השינוי הגדול: לולאה ללא הגבלה ---
            # עוברים על כל מה שגוגל נתן (יכול להיות גם 50 כתבות)
            # עד שמוצאים אחת שלא פורסמה
            for i, item in enumerate(feed.entries): 
                if found_new_for_topic: break 

                # 1. בדיקת כפילות בתוך הריצה הנוכחית
                is_duplicate_in_batch = False
                for collected in collected_intel:
                    if collected['title'] == item.title:
                        is_duplicate_in_batch = True
                        break
                
                if is_duplicate_in_batch:
                    continue 

                # 2. בדיקת כפילות מול ההיסטוריה בדאטה בייס
                try:
                    existing = supabase.table('news').select("id").eq('title', item.title).execute()
                    if existing.data and len(existing.data) > 0:
                        # אם קיים - ממשיכים מיד לכתבה הבאה ברשימה
                        # לא מדפיסים כלום כדי לא ללכלך את הלוג
                        continue 
                except Exception as e:
                    print(f"   ⚠️ DB Error: {e}")
                    continue

                # --- מצאנו זהב! ---
                print(f"   ⚡ Match Found (at depth {i}): {item.title[:40]}...")
                time.sleep(2) # השהייה קלה למניעת חסימה

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
                
                # ניקוי הטקסט שה-AI מחזיר
                if "Category:" in text:
                    parts = text.split("Summary:")
                    if len(parts) > 1:
                        category = parts[0].replace("Category:", "").strip()
                        content = parts[1].strip()
                    else:
                        content = text.replace("Category:", "").replace("Summary:", "")
                
                # מנקים כוכביות או סימנים מיותרים
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
                found_new_for_topic = True 
            
            if not found_new_for_topic:
                print(f"   😓 Scanned {len(feed.entries)} items but all were duplicates.")

        except Exception as e:
            print(f"   ❌ Error scanning topic: {e}")
            time.sleep(1)

    # שלב ב': תזמון חכם והפצה
    # ------------------------------------------------
    total_items = len(collected_intel)
    
    if total_items == 0:
        print("😴 No new intel found in this run.")
        return

    print(f"--- Phase 2: Distributing {total_items} items over {RUN_INTERVAL_MINUTES} minutes ---")
    
    interval_minutes = 0
    if total_items > 1:
        interval_minutes = RUN_INTERVAL_MINUTES / total_items
    
    # לוקחים זמן עכשיו פחות דקה
    base_time = datetime.utcnow() - timedelta(minutes=1)
    
    for i, news_item in enumerate(collected_intel):
        delay = i * interval_minutes
        publish_time = base_time + timedelta(minutes=delay)
        
        news_item['created_at'] = publish_time.isoformat()
        
        try:
            supabase.table('news').insert(news_item).execute()
            print(f"   ✅ Scheduled: {publish_time.strftime('%H:%M:%S')} (+{delay:.1f}m)")
        except Exception as e:
            print(f"   ❌ DB Error: {e}")

    print(f"✨ Session Complete. {total_items} items queued.")

if __name__ == "__main__":
    run_bot()
