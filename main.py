import os
import time
import feedparser
import google.generativeai as genai
from supabase import create_client
import urllib.parse
from datetime import datetime

# קריאת המפתחות מהסביבה המאובטחת של גיטהאב
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

# הגדרות
genai.configure(api_key=GEMINI_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- רשימת נושאים מורחבת (ניצול מקסימלי של החינם) ---
TOPICS = [
    "Textile Supply Chain",           # ליבה
    "Cotton Prices Market",           # חומרי גלם
    "Fashion Technology Innovation",  # טכנולוגיה
    "Sustainable Fashion EU Laws",    # רגולציה
    "Textile Manufacturing Automation", # אוטומציה
    "Zara H&M Supply Chain",          # מעקב מתחרים
    "Luxury Fashion Market Trends",   # שוק היוקרה
    "Smart Fabrics Wearables",        # בדים חכמים
    "Fashion Logistics Shipping"      # שילוח
]

def get_google_news_url(query):
    encoded = urllib.parse.quote(query)
    # חיפוש של 24 השעות האחרונות
    return f"https://news.google.com/rss/search?q={encoded}+when:1d&hl=en-US&gl=US&ceid=US:en"

RSS_FEEDS = [get_google_news_url(t) for t in TOPICS]

def run_bot():
    print(f"🚀 Bot started at {datetime.now()}")
    
    # בחירת מודל חכמה (כדי למנוע שגיאות)
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        # מנסים למצוא את Flash כי הוא הכי מהיר וחסכוני, אחרת לוקחים את הראשון
        selected_model = next((m for m in models if 'flash' in m), models[0])
        print(f"🤖 Using model: {selected_model}")
        model = genai.GenerativeModel(selected_model)
    except Exception as e:
        print(f"⚠️ Model selection failed, using default: {e}")
        model = genai.GenerativeModel('gemini-1.5-flash')

    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            if not feed.entries: continue
            
            # לוקחים רק את הידיעה הכי רלוונטית
            item = feed.entries[0]

            # בדיקת כפילות (כדי לא לבזבז AI על מה שכבר יש)
            existing = supabase.table('news').select("id").eq('title', item.title).execute()
            if existing.data:
                print(f"   Skipping existing: {item.title[:20]}...")
                continue

            print(f"   🎣 Processing: {item.title[:30]}...")
            
            # השהייה קריטית למניעת חסימה (Rate Limiting)
            time.sleep(5) 

            prompt = f"""
            Act as an elite fashion intelligence analyst.
            1. Summarize this news in Hebrew (Business tone, max 2 sentences).
            2. Categorize into ONE: 'LOGISTICS', 'MATERIALS', 'REGULATION', 'TECH', 'MARKET'.
            
            Format exactly:
            Category: [CATEGORY]
            Summary: [HEBREW TEXT]
            
            News: {item.title}
            Link: {item.link}
            """
            
            res = model.generate_content(prompt)
            text = res.text
            
            # פירוק התשובה
            category = "GLOBAL"
            content = text
            if "Category:" in text:
                parts = text.split("Summary:")
                category = parts[0].replace("Category:", "").strip()
                content = parts[1].strip()

            # שמירה
            data = {
                "title": item.title,
                "content": content,
                "category": category,
                "source_url": item.link,
                "likes": 0,
                "is_public": True
            }
            
            supabase.table('news').insert(data).execute()
            print(f"   ✅ Saved: [{category}]")
            
        except Exception as e:
            print(f"   ❌ Error on feed: {e}")
            time.sleep(5) # המתנה במקרה שגיאה

if __name__ == "__main__":
    run_bot()
