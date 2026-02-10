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

# --- הגדרות הפצה ---
MAX_ITEMS_PER_RUN = 20 
RUN_INTERVAL_MINUTES = 30 

# --- רשימת נושאים כלליים (ללא מותגים) ---
# הרשימה מכסה את כל שרשרת הערך: מעיצוב ועד לוגיסטיקה
ALL_TOPICS = [
    # --- TRENDS & FORECASTS (תחזיות וטרנדים) ---
    "Global Fashion Trend Forecasting 2026",
    "Textile Color Trends Spring Summer",
    "Fabric Material Trends Autumn Winter",
    "Future of Denim Trends Analysis",
    "Sustainable Fashion Consumer Trends",
    "Streetwear Market Trends Global",
    "Luxury Apparel Market Analysis",
    "Menswear Fashion Market Trends",
    "Womenswear Design Trends Forecast",
    "Footwear Industry Design Trends",

    # --- EXHIBITIONS & EVENTS (תערוכות ותחרויות) ---
    "Global Textile Trade Shows News",
    "Fashion Week Industry Highlights",
    "Première Vision Textile News", # תערוכת בדים מרכזית (זה אירוע, לא מותג אופנה)
    "Pitti Uomo Industry News",
    "Techtextil Exhibition Updates",
    "Emerging Fashion Designer Competitions",
    "Global Fashion Awards Winners",
    "Textile Innovation Awards News",
    "Fashion Design Contest Results",

    # --- TECHNOLOGY & INNOVATION (טכנולוגיה) ---
    "AI in Fashion Design and Manufacturing",
    "3D Knitting Technology Innovations",
    "Digital Fashion and Metaverse News",
    "Smart Fabrics and Wearable Tech",
    "Biodegradable Textiles Innovations",
    "Textile Recycling Technology Advances",
    "Automated Garment Manufacturing Robots",
    "Blockchain in Fashion Supply Chain",
    "On-Demand Clothing Production Tech",

    # --- BUSINESS & SUPPLY CHAIN (עסקים ולוגיסטיקה) ---
    "Global Apparel Supply Chain Issues",
    "Textile Raw Material Price Trends",
    "Cotton Market Global Prices",
    "Synthetic Fibers Market Analysis",
    "Garment Manufacturing in Vietnam",
    "Textile Industry in Bangladesh News",
    "Fashion Retail Logistics Challenges",
    "Global Shipping Freight Rates Textiles",
    "Apparel Import Export Regulations",
    "EU Strategy for Sustainable Textiles",

    # --- GENERAL INDUSTRY (כללי) ---
    "Fashion Industry Sustainability Report",
    "Textile Manufacturing Market Size",
    "Global Apparel Consumption Data",
    "Circular Fashion Economy News",
    "Ethical Fashion Labor Standards"
]

def get_google_news_url(query):
    encoded = urllib.parse.quote(query)
    # חיפוש עד 7 ימים אחורה כדי להבטיח תוצאות
    return f"https://news.google.com/rss/search?q={encoded}+when:7d&hl=en-US&gl=US&ceid=US:en"

def analyze_and_add(item, collected_intel):
    print(f"   ⚡ Match Found: {item.title[:40]}...")
    time.sleep(2) 

    # ההנחיה ל-AI עודכנה כדי להתמקד בהיבט המקצועי/תעשייתי
    prompt = f"""
    Act as a senior business analyst for the fashion & textile industry.
    Analyze this news: {item.title} ({item.link})
    
    Task:
    1. Summarize in HEBREW (2-3 sentences). Focus on the *industry impact*, *innovation*, or *market shift*.
    2. Categorize exactly as: 'LOGISTICS', 'MARKET', 'TECH', 'REGULATION', 'TRENDS'.
    
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

def run_bot():
    print(f"🚀 StyleMe PRO: General Industry Scanner Started at {datetime.now()}")
    
    scan_queue = ALL_TOPICS.copy()
    random.shuffle(scan_queue)
    
    collected_intel = [] 
    
    print("--- Phase 1: Harvesting Intel ---")
    
    for topic in scan_queue:
        if len(collected_intel) >= MAX_ITEMS_PER_RUN:
            print("🛑 Max items limit reached.")
            break
            
        url = get_google_news_url(topic)
        print(f"🔎 Scanning Topic: {topic}...")
        
        try:
            feed = feedparser.parse(url)
            if not feed.entries: 
                print("   No entries found.")
                continue
            
            found_new_for_topic = False
            
            # סורק את כל הפיד של אותו נושא
            for item in feed.entries: 
                if found_new_for_topic: break 

                # בדיקת כפילות בזיכרון
                if any(c['title'] == item.title for c in collected_intel): continue 

                # בדיקת כפילות בדאטה בייס
                try:
                    existing = supabase.table('news').select("id").eq('title', item.title).execute()
                    if existing.data and len(existing.data) > 0: continue 
                except: continue

                # מצאנו ידיעה חדשה
                analyze_and_add(item, collected_intel)
                found_new_for_topic = True 
            
        except Exception as e:
            print(f"   ❌ Error: {e}")

    # --- רשת ביטחון: חיפוש כללי מאוד אם לא מצאנו כלום ---
    if len(collected_intel) < 2:
        print("⚠️ Low intel count. Running General Fashion Scan...")
        # חיפוש רחב מאוד אך ללא שמות מותגים
        emergency_topics = ["Fashion Industry News", "Textile Industry Updates", "Apparel Market Analysis"]
        
        for em_topic in emergency_topics:
            if len(collected_intel) >= 5: break
            try:
                url = get_google_news_url(em_topic)
                feed = feedparser.parse(url)
                for item in feed.entries[:5]:
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
        print("😴 No new intel found in this run.")
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
