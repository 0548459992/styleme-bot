import sys
import time
import os
import json
import random
import urllib.parse
import feedparser
import requests
from datetime import datetime, timedelta, timezone
from supabase import create_client
from google import genai
from google.genai import types

# --- 1. הגדרות ומשתני סביבה ---
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

# --- 2. רשימת 20 השפות הגלובליות ---
LANG_CODES = [
    "en", "he", "it", "fr", "es", "de",  # מערב אירופה וישראל
    "zh", "jp", "ko", "ru",              # אסיה ומזרח אירופה
    "ar", "pt", "tr", "hi", "vi",        # מזרח תיכון, ברזיל, הודו, וייטנאם
    "id", "th", "nl", "pl", "sv"         # אינדונזיה, תאילנד, צפון ומזרח אירופה
]

# --- 3. מקורות מידע ונושאים (הרשימה המלאה) ---
DIRECT_FEEDS = [
    "https://www.businessoffashion.com/feeds/rss/",
    "https://www.voguebusiness.com/feed",
    "https://wwd.com/feed/",
    "https://www.fashionunited.com/rss-feed",
    "https://www.fashionnetwork.com/rss/feed.xml"
]

# הרשימה המלאה כפי שביקשת - ללא קיצורים
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

# --- 4. ניהול מודלים דינמי לחלוטין (ללא שמות קשיחים) ---
def get_dynamic_models():
    """
    מביא את רשימת המודלים מגוגל בזמן אמת.
    מסנן רק את אלו שמכילים את המילה 'flash' (כי הם מהירים וזולים).
    ממיין אותם כך שגרסאות חדשות (מספר גרסה גבוה) יהיו ראשונות.
    """
    try:
        print("📡 Querying Google API for available models...", flush=True)
        all_models = list(client_ai.models.list())
        
        valid_models = []
        for m in all_models:
            # סינון גנרי: אם השם מכיל flash - אנחנו לוקחים אותו. לא משנה אם זה 1.5 או 2.0 או 3.0 עתידי
            if "flash" in m.name.lower():
                # ניקוי השם (הסרת הקידומת models/ אם קיימת)
                clean_name = m.name.replace("models/", "")
                valid_models.append(clean_name)
        
        # מיון חכם: מנסה למצוא מספרים בשם ולמיין מהגדול לקטן (2.0 לפני 1.5)
        # אם אין מספרים, סתם מיון לפי א-ב
        valid_models.sort(reverse=True) 
        
        if not valid_models:
            print("⚠️ Warning: No 'flash' models found. Using auto-select.", flush=True)
            return [] # החזרה של רשימה ריקה תגרום לקוד לנסות לרוץ ללא שם מודל (ברירת מחדל)
            
        print(f"✅ Dynamic Model List: {valid_models}", flush=True)
        return valid_models
        
    except Exception as e:
        print(f"⚠️ API Discovery failed: {e}", flush=True)
        return []

# טעינת המודלים פעם אחת בריצה
ACTIVE_MODELS = get_dynamic_models()

# --- 5. פונקציות עזר ---

def extract_json_smart(text):
    """מחלץ JSON מתוך טקסט גם אם המודל הוסיף שטויות מסביב"""
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

def check_recent_duplicate(url):
    """
    בודק כפילויות יחסיות לזמן:
    אם הלינק קיים בטבלה, והוא נוצר ב-3 הימים האחרונים -> זה כפול (דלג).
    אם הלינק קיים אבל נוצר לפני שבוע -> זה לא נחשב כפול (פרסם מחדש).
    """
    try:
        # חישוב תאריך של לפני 3 ימים
        three_days_ago = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        
        # השאילתה: תביא לי שורה אם הלינק זהה AND התאריך גדול (חדש) מ-3 ימים אחורה
        response = supabase.table("news").select("id") \
            .eq("source_url", url) \
            .gte("created_at", three_days_ago) \
            .execute()
            
        if response.data and len(response.data) > 0:
            return True # נמצאה כתבה זהה מהימים האחרונים
        return False # הלינק לא קיים, או שהוא ישן מאוד
    except Exception as e:
        print(f"⚠️ DB Check Error: {e}")
        return False

def analyze_content(item_title):
    """שולח למודל ומבקש תרגום ל-20 שפות"""
    
    prompt = f"""
    You are a Global Fashion Intelligence Analyst.
    Analyze this news title: "{item_title}".
    
    Task:
    1. Categorize it into one technical category (e.g., Logistics, Tech, Trends).
    2. Translate the title into ALL these languages: {LANG_CODES}.
    3. Write a very short summary (1 sentence) in ALL these languages: {LANG_CODES}.
    
    Return ONLY valid JSON.
    """
    
    # ניסיון ריצה על המודלים שנמצאו דינמית
    # אם הרשימה ריקה (כי החיפוש נכשל), ננסה לשלוח None למודל כדי שיבחר ברירת מחדל
    models_to_try = ACTIVE_MODELS if ACTIVE_MODELS else [None]

    for model_name in models_to_try:
        try:
            print(f"🧠 Analyzing with: {model_name if model_name else 'Default Auto'}...", flush=True)
            
            # אם יש שם מודל - משתמשים בו. אם לא - שולחים בלי פרמטר model (ברירת מחדל של הספרייה)
            if model_name:
                response = client_ai.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                )
            else:
                 # Fallback למקרה שאין רשימה דינמית
                 # הערה: זה תלוי בגרסת הספרייה, לרוב עדיף לציין מודל.
                 # אם הקוד מגיע לפה, כנראה הייתה בעיית תקשורת בזיהוי המודלים.
                 print("⚠️ No model name detected, skipping AI analysis for this item.")
                 return None

            result = extract_json_smart(response.text)
            if result: return result
            
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "quota" in err:
                print(f"⚠️ Quota Exceeded for this model. Switching...", flush=True)
                continue 
            else:
                print(f"❌ Error with model: {e}", flush=True)
                continue

    return None

def save_to_db(item):
    try:
        supabase.table('news').insert(item).execute()
        return True
    except Exception as e:
        if "42501" in str(e):
            print(f"🚨 DB PERMISSION ERROR: Please Disable RLS in Supabase!", flush=True)
        else:
            print(f"❌ DB Error: {e}", flush=True)
        return False

# --- 6. הלוגיקה הראשית ---

def run_bot():
    print(f"🚀 StyleMe Pro Intelligence Engine Started", flush=True)
    
    tasks = []
    
    # בחירה אקראית של 2 פידים
    rss_samples = random.sample(DIRECT_FEEDS, 2) 
    for f in rss_samples: tasks.append((f, "RSS"))
    
    # בחירה אקראית של 3 נושאים מתוך הרשימה הענקית
    topic_samples = random.sample(ALL_TOPICS, 3)
    for t in topic_samples: tasks.append((t, "TOPIC"))
        
    random.shuffle(tasks)
    
    MAX_ARTICLES_PER_RUN = 5 
    items_published = 0

    for source, s_type in tasks:
        if items_published >= MAX_ARTICLES_PER_RUN: 
            print("🏁 Batch limit reached. Stopping.", flush=True)
            break
        
        # בניית הלינק (RSS או חיפוש גוגל לפי נושא)
        url = source if s_type == "RSS" else f"https://news.google.com/rss/search?q={urllib.parse.quote(source)}&hl=en-US&gl=US&ceid=US:en"
        
        try:
            print(f"📥 Fetching: {source[:40]}...", flush=True)
            resp = requests.get(url, timeout=10)
            feed = feedparser.parse(resp.content)
            
            # מעבר על הכתבות (לוקחים עד 3 מכל מקור כדי לגוון)
            for entry in feed.entries[:3]:
                if items_published >= MAX_ARTICLES_PER_RUN: break
                
                # בדיקת כפילויות חכמה (לפי 3 ימים)
                if check_recent_duplicate(entry.link):
                    print(f"🔹 Skipping recent duplicate: {entry.title[:20]}...", flush=True)
                    continue

                # שליחה ל-AI
                ai_data = analyze_content(entry.title)
                
                if ai_data:
                    item = {
                        "source_url": entry.link,
                        "category": ai_data.get('category', 'General'),
                        "titles": ai_data.get('titles', {}),     # 20 שפות
                        "summaries": ai_data.get('summaries', {}), # 20 שפות
                        "needs_full_translation": False,
                        "is_public": True,
                        "likes": 0,
                        "created_at": datetime.utcnow().isoformat()
                    }
                    
                    if save_to_db(item):
                        print(f"✅ PUBLISHED: {entry.title[:30]}...", flush=True)
                        items_published += 1
                        time.sleep(2) 
                else:
                    print("⚠️ AI Analysis failed (quota or error), skipping.")
                
        except Exception as e:
            print(f"❌ Error fetching feed: {e}")
            continue

if __name__ == "__main__":
    run_bot()
