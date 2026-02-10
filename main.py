import os
import time
import feedparser
import google.generativeai as genai
from supabase import create_client
import urllib.parse
from datetime import datetime

# --- הגדרות סביבה ---
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

genai.configure(api_key=GEMINI_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- רשימת הזהב: כיסוי תעשייתי מלא ---
# במקום שמות של מותגים, אנחנו מחפשים תופעות ומגמות
TOPICS = [
    # --- ליבה: ייצור ולוגיסטיקה ---
    "Global Cotton Market Prices News",
    "Textile Raw Material Shortage",
    "Synthetic Fibers Market Trends",
    "Global Shipping Freight Rates News",
    "Fashion Supply Chain Disruption",
    "Apparel Manufacturing Hubs Vietnam Bangladesh Turkey",

    # --- הליבה של StyleMe: העתיד ---
    "On-Demand Fashion Manufacturing Market",   # ה-צדקה לקיום שלנו
    "Textile Industry Automation AI Robotics",
    "Digital Fashion & 3D Knitting Technology",
    "Micro-Factory Fashion Trends",             # מפעלים קטנים ומקומיים
    
    # --- רגולציה וקיימות (חובה לאירופה) ---
    "EU Strategy for Sustainable Textiles",
    "Fashion Industry Carbon Footprint Regulations",
    "Textile Recycling Technology News",
    "Digital Product Passport Textiles",        # הדרכון הדיגיטלי האירופי
    
    # --- מתחרים ואיומים (דע את האויב) ---
    "Shein Supply Chain Strategy",
    "Temu Fashion Market Impact",
    "Inditex H&M Business Strategy News",
    "Fashion Ultra Fast Fashion Environmental Impact",

    # --- פיננסים ומאקרו (למנהלי כספים) ---
    "Global Apparel Market Economic Outlook",
    "Luxury Fashion Market Economics",
    "Fashion Retail Bankruptcy & Mergers",
    "Textile Import Export Tariffs Trade War",  # מכסים ומלחמות סחר

    # --- טרנדים וצרכנות (למעצבים) ---
    "Gen Z Fashion Consumer Trends",
    "TikTok Fashion Trends Impact Retail",
    "Smart Fabrics Wearables Innovation",
    "Virtual Fitting Room Technology Market"
]

def get_google_news_url(query):
    # מבקש מגוגל רק חדשות מה-24 שעות האחרונות (when:1d)
    encoded = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={encoded}+when:1d&hl=en-US&gl=US&ceid=US:en"

RSS_FEEDS = [get_google_news_url(t) for t in TOPICS]

def run_bot():
    print(f"🚀 StyleMe Intelligence Bot Started at {datetime.now()}")
    
    # בחירת מודל חכמה - מנסה לקחת את Flash המהיר והחסכוני
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        selected_model = next((m for m in models if 'flash' in m), models[0])
        print(f"🤖 Connected to Brain: {selected_model}")
        model = genai.GenerativeModel(selected_model)
    except Exception as e:
        print(f"⚠️ Fallback to default model: {e}")
        model = genai.GenerativeModel('gemini-1.5-flash')

    # סריקת כל הנושאים
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            if not feed.entries: continue
            
            # לוקחים את הידיעה הכי רלוונטית מהנושא הנוכחי
            item = feed.entries[0]

            # בדיקת כפילות ב-DB (כדי לא לשרוף קרדיט AI סתם)
            existing = supabase.table('news').select("id").eq('title', item.title).execute()
            if existing.data:
                continue # מדלג בשקט

            print(f"   🎣 Found Intel: {item.title[:40]}...")
            
            # השהייה של 5 שניות למניעת חסימה בגוגל
            time.sleep(5) 

            # הנחיה ל-AI: לנתח כמו מומחה אסטרטגי
            prompt = f"""
            You are a senior analyst for StyleMe.
            Analyze this news item for fashion executives.
            
            1. Summarize in Hebrew (Business/Professional tone, max 2 sentences).
            2. Categorize into ONE: 'LOGISTICS', 'MATERIALS', 'REGULATION', 'TECH', 'MARKET', 'SUSTAINABILITY'.
            
            Format exactly:
            Category: [CATEGORY]
            Summary: [HEBREW TEXT]
            
            News Title: {item.title}
            Link: {item.link}
            """
            
            res = model.generate_content(prompt)
            text = res.text
            
            # חילוץ הנתונים מהתשובה
            category = "GLOBAL"
            content = text
            if "Category:" in text:
                parts = text.split("Summary:")
                category = parts[0].replace("Category:", "").strip()
                content = parts[1].strip()

            # שמירה בבסיס הנתונים
            data = {
                "title": item.title,
                "content": content,
                "category": category,
                "source_url": item.link,
                "likes": 0,
                "is_public": True
            }
            
            supabase.table('news').insert(data).execute()
            print(f"   ✅ Published: [{category}]")
            
        except Exception as e:
            print(f"   ❌ Error analyzing feed: {e}")
            time.sleep(5)

if __name__ == "__main__":
    run_bot()
