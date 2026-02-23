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
    
    # חשוב: מומלץ להשתמש ב-SERVICE_ROLE KEY כדי שהבוט יראה כתבות מוסתרות
    SUPABASE_KEY = os.environ["SUPABASE_KEY"]
    
    # טעינת רשימת מפתחות (Key Rotation)
    keys_env = os.environ.get("GEMINI_API_KEYS", os.environ.get("GEMINI_API_KEY"))
    if not keys_env: raise KeyError("API Keys variable is empty!")
    
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

# --- 3. מודלים חסינים (Resilient Models Logic) ---
def get_dynamic_models():
    try:
        global client_ai
        all_models = list(client_ai.models.list())
        valid_models = []
        
        # רשימה שחורה: מילים שאנחנו לא רוצים בשם של המודל (קול, תמונות, גרסאות ישנות)
        bad_words = ['audio', 'tts', 'image', 'vision', 'preview-09', 'preview-12']
        
        for m in all_models:
            name = m.name.lower()
            # מוודא שיש "flash" אבל שאין אף מילה מהרשימה השחורה
            if "flash" in name and not any(bad in name for bad in bad_words):
                valid_models.append(m.name.replace("models/", ""))
        
        valid_models.sort(reverse=True) 
        if not valid_models: 
            return []
        
        print(f"✅ Clean Models Found: {valid_models}", flush=True)
        return valid_models
        
    except Exception as e:
        print(f"⚠️ Error fetching models: {e}", flush=True)
        if rotate_key():
            client_ai = get_ai_client()
            return get_dynamic_models()
        return ["gemini-2.0-flash", "gemini-1.5-flash"] # Fallback בטוח

# טעינה ראשונית של המודלים
ACTIVE_MODELS = get_dynamic_models()

# --- 4. המוח: ניתוח תוכן עם התאוששות (Retry Engine) ---

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
    
    if not ACTIVE_MODELS:
        get_dynamic_models()
    
    # הפרומפט החדש: כופה על גוגל מבנה קשיח בלי מקום לאלתורים!
    prompt = f"""
    You are a Global Fashion Intelligence Analyst.
    Analyze this news title: "{item_title}".
    
    CRITICAL: You MUST return ONLY a valid JSON object matching this EXACT structure:
    {{
        "category": "TRENDS", // Choose exactly ONE: MARKET, LOGISTICS, TECH, TRENDS
        "titles": {{
            "en": "English translated title",
            "he": "Hebrew translated title"
            // Continue for all requested languages
        }},
        "summaries": {{
            "en": "English 1-sentence summary",
            "he": "Hebrew 1-sentence summary"
            // Continue for all requested languages
        }}
    }}
    
    Target languages: {LANG_CODES}
    """
    
    for model_name in ACTIVE_MODELS:
        try:
            # מנוחה קטנה כדי לא לעצבן את שרתי גוגל
            time.sleep(1.5) 
            
            response = client_ai.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            
            result = extract_json_smart(response.text)
            
            if result:
                # מנגנון תיקון אוטומטי במקרה שה-AI טעה באיות של המפתחות
                if 'title' in result and 'titles' not in result:
                    result['titles'] = result.pop('title')
                if 'summary' in result and 'summaries' not in result:
                    result['summaries'] = result.pop('summary')
                if 'translations' in result and 'titles' not in result:
                    result['titles'] = result.pop('translations')
                
                # בדיקת תקינות הקטגוריה
                cat = result.get('category', '').upper()
                valid_cats = ['TRENDS', 'TECH', 'MARKET', 'LOGISTICS']
                result['category'] = cat if cat in valid_cats else 'TRENDS'
                
                return result
                
        except Exception as e:
            err = str(e).lower()
            
            # עומס זמני על המודל הספציפי אצל גוגל (503)
            if "503" in err or "unavailable" in err:
                print(f"⚠️ Model {model_name} is overloaded (503). Trying next model...", flush=True)
                continue
                
            # חסימת מהירות/מכסה (Quota - 429)
            elif "429" in err or "quota" in err or "resourceexhausted" in err:
                if rotate_key():
                    print(f"🔄 Switched Key on {model_name}. Retrying...", flush=True)
                    client_ai = get_ai_client()
                    continue 
                else:
                    print(f"⚠️ Key exhausted. Sleeping 60s to let Google reset quota...", flush=True)
                    time.sleep(60) 
                    return None 
                    
            elif "not found" in err:
                continue
            else:
                print(f"🚨 DEBUG ERROR on {model_name}: {repr(e)}", flush=True)
                continue 

    print("❌ All models failed for this item.", flush=True)
    return None
    
# --- 5. לוגיקה עסקית ---

def enforce_secrecy():
    """מוודא ששום טיוטה או פנדינג לא חשופים לציבור"""
    print("👮 Safety Check: Hiding leaks...", flush=True)
    try:
        supabase.table('news').update({"is_public": False}).eq('category', 'Pending').execute()
        supabase.table('news').update({"is_public": False}).eq('needs_full_translation', True).execute()
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
                
                # הכל מוסתר בהתחלה
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
                    print("📥 Queue +1 (Hidden)")
                else:
                    print("⚠️ Draft +1 (Hidden)")
                    item.update({
                        "category": "Pending",
                        "titles": {"en": entry.title},
                        "summaries": {},
                        "needs_full_translation": True
                    })
                
                # תפיסת שגיאות במסד הנתונים כדי שלא ישתקו אותנו
                try:
                    supabase.table('news').insert(item).execute()
                    count += 1
                except Exception as db_err:
                    print(f"🚨 DATABASE INSERT ERROR: {db_err}", flush=True)
                
        except Exception as e:
            continue
        
    print(f"🚜 Harvest Finished. +{count} hidden items.", flush=True)

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
                try:
                    supabase.table('news').update({
                        "category": ai_data.get('category', 'TRENDS'),
                        "titles": ai_data.get('titles'),
                        "summaries": ai_data.get('summaries'),
                        "needs_full_translation": False,
                        "is_public": False # הופך למוכן אך מוסתר
                    }).eq('id', item['id']).execute()
                    print("✅ Draft Fixed -> Queue.", flush=True)
                except Exception as db_err:
                    print(f"🚨 DATABASE UPDATE ERROR: {db_err}", flush=True)
    except pass

def publish_all_spread():
    """
    מפרסם את *כל* הכתבות המוכנות שיש במחסנית,
    אבל בפריסה יחסית של זמן (Spaced out).
    """
    print("🚀 Starting Smart Spread Publish...", flush=True)
    
    try:
        # 1. שליפת כל הכתבות המוכנות (ללא הגבלת כמות!)
        res = supabase.table('news').select("id, titles") \
            .eq('is_public', False) \
            .eq('needs_full_translation', False) \
            .neq('category', 'Pending') \
            .order('created_at', desc=False) \
            .execute()
            
        queue = res.data
        total_items = len(queue)

        if total_items == 0:
            print("😴 Queue empty. Nothing to publish.", flush=True)
            return

        print(f"📊 Found {total_items} items ready to go.", flush=True)

        # 2. חישוב זמן ההשהייה
        MAX_DURATION_SECONDS = 720 
        delay = int(MAX_DURATION_SECONDS / max(total_items, 1))
        
        # מגבלות שפיות: לא פחות מ-2 שניות, לא יותר מ-3 דקות בין כתבה לכתבה
        delay = max(2, min(delay, 180))

        print(f"⏳ Spreading publication. Delay: {delay}s per article.", flush=True)
        
        published_count = 0

        for item in queue:
            title = item['titles'].get('en', 'News')
            
            # פרסום
            try:
                supabase.table('news').update({"is_public": True}).eq('id', item['id']).execute()
                
                published_count += 1
                print(f"✅ ({published_count}/{total_items}) LIVE: {title[:40]}...", flush=True)
                
                # מחכים רק אם זו לא הכתבה האחרונה
                if published_count < total_items:
                    time.sleep(delay)
            except Exception as db_err:
                print(f"🚨 DATABASE PUBLISH ERROR: {db_err}", flush=True)
            
        print("🏁 Queue cleared completely.", flush=True)
            
    except Exception as e:
        print(f"❌ Publish Error: {e}")

# --- 6. הפונקציה הראשית ---

def run_once():
    print("⚡ StyleMe Bot: Smart Pulse", flush=True)
    
    # 1. בטיחות
    enforce_secrecy()
    
    # 2. איסוף מסיבי (הכל נכנס מוסתר)
    harvest_aggressive_time_limited()
    
    # 3. תיקון טיוטות
    process_pending_drafts()
    
    # 4. פרסום חכם (הכל, בפריסה יחסית)
    publish_all_spread()
    
    print("🏁 Done.", flush=True)

if __name__ == "__main__":
    run_once()
