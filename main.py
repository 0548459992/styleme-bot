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
    
    keys_env = os.environ.get("GEMINI_API_KEYS", os.environ.get("GEMINI_API_KEY"))
    API_KEYS_POOL = [k.strip() for k in keys_env.split(',') if k.strip()]
    if not API_KEYS_POOL: raise KeyError("No API Keys found!")

except KeyError as e:
    print(f"❌ CRITICAL ERROR: Missing Config: {e}")
    sys.exit(1)

# ניהול מפתחות
current_key_index = 0
def get_ai_client():
    return genai.Client(api_key=API_KEYS_POOL[current_key_index])

def rotate_key():
    global current_key_index
    if len(API_KEYS_POOL) > 1:
        current_key_index = (current_key_index + 1) % len(API_KEYS_POOL)
        print(f"🔄 Switching API Key (Index {current_key_index})...", flush=True)
        return True
    return False

client_ai = get_ai_client()
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 2. שפות ונושאים ---
LANG_CODES = [
    "en", "he", "it", "fr", "es", "de", 
    "zh", "jp", "ko", "ru", 
    "ar", "pt", "tr", "hi", "vi", 
    "id", "th", "nl", "pl", "sv"
]

DIRECT_FEEDS = [
    "https://www.businessoffashion.com/feeds/rss/",
    "https://www.voguebusiness.com/feed",
    "https://wwd.com/feed/",
    "https://www.fashionunited.com/rss-feed",
    "https://www.fashionnetwork.com/rss/feed.xml",
    "https://sourcingjournal.com/feed/",
    "https://www.textileworld.com/feed/"
]

ALL_TOPICS = [
    # MARKET
    "Fashion Industry IPO News", "Luxury Brands Stock Performance",
    "Global Fashion Retail Revenue 2026", "Mergers and Acquisitions Fashion",
    "Apparel Consumer Spending Trends", "Emerging Markets Fashion Growth",
    # LOGISTICS
    "Textile Supply Chain Disruptions", "Fashion Last Mile Delivery",
    "Warehouse Automation Apparel", "Sustainable Packaging Solutions",
    "Cold Chain Logistics Luxury", "Freight Shipping Rates Textiles",
    # TECH
    "Generative AI Fashion Design", "Virtual Try-On Technology",
    "Digital Product Passports", "Smart Fabrics Wearable Tech",
    "3D Knitting Technology", "Biomaterials Fashion Innovation",
    # TRENDS
    "Runway Color Trends 2026", "Sustainable Couture Techniques",
    "Avant-Garde Silhouette Trends", "Streetwear Culture Evolution",
    "Gender-Neutral Fashion Design", "Vintage and Resale Market Trends"
]

# --- 3. מודלים ---
def get_dynamic_models():
    try:
        global client_ai
        all_models = list(client_ai.models.list())
        valid_models = []
        for m in all_models:
            if "flash" in m.name.lower():
                valid_models.append(m.name.replace("models/", ""))
        valid_models.sort(reverse=True) 
        return valid_models if valid_models else ["gemini-1.5-flash"]
    except Exception:
        if rotate_key():
            client_ai = get_ai_client()
            return get_dynamic_models()
        return ["gemini-1.5-flash"]

ACTIVE_MODELS = get_dynamic_models()

# --- 4. פונקציות ליבה ---

def extract_json_smart(text):
    try: return json.loads(text)
    except:
        try:
            start = text.find('{')
            end = text.rfind('}') + 1
            if start != -1 and end != -1: return json.loads(text[start:end])
            return None
        except: return None

def check_recent_duplicate(url):
    try:
        three_days_ago = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        res = supabase.table("news").select("id").eq("source_url", url).gte("created_at", three_days_ago).execute()
        return True if res.data else False
    except: return False

def analyze_content(item_title):
    global client_ai
    
    prompt = f"""
    You are a Global Fashion Intelligence Analyst.
    Analyze this news title: "{item_title}".
    
    TASK 1: Categorize into EXACTLY ONE: 'MARKET', 'LOGISTICS', 'TECH', 'TRENDS'.
    TASK 2: Translate title to: {LANG_CODES}.
    TASK 3: Summarize in 1 sentence in: {LANG_CODES}.
    
    Return ONLY valid JSON.
    """
    
    models_to_try = ACTIVE_MODELS if ACTIVE_MODELS else [None]

    for model_name in models_to_try:
        try:
            response = client_ai.models.generate_content(
                model=model_name, contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            result = extract_json_smart(response.text)
            
            if result:
                cat = result.get('category', '').upper()
                valid_cats = ['TRENDS', 'TECH', 'MARKET', 'LOGISTICS']
                if cat not in valid_cats: result['category'] = 'TRENDS'
                else: result['category'] = cat
                return result
            
        except Exception as e:
            if "429" in str(e) or "quota" in str(e).lower():
                print(f"⚠️ Quota hit. Rotating key...", flush=True)
                if rotate_key():
                    client_ai = get_ai_client()
                    continue
                else: return None
            continue 

    return None

# --- 5. ליבה: איסוף מהיר עם סטופר (Time Limited Harvest) ---

def harvest_aggressive_time_limited():
    print("🚜 STARTING TIME-BOXED HARVEST (Max 9 mins)...", flush=True)
    
    start_time = time.time()
    TIME_LIMIT_SECONDS = 540 # 9 דקות בדיוק
    
    tasks = []
    for f in DIRECT_FEEDS: tasks.append((f, "RSS"))
    
    # לוקחים הרבה נושאים
    topic_samples = random.sample(ALL_TOPICS, min(25, len(ALL_TOPICS)))
    for t in topic_samples: tasks.append((t, "TOPIC"))
    
    random.shuffle(tasks)
    
    count = 0
    
    for source, s_type in tasks:
        # 1. בדיקת הסטופר - הדבר הכי חשוב!
        if time.time() - start_time > TIME_LIMIT_SECONDS:
            print("⏰ TIME LIMIT REACHED (9 mins). Stopping Harvest.", flush=True)
            break
            
        url = source if s_type == "RSS" else f"https://news.google.com/rss/search?q={urllib.parse.quote(source)}&hl=en-US&gl=US&ceid=US:en"
        
        try:
            resp = requests.get(url, timeout=5) # טיימאאוט קצר לרשת
            feed = feedparser.parse(resp.content)
            
            # לוקחים עד 3 כתבות מכל מקור
            for entry in feed.entries[:3]:
                
                # בדיקה חוזרת בתוך הלולאה הפנימית
                if time.time() - start_time > TIME_LIMIT_SECONDS: break
                
                if check_recent_duplicate(entry.link): continue

                print(f"🤖 Processing: {entry.title[:30]}...", flush=True)
                ai_data = analyze_content(entry.title)
                
                item = {
                    "source_url": entry.link,
                    "created_at": datetime.utcnow().isoformat(),
                    "likes": 0,
                    "is_public": False 
                }

                if ai_data and 'en' in ai_data.get('titles', {}):
                    item.update({
                        "category": ai_data.get('category'),
                        "titles": ai_data.get('titles'),
                        "summaries": ai_data.get('summaries'),
                        "needs_full_translation": False
                    })
                    print("📥 Queue +1")
                else:
                    print("⚠️ Draft +1")
                    item.update({
                        "category": "Pending",
                        "titles": {"en": entry.title},
                        "summaries": {},
                        "needs_full_translation": True
                    })
                
                supabase.table('news').insert(item).execute()
                count += 1
                # ביטלתי את ה-Sleep כאן כדי לטוס
                
        except: continue
        
    print(f"🚜 Harvest Finished. Total: +{count} items. Time: {int(time.time() - start_time)}s", flush=True)

def process_pending_drafts():
    """תיקון טיוטות"""
    print("🛠️ Checking Drafts...", flush=True)
    try:
        drafts = supabase.table('news').select("*").eq('needs_full_translation', True).limit(3).execute()
        if not drafts.data: return

        for item in drafts.data:
            original_title = item['titles'].get('en') if item['titles'] else "News"
            ai_data = analyze_content(original_title)
            
            if ai_data and 'en' in ai_data.get('titles', {}):
                supabase.table('news').update({
                    "category": ai_data.get('category', 'TRENDS'),
                    "titles": ai_data.get('titles'),
                    "summaries": ai_data.get('summaries'),
                    "needs_full_translation": False,
                    "is_public": False
                }).eq('id', item['id']).execute()
                print("✅ Draft repaired.", flush=True)
    except: pass

def publish_one_from_queue():
    """מפרסם כתבה אחת"""
    try:
        res = supabase.table('news').select("id, titles") \
            .eq('is_public', False) \
            .eq('needs_full_translation', False) \
            .order('created_at', desc=False) \
            .limit(1) \
            .execute()
            
        if res.data:
            item = res.data[0]
            title = item['titles'].get('en', 'News')
            supabase.table('news').update({"is_public": True}).eq('id', item['id']).execute()
            print(f"🚀 PUBLISHED: {title[:40]}...", flush=True)
    except: pass

# --- 6. הפונקציה הראשית ---

def run_once():
    print("⚡ StyleMe Bot: Safe Pulse", flush=True)
    
    # 1. איסוף עם הגבלת זמן קשיחה
    harvest_aggressive_time_limited()
    
    # 2. תיקון טיוטות (מהיר)
    process_pending_drafts()
    
    # 3. פרסום כתבה אחת
    publish_one_from_queue()
    
    print("🏁 Done.", flush=True)

if __name__ == "__main__":
    run_once()
