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
MAX_ITEMS_PER_RUN = 15 
RUN_INTERVAL_MINUTES = 30 

# רשימת נושאים ממוקדת - עיצוב, ביזנס וטכנולוגיה
SPECIFIC_TOPICS = [
    "Fashion Design Trends 2026",
    "Haute Couture News",
    "Sustainable Fashion Innovation",
    "Textile Material Science News",
    "Global Fashion Market Analysis",
    "Sneaker Culture Trends",
    "Fashion Week Runway Reports",
    "Luxury Brand Business Strategies",
    "Digital Fashion Metaverse",
    "Eco-friendly Fabric Technology",
    "Apparel Supply Chain Logistics"
]

# רשימת נושאים כלליים לחיפוש רחב (למקרה שהספציפיים נכשלים)
BROAD_TOPICS = [
    "Fashion Industry News",
    "Textile Industry Updates",
    "Style and Design Trends",
    "Global Apparel Market"
]

def get_google_news_url(query, days=None):
    encoded = urllib.parse.quote(query)
    # אם לא הוגדרו ימים, מביא את הכי רלוונטי ללא הגבלת זמן חמורה
    if days:
        return f"https://news.google.com/rss/search?q={encoded}+when:{days}d&hl=en-US&gl=US&ceid=US:en"
    else:
        return f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"

def analyze_and_add(item, collected_intel):
    if len(collected_intel) >= MAX_ITEMS_PER_RUN: return

    # בדיקת כפילות מול מה שכבר אספנו בריצה זו
    if any(c['title'] == item.title for c in collected_intel): 
        print(f"   Skipping duplicate in batch: {item.title[:20]}...")
        return

    # בדיקת כפילות מול הדאטה בייס (האם כבר פורסם?)
    try:
        existing = supabase.table('news').select("id").eq('title', item.title).execute()
        if existing.data and len(existing.data) > 0: 
            print(f"   Skipping existing DB item: {item.title[:20]}...")
            return 
    except: 
        return

    print(f"   ⚡ Match Found: {item.title[:50]}...")
    time.sleep(2) # השהייה קצרה

    prompt = f"""
    Act as a fashion industry expert.
    Analyze this news: {item.title} ({item.link})
    
    Task:
    1. Summarize in HEBREW (2 sentences). Focus on the essence (Design/Business/Tech).
    2. Categorize: 'TRENDS', 'LOGISTICS', 'MARKET', 'TECH', 'REGULATION', 'DESIGN'.
    
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
        print(f"   📥 Added! Total: {len(collected_intel)}")
        
    except Exception as e:
        print(f"   ⚠️ AI Error: {e}")
        time.sleep(2)

def run_bot():
    print(f"🚀 StyleMe PRO: Guaranteed Search Started at {datetime.now()}")
    
    scan_queue = SPECIFIC_TOPICS.copy()
    random.shuffle(scan_queue)
    
    collected_intel = [] 
    
    # --- שלב 1: חיפוש ממוקד (7 ימים) ---
    print("--- Phase 1: Specific Topics (7 Days) ---")
    for topic in scan_queue:
        if len(collected_intel) >= MAX_ITEMS_PER_RUN: break
        
        url = get_google_news_url(topic, days=7)
        print(f"🔎 Scanning: {topic}...")
        
        try:
            feed = feedparser.parse(url)
            # לוקחים רק את 3 הראשונים מכל נושא כדי לגוון
            for item in feed.entries[:3]: 
                if len(collected_intel) >= MAX_ITEMS_PER_RUN: break
                analyze_and_add(item, collected_intel)
        except: continue

    # --- שלב 2: רשת ביטחון (חיפוש כללי ללא הגבלת זמן) ---
    # אם לא מצאנו מספיק (פחות מ-5), עוברים לחיפוש רחב
    if len(collected_intel) < 5:
        print(f"⚠️ Only found {len(collected_intel)} items. Engaging BROAD SEARCH...")
        
        for broad in BROAD_TOPICS:
            if len(collected_intel) >= MAX_ITEMS_PER_RUN: break
            
            # שים לב: כאן אין days=7. זה יביא את החדשות הכי רלוונטיות בכל זמן.
            url = get_google_news_url(broad) 
            print(f"🌍 Broad Scanning: {broad}...")
            
            try:
                feed = feedparser.parse(url)
                # בחיפוש רחב לוקחים יותר (עד 10)
                for item in feed.entries[:10]:
                    if len(collected_intel) >= MAX_ITEMS_PER_RUN: break
                    analyze_and_add(item, collected_intel)
            except: continue

    # --- שלב 3: הפצה ---
    total_items = len(collected_intel)
    
    if total_items == 0:
        print("❌ CRITICAL: No items found even after broad search.")
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
