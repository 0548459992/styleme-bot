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
    
    # טעינת רשימת מפתחות (Key Rotation)
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

# --- 3. מודלים (דינמי לחלוטין - ללא שמות קשיחים) ---
def get_dynamic_models():
    """
    שואב את רשימת המודלים מגוגל.
    אם אין מודלים (או המפתח נכשל) - מנסה להחליף מפתח.
    אם כל המפתחות נכשלו - מחזיר רשימה ריקה (והבוט יעצור).
    """
    try:
        global client_ai
        all_models = list(client_ai.models.list())
        valid_models = []
        for m in all_models:
            # סינון גנרי: כל מה שמכיל flash
            if "flash" in m.name.lower():
                valid_models.append(m.name.replace("models/", ""))
        
        # מיון: החדשים ביותר למעלה
        valid_models.sort(reverse=True) 
        
        if not valid_models:
            print("⚠️ API connected but no 'flash' models found.", flush=True)
            return []
            
        return valid_models
        
    except Exception as e:
        print(f"⚠️ Error fetching models: {e}", flush=True)
        if rotate_key():
            client_ai = get_ai_client()
            return get_dynamic_models() # נסיון חוזר עם מפתח חדש
        return [] # כישלון טוטאלי

# טעינה ראשונית
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
    
    # בדיקת מגן: אם אין מודלים, לא מנסים אפילו
    if not ACTIVE_MODELS:
        print("🛑 No active models found via API. Skipping analysis.", flush=True)
        return None
    
    prompt = f"""
    You are a Global Fashion Intelligence Analyst.
    Analyze this news title: "{item_title}".
    
    TASK 1: Categorize into EXACTLY ONE: 'MARKET', 'LOGISTICS', 'TECH', 'TRENDS'.
    TASK 2: Translate title to: {LANG_CODES}.
    TASK 3: Summarize in 1 sentence in: {LANG_CODES}.
    
    Return ONLY valid JSON.
    """
    
    for model_name in ACTIVE_MODELS:
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
                    continue # נסה שוב עם המפתח החדש
                else: return None
            continue 

    return None

# --- 5. מנגנון בטיחות ---

def enforce_secrecy():
    """מוודא ששום טיוטה או פנדינג לא חשופים לציבור"""
    print("👮 Safety Check: Hiding leaks...", flush=True)
    try:
        supabase.table('news').update({"is_public": False}).eq('category', 'Pending').execute()
        supabase.table('news').update({"is_public": False}).eq('needs_full_translation', True).execute()
        # הגנה נוספת: הסתרת שורות בלי כותרת באנגלית
        # (הערה: Supabase Python לא תמיד תומך ב-filters מורכבים ב-JSON, אז פשוט נסמוך על הדגלים למעלה)
    except: pass

def harvest_aggressive_time_limited():
    print("🚜 STARTING HARVEST (Hidden Mode)...", flush=True)
    
    start_time = time.time()
    TIME_LIMIT_SECONDS = 540 # 9 דקות
    
    tasks = []
    for f in DIRECT_FEEDS: tasks.append((f, "RSS"))
    topic_samples = random.sample(ALL_TOPICS, min(25, len(ALL_TOPICS)))
    for t in topic_samples: tasks.append((t, "TOPIC"))
    random.shuffle(tasks)
    
    count = 0
    
    for source, s_type in tasks:
        if time.time() - start_time > TIME_LIMIT_SECONDS:
            print("⏰ Time Limit. Stopping Harvest.", flush=True)
            break
            
        url = source if s_type == "RSS" else f"https://news.google.com/rss/search?q={urllib.parse.quote(source)}&hl=en-US&gl=US&ceid=US:en"
        
        try:
            resp = requests.get(url, timeout=5)
            feed = feedparser.parse(resp.content)
            
            for entry in feed.entries[:3]:
                if time.time() - start_time > TIME_LIMIT_SECONDS: break
                if check_recent_duplicate(entry.link): continue

                print(f"🤖 Processing: {entry.title[:30]}...", flush=True)
                ai_data = analyze_content(entry.title)
                
                item = {
                    "source_url": entry.link,
                    "created_at": datetime.utcnow().isoformat(),
                    "likes": 0,
                    "is_public": False # הכל מוסתר בהתחלה
                }

                if ai_data and 'en' in ai_data.get('titles', {}):
                    item.update({
                        "category": ai_data.get('category'),
                        "titles": ai_data.get('titles'),
                        "summaries": ai_data.get('summaries'),
                        "needs_full_translation": False
                    })
                    print("📥 Queue +1 (Hidden)")
                else:
                    print("⚠️ Draft +1 (Hidden)")
                    item.update({
                        "category": "Pending",
                        "titles": {"en": entry.title},
                        "summaries": {},
                        "needs_full_translation": True
                    })
                
                supabase.table('news').insert(item).execute()
                count += 1
                
        except: continue
        
    print(f"🚜 Harvest Finished. +{count} hidden items.", flush=True)

def publish_batch_from_queue():
    """
    מפרסם צרור (Batch) של כתבות.
    לא אחת, אלא עד 5 כתבות בכל ריצה.
    """
    print("🚀 Starting Batch Publish...", flush=True)
    
    # כמה כתבות לפרסם במכה?
    BATCH_SIZE = 5 
    published_count = 0
    
    try:
        # שולף את ה-5 הכי ישנות שמוכנות לפרסום
        res = supabase.table('news').select("id, titles") \
            .eq('is_public', False) \
            .eq('needs_full_translation', False) \
            .neq('category', 'Pending') \
            .order('created_at', desc=False) \
            .limit(BATCH_SIZE) \
            .execute()
            
        if not res.data:
            print("😴 Queue empty. Nothing to publish.", flush=True)
            return

        for item in res.data:
            title = item['titles'].get('en', 'News')
            
            # הופך ל-PUBLIC
            supabase.table('news').update({"is_public": True}).eq('id', item['id']).execute()
            print(f"✅ PUBLISHED: {title[:40]}...", flush=True)
            published_count += 1
            time.sleep(1) # השהייה קטנטנה בין עדכונים
            
        print(f"🏁 Batch Complete. Published {published_count} articles.", flush=True)
            
    except Exception as e:
        print(f"❌ Publish Error: {e}")

def process_pending_drafts():
    """תיקון טיוטות"""
    print("🛠️ Checking Drafts...", flush=True)
    try:
        drafts = supabase.table('news').select("*").eq('needs_full_translation', True).limit(5).execute()
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
                    "is_public": False # הופך למוכן אך מוסתר (יפורסם ב-Batch הבא)
                }).eq('id', item['id']).execute()
                print("✅ Draft Fixed -> Queue.", flush=True)
    except: pass

# --- 6. הפונקציה הראשית ---

def run_once():
    print("⚡ StyleMe Bot: Batch Pulse", flush=True)
    
    # 1. בטיחות
    enforce_secrecy()
    
    # 2. איסוף מסיבי
    harvest_aggressive_time_limited()
    
    # 3. תיקון טיוטות
    process_pending_drafts()
    
    # 4. פרסום בצרורות (Batch)
    publish_batch_from_queue()
    
    print("🏁 Done.", flush=True)

if __name__ == "__main__":
    run_once()
