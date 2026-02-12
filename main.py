import sys
import time
import os
import json
import random
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

# --- פונקציה דינמית חכמה ---
def get_clean_models():
    """מושך מודלים, מנקה שמות, וממיין"""
    try:
        # במצב של "אין מכסה", הפונקציה הזו לפעמים נכשלת. לכן נשים לה ברירת מחדל קבועה
        # כדי לא לבזבז קריאות API על רשימת מודלים אם ממילא אין מכסה.
        print("📡 Using Smart Model List...", flush=True)
        # רשימה קבועה וחכמה שכוללת את כל האפשרויות, כדי לחסוך קריאה אחת
        return [
            "gemini-2.0-flash", 
            "gemini-2.0-flash-lite-preview-02-05",
            "gemini-1.5-flash", 
            "gemini-1.5-flash-8b"
        ]
    except:
        return ["gemini-2.0-flash"]

CURRENT_MODELS = get_clean_models()

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

def analyze_content(item_title):
    """מנסה לנתח עם AI. אם נכשל - מחזיר None (ולא קורס!)"""
    prompt = f"""
    Act as a Fashion Editor. Analyze this news title: "{item_title}".
    Return a JSON object ONLY with:
    1. "category": One specific fashion category.
    2. "titles": Translated title in {LANG_CODES}.
    3. "summaries": A 2-sentence summary in {LANG_CODES}.
    Return JSON only.
    """
    
    for model_name in CURRENT_MODELS:
        try:
            print(f"🧠 Trying: {model_name}...", flush=True)
            response = client_ai.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            return extract_json_smart(response.text)
            
        except Exception as e:
            err_msg = str(e).lower()
            if "429" in err_msg or "quota" in err_msg:
                print(f"⚠️ {model_name} Quota full.", flush=True)
                continue # מנסה את המודל הבא
            print(f"❌ Error {model_name}: {e}", flush=True)
            continue

    print("🛑 All AI models failed/busy.", flush=True)
    return None # החזרת None מסמנת לבוט לשמור במצב "טיוטה"

def process_pending_articles():
    """פונקציית התיקון: עוברת על כתבות שפורסמו באנגלית ומנסה לתרגם"""
    print("🛠️ Checking for pending translations...", flush=True)
    try:
        # שולפים כתבות שצריכות תיקון (עד 2 בכל ריצה כדי לא להעמיס)
        pending = supabase.table('news').select("*").eq('needs_full_translation', True).limit(2).execute()
        
        if not pending.data:
            print("✨ No pending articles found.", flush=True)
            return

        for item in pending.data:
            print(f"🔄 Fixing: {item['source_url']}...", flush=True)
            # לוקחים את הכותרת המקורית מתוך ה-JSON או מהשדה
            original_title = item.get('titles', {}).get('en', 'News Update')
            
            ai_data = analyze_content(original_title)
            
            if ai_data:
                # עדכון הכתבה עם הנתונים החדשים והמלאים
                supabase.table('news').update({
                    "category": ai_data.get('category'), 
                    "titles": ai_data.get('titles'),
                    "summaries": ai_data.get('summaries'), 
                    "needs_full_translation": False # זהו, תוקן!
                }).eq('id', item['id']).execute()
                print("✅ Fixed successfully!", flush=True)
                time.sleep(5)
            else:
                print("💤 AI still busy, skipping fix.", flush=True)
                break # אם ה-AI לא עובד, אין טעם לנסות לתקן את השאר
                
    except Exception as e:
        print(f"⚠️ Fix loop error: {e}", flush=True)

def run_bot():
    print(f"🚀 StyleMe RESILIENT Engine Active", flush=True)
    
    # 1. קודם כל מנסים לתקן ישנים
    process_pending_articles()

    # 2. מחפשים חדשים
    tasks = []
    rss_samples = random.sample(DIRECT_FEEDS, 2) 
    for f in rss_samples: tasks.append((f, "RSS"))
    
    # מוסיפים גם נושאים כדי לגוון
    topic_samples = random.sample(ALL_TOPICS, 2)
    for t in topic_samples: tasks.append((t, "TOPIC"))
        
    random.shuffle(tasks)
    
    MAX_ARTICLES_PER_RUN = 3 # קצת יותר, כי עכשיו יש לנו גיבוי
    items_published = 0

    for source, s_type in tasks:
        if items_published >= MAX_ARTICLES_PER_RUN: 
            print("🏁 Batch done.", flush=True)
            break 
        
        url = source if s_type == "RSS" else f"https://news.google.com/rss/search?q={urllib.parse.quote(source)}&hl=en-US&gl=US&ceid=US:en"
        
        try:
            print(f"📥 Checking: {source[:30]}...", flush=True)
            resp = requests.get(url, timeout=10)
            feed = feedparser.parse(resp.content)
            
            for entry in feed.entries[:1]:
                if items_published >= MAX_ARTICLES_PER_RUN: break
                
                exists = supabase.table('news').select("id").eq('source_url', entry.link).execute()
                if exists.data:
                    print("🔹 Exists.", flush=True)
                    continue

                # ניסיון לניתוח AI
                ai_data = analyze_content(entry.title)
                
                if ai_data:
                    # הצלחה! שומרים מלא
                    item = {
                        "source_url": entry.link,
                        "category": ai_data.get('category', 'General'),
                        "titles": ai_data.get('titles', {}),
                        "summaries": ai_data.get('summaries', {}),
                        "needs_full_translation": False,
                        "is_public": True,
                        "created_at": datetime.utcnow().isoformat()
                    }
                    print(f"✅ PUBLISHED (AI): {entry.title[:30]}...", flush=True)
                else:
                    # כישלון (מכסה נגמרה) -> שומרים במצב 'חירום' (באנגלית)
                    print(f"⚠️ Saving as RAW DRAFT (Quota empty): {entry.title[:30]}...", flush=True)
                    item = {
                        "source_url": entry.link,
                        "category": "Latest News", # קטגוריה זמנית
                        "titles": {
                            "en": entry.title,
                            "he": entry.title, # שומרים אנגלית גם בשדה העברית בינתיים
                        },
                        "summaries": {
                            "en": "Full analysis coming soon...",
                            "he": "הניתוח המלא יעלה בקרוב...",
                        },
                        "needs_full_translation": True, # מסמנים שצריך לתקן אחר כך
                        "is_public": True, # מפרסמים מיד!
                        "created_at": datetime.utcnow().isoformat()
                    }
                
                # שמירה לדאטה בייס (בין אם זה מלא או טיוטה)
                supabase.table('news').insert(item).execute()
                items_published += 1
                time.sleep(5) 
                
        except Exception as e:
            print(f"Error feed: {e}", flush=True)
            continue

if __name__ == "__main__":
    run_bot()
