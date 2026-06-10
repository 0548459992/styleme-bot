import sys
import time
import os
import json
import random
import urllib.parse
import feedparser
import requests
from datetime import datetime, timedelta, timezone
from google import genai
from google.genai import types
import firebase_admin
from firebase_admin import credentials, firestore

# --- 1. הגדרות ומשתני סביבה ---
try:
    # מפתח ההתחברות החדש לפיירבייס (כמחרוזת JSON)
    firebase_creds_json = os.environ["FIREBASE_CREDENTIALS"]
    
    # טעינת רשימת מפתחות (Key Rotation)
    keys_env = os.environ.get("GEMINI_API_KEYS", os.environ.get("GEMINI_API_KEY"))
    if not keys_env: raise KeyError("API Keys variable is empty!")
    
    API_KEYS_POOL = [k.strip() for k in keys_env.split(',') if k.strip()]
    if not API_KEYS_POOL: raise KeyError("No API Keys found!")

except KeyError as e:
    print(f"❌ CRITICAL ERROR: Missing Config: {e}")
    sys.exit(1)

# חיבור לפיירבייס
try:
    creds_dict = json.loads(firebase_creds_json)
    cred = credentials.Certificate(creds_dict)
    # מוודא שלא מתבצע אתחול כפול
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("✅ Connected to Firebase Firestore")
except Exception as e:
    print(f"❌ CRITICAL ERROR: Failed to init Firebase: {e}")
    sys.exit(1)

# ניהול מפתחות Gemini
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
    "Fashion Industry IPO News", "Luxury Brands Stock Performance",
    "Global Fashion Retail Revenue 2026", "Mergers and Acquisitions Fashion",
    "Apparel Consumer Spending Trends", "Emerging Markets Fashion Growth",
    "Textile Supply Chain Disruptions", "Fashion Last Mile Delivery",
    "Warehouse Automation Apparel", "Sustainable Packaging Solutions",
    "Cold Chain Logistics Luxury", "Freight Shipping Rates Textiles",
    "Generative AI Fashion Design", "Virtual Try-On Technology",
    "Digital Product Passports", "Smart Fabrics Wearable Tech",
    "3D Knitting Technology", "Biomaterials Fashion Innovation",
    "Runway Color Trends 2026", "Sustainable Couture Techniques",
    "Avant-Garde Silhouette Trends", "Streetwear Culture Evolution",
    "Gender-Neutral Fashion Design", "Vintage and Resale Market Trends"
]

# --- 3. מודלים חסינים ---
def get_dynamic_models():
    try:
        global client_ai
        all_models = list(client_ai.models.list())
        valid_models = []
        bad_words = ['audio', 'tts', 'image', 'vision', 'preview-09', 'preview-12']
        
        for m in all_models:
            name = m.name.lower()
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
        return ["gemini-2.0-flash", "gemini-1.5-flash"]

ACTIVE_MODELS = get_dynamic_models()

# --- 4. המוח: ניתוח תוכן ---
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
        # פיירבייס: חיפוש לפי URL בלבד מספיק לסינון כפילויות יעיל ומהיר
        docs = db.collection("news").where("source_url", "==", url).limit(1).get()
        return len(docs) > 0
    except: return False

def analyze_content(item_title):
    global client_ai
    if not ACTIVE_MODELS:
        get_dynamic_models()
    
    prompt = f"""
    You are a Global Fashion Intelligence Analyst.
    Analyze this news title: "{item_title}".
    
    CRITICAL: You MUST return ONLY a valid JSON object matching this EXACT structure:
    {{
        "category": "TRENDS", // Choose exactly ONE: MARKET, LOGISTICS, TECH, TRENDS
        "titles": {{
            "en": "English translated title",
            "he": "Hebrew translated title"
        }},
        "summaries": {{
            "en": "English 1-sentence summary",
            "he": "Hebrew 1-sentence summary"
        }}
    }}
    
    Target languages: {LANG_CODES}
    """
    
    for model_name in ACTIVE_MODELS:
        try:
            time.sleep(1.5) 
            response = client_ai.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            
            result = extract_json_smart(response.text)
            
            if result:
                if 'title' in result and 'titles' not in result:
                    result['titles'] = result.pop('title')
                if 'summary' in result and 'summaries' not in result:
                    result['summaries'] = result.pop('summary')
                if 'translations' in result and 'titles' not in result:
                    result['titles'] = result.pop('translations')
                
                cat = result.get('category', '').upper()
                valid_cats = ['TRENDS', 'TECH', 'MARKET', 'LOGISTICS']
                result['category'] = cat if cat in valid_cats else 'TRENDS'
                
                return result
                
        except Exception as e:
            err = str(e).lower()
            if "503" in err or "unavailable" in err:
                print(f"⚠️ Model {model_name} is overloaded (503). Trying next...", flush=True)
                continue
            elif "429" in err or "quota" in err or "resourceexhausted" in err:
                if rotate_key():
                    print(f"🔄 Switched Key on {model_name}. Retrying...", flush=True)
                    client_ai = get_ai_client()
                    continue 
                else:
                    print(f"⚠️ Key exhausted. Sleeping 30s...", flush=True)
                    time.sleep(30) 
                    return None 
            elif "not found" in err: continue
            else:
                print(f"🚨 DEBUG ERROR on {model_name}: {repr(e)}", flush=True)
                continue 

    print("❌ All models failed for this item.", flush=True)
    return None
    
# --- 5. לוגיקה עסקית (פיירבייס) ---

def enforce_secrecy():
    print("👮 Safety Check: Hiding leaks...", flush=True)
    try:
        # פיירבייס: שימוש ב-Batch לעדכון המוני יעיל
        batch = db.batch()
        updates_count = 0
        
        pending_docs = db.collection('news').where('category', '==', 'Pending').where('is_public', '==', True).get()
        for doc in pending_docs:
            batch.update(doc.reference, {"is_public": False})
            updates_count += 1
            
        untranslated_docs = db.collection('news').where('needs_full_translation', '==', True).where('is_public', '==', True).get()
        for doc in untranslated_docs:
            batch.update(doc.reference, {"is_public": False})
            updates_count += 1
            
        if updates_count > 0:
            batch.commit()
    except Exception as e: 
        print(f"Secrecy error: {e}")

def harvest_aggressive_time_limited():
    print("🚜 STARTING HARVEST (Hidden Mode)...", flush=True)
    start_time = time.time()
    TIME_LIMIT_SECONDS = 360 
    
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
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "views": 0, # הוספנו תמיכה במונה צפיות למקרה הצורך
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
                
                try:
                    # הוספת המסמך לקולקציה
                    db.collection('news').add(item)
                    count += 1
                except Exception as db_err:
                    print(f"🚨 DATABASE INSERT ERROR: {db_err}", flush=True)
                
        except Exception as e:
            continue
        
    print(f"🚜 Harvest Finished. +{count} hidden items.", flush=True)

def process_pending_drafts():
    print("🛠️ Checking Drafts...", flush=True)
    try:
        drafts = db.collection('news').where('needs_full_translation', '==', True).limit(5).get()
        if not drafts: return

        for doc in drafts:
            item = doc.to_dict()
            original_title = item.get('titles', {}).get('en', 'News')
            ai_data = analyze_content(original_title)
            
            if ai_data and 'en' in ai_data.get('titles', {}):
                try:
                    doc.reference.update({
                        "category": ai_data.get('category', 'TRENDS'),
                        "titles": ai_data.get('titles'),
                        "summaries": ai_data.get('summaries'),
                        "needs_full_translation": False,
                        "is_public": False
                    })
                    print("✅ Draft Fixed -> Queue.", flush=True)
                except Exception as db_err:
                    print(f"🚨 DATABASE UPDATE ERROR: {db_err}", flush=True)
    except Exception as e: 
        pass

def schedule_publications():
    print("📅 Scheduling items for the next 2 hours...", flush=True)
    try:
        # שליפת מסמכים לפי סטטוס מוכנות
        docs = db.collection('news').where('is_public', '==', False).where('needs_full_translation', '==', False).get()
        
        # סינון נוסף בזיכרון (פיירבייס מגביל מספר תנאי inequality בשאילתה אחת)
        queue = [doc for doc in docs if doc.to_dict().get('category') != 'Pending']
        total_items = len(queue)

        if total_items == 0:
            print("😴 Queue empty. Nothing to schedule.", flush=True)
            return

        # מיון לפי זמן יצירה מוקדם קודם
        queue.sort(key=lambda x: x.to_dict().get('created_at', ''))

        print(f"📊 Found {total_items} items. Writing future timestamps...", flush=True)

        SPREAD_MINUTES = 115 
        gap_minutes = SPREAD_MINUTES / max(total_items, 1)
        now = datetime.now(timezone.utc)
        
        # שימוש ב-Batch לעדכון מסות של נתונים ביעילות
        batch = db.batch()

        for i, doc in enumerate(queue):
            item = doc.to_dict()
            title = item.get('titles', {}).get('en', 'News')
            publish_time = now + timedelta(minutes=(i * gap_minutes))
            
            batch.update(doc.reference, {
                "is_public": True,
                "created_at": publish_time.isoformat() 
            })
            print(f"✅ Scheduled [{publish_time.strftime('%H:%M:%S UTC')}]: {title[:30]}...", flush=True)
            
        batch.commit()
        print("🏁 Scheduling complete! The frontend will reveal them over time.", flush=True)
            
    except Exception as e:
        print(f"❌ Schedule Error: {e}")

# --- 6. הפונקציה הראשית ---

def run_once():
    print("⚡ StyleMe Bot: Smart Scheduled Pulse (Firebase Edition)", flush=True)
    enforce_secrecy()
    harvest_aggressive_time_limited()
    process_pending_drafts()
    schedule_publications()
    print("🏁 Done.", flush=True)

if __name__ == "__main__":
    run_once()
