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

# --- 4. ניהול מודלים דינמי ---
def get_dynamic_models():
    """מביא את רשימת המודלים מגוגל בזמן אמת ומסנן מודלים מהירים"""
    try:
        print("📡 Querying Google API for available models...", flush=True)
        all_models = list(client_ai.models.list())
        
        valid_models = []
        for m in all_models:
            if "flash" in m.name.lower():
                clean_name = m.name.replace("models/", "")
                valid_models.append(clean_name)
        
        valid_models.sort(reverse=True) 
        
        if not valid_models:
            print("⚠️ Warning: No 'flash' models found. Using auto-select.", flush=True)
            return []
            
        print(f"✅ Dynamic Model List: {valid_models}", flush=True)
        return valid_models
        
    except Exception as e:
        print(f"⚠️ API Discovery failed: {e}", flush=True)
        return []

ACTIVE_MODELS = get_dynamic_models()

# --- 5. פונקציות עזר ---

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

def check_recent_duplicate(url):
    """בודק כפילויות בטווח של 3 ימים"""
    try:
        three_days_ago = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        response = supabase.table("news").select("id").eq("source_url", url).gte("created_at", three_days_ago).execute()
        if response.data and len(response.data) > 0:
            return True 
        return False 
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
    
    models_to_try = ACTIVE_MODELS if ACTIVE_MODELS else [None]

    for model_name in models_to_try:
        try:
            print(f"🧠 Analyzing with: {model_name if model_name else 'Default Auto'}...", flush=True)
            if model_name:
                response = client_ai.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                )
            else:
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

# --- 6. הלוגיקה הראשית המעודכנת ---

def run_bot():
    print(f"🚀 StyleMe Pro Intelligence Engine Started", flush=True)
    
    tasks = []
    
    # איסוף משימות
    rss_samples = random.sample(DIRECT_FEEDS, 2) 
    for f in rss_samples: tasks.append((f, "RSS"))
    
    topic_samples = random.sample(ALL_TOPICS, 3)
    for t in topic_samples: tasks.append((t, "TOPIC"))
        
    random.shuffle(tasks)
    
    MAX_ARTICLES_PER_RUN = 5 
    
    # חישוב זמן השהייה: 30 דקות (1800 שניות) לחלק לכמות הכתבות
    # זה נותן כ-6 דקות המתנה בין כל פרסום
    DELAY_BETWEEN_POSTS = 360 
    
    items_published = 0

    for source, s_type in tasks:
        if items_published >= MAX_ARTICLES_PER_RUN: 
            print("🏁 Batch limit reached. Stopping.", flush=True)
            break
        
        url = source if s_type == "RSS" else f"https://news.google.com/rss/search?q={urllib.parse.quote(source)}&hl=en-US&gl=US&ceid=US:en"
        
        try:
            print(f"📥 Fetching: {source[:40]}...", flush=True)
            resp = requests.get(url, timeout=10)
            feed = feedparser.parse(resp.content)
            
            for entry in feed.entries[:3]:
                if items_published >= MAX_ARTICLES_PER_RUN: break
                
                if check_recent_duplicate(entry.link):
                    print(f"🔹 Skipping recent duplicate: {entry.title[:20]}...", flush=True)
                    continue

                # ניתוח AI
                ai_data = analyze_content(entry.title)
                
                # תנאי סף: שומרים רק אם התקבל מידע מלא ומתורגם
                if ai_data and isinstance(ai_data.get('titles'), dict) and 'en' in ai_data['titles']:
                    item = {
                        "source_url": entry.link,
                        "category": ai_data.get('category', 'General'),
                        "titles": ai_data.get('titles', {}),
                        "summaries": ai_data.get('summaries', {}),
                        "needs_full_translation": False,
                        "is_public": True,
                        "likes": 0,
                        "created_at": datetime.utcnow().isoformat()
                    }
                    
                    if save_to_db(item):
                        print(f"✅ PUBLISHED: {entry.title[:30]}...", flush=True)
                        items_published += 1
                        
                        # --- השהייה חכמה (לפחות 6 דקות) ---
                        if items_published < MAX_ARTICLES_PER_RUN:
                            print(f"⏳ Waiting {DELAY_BETWEEN_POSTS} seconds before next article...", flush=True)
                            time.sleep(DELAY_BETWEEN_POSTS)
                            
                else:
                    # אם אין AI - מדלגים! לא שומרים טיוטה.
                    print("⚠️ AI Analysis failed or incomplete. SKIPPING article (No Drafts).")
                
        except Exception as e:
            print(f"❌ Error fetching feed: {e}")
            continue

if __name__ == "__main__":
    run_bot()
