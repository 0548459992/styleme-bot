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

# הרשימה המורחבת והמלאה ביותר
ALL_TOPICS = [
    # --- MARKET, FINANCE & BUSINESS (עבור לחצן MARKET) ---
    "Fashion Industry IPO News", "Luxury Brands Stock Performance",
    "Global Fashion Retail Revenue 2026", "Mergers and Acquisitions Fashion",
    "Apparel Consumer Spending Trends", "Emerging Markets Fashion Growth",
    "Venture Capital in Fashion Tech", "Luxury Goods Market Analysis",
    "Fashion E-commerce Quarterly Reports", "Retail Bankruptcy News Fashion",
    "Fast Fashion Market Share Data", "Sportswear Market Growth Forecast",
    
    # --- LOGISTICS & SUPPLY CHAIN (עבור לחצן LOGISTICS) ---
    "Textile Supply Chain Disruptions", "Fashion Last Mile Delivery",
    "Warehouse Automation Apparel", "Sustainable Packaging Solutions",
    "Cold Chain Logistics Luxury", "Freight Shipping Rates Textiles",
    "Reshoring Textile Manufacturing", "Inventory Management AI",
    "RFID Technology Fashion Retail", "Circular Supply Chain Models",
    "Traceability in Cotton Supply", "Cross-border E-commerce Logistics",
    
    # --- TECH & INNOVATION (עבור לחצן TECH) ---
    "Generative AI Fashion Design", "Virtual Try-On Technology",
    "Digital Product Passports", "Smart Fabrics Wearable Tech",
    "3D Knitting Technology", "Biomaterials Fashion Innovation",
    "Mycelium Leather Developments", "Waterless Dyeing Technologies",
    "Blockchain Luxury Authentication", "NFT Fashion Trends 2026",
    "Hyper-Personalization AI", "Robotics in Garment Manufacturing",
    
    # --- TRENDS & DESIGN (עבור לחצן TRENDS) ---
    "Runway Color Trends 2026", "Sustainable Couture Techniques",
    "Avant-Garde Silhouette Trends", "Streetwear Culture Evolution",
    "Gender-Neutral Fashion Design", "Vintage and Resale Market Trends",
    "Denim Upcycling Trends", "Modest Fashion Market Growth",
    "Footwear Design Innovation", "Accessories Trend Forecast",
    "Textile Pattern Trends 2026", "Minimalist Fashion Aesthetics"
]

# --- 3. ניהול מודלים ---
def get_dynamic_models():
    """מביא מודלים ומתעדף FLASH"""
    try:
        all_models = list(client_ai.models.list())
        valid_models = []
        for m in all_models:
            if "flash" in m.name.lower():
                clean_name = m.name.replace("models/", "")
                valid_models.append(clean_name)
        valid_models.sort(reverse=True) 
        return valid_models if valid_models else []
    except: return []

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
    """בודק אם הלינק קיים ב-3 ימים האחרונים"""
    try:
        three_days_ago = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        response = supabase.table("news").select("id").eq("source_url", url).gte("created_at", three_days_ago).execute()
        return True if response.data else False
    except: return False

def analyze_content(item_title):
    """
    מנתח את התוכן ומכריח את ה-AI לבחור קטגוריה חוקית בלבד.
    """
    prompt = f"""
    You are a Global Fashion Intelligence Analyst.
    Analyze this news title: "{item_title}".
    
    CRITICAL TASK 1: Categorize into EXACTLY ONE of these 4 categories:
    - 'MARKET' (For finance, stocks, retail, business, mergers, sales).
    - 'LOGISTICS' (For supply chain, shipping, manufacturing, sustainability, regulation).
    - 'TECH' (For AI, digital, smart fabrics, innovation, materials).
    - 'TRENDS' (For design, runway, style, colors, collections).
    
    CRITICAL TASK 2: Translate title to: {LANG_CODES}.
    CRITICAL TASK 3: Summarize in 1 sentence in: {LANG_CODES}.
    
    Return ONLY valid JSON:
    {{
        "category": "CATEGORY_NAME",
        "titles": {{...}},
        "summaries": {{...}}
    }}
    """
    
    models_to_try = ACTIVE_MODELS if ACTIVE_MODELS else [None]

    for model_name in models_to_try:
        try:
            # print(f"🧠 Analyzing with: {model_name}...", flush=True)
            if model_name:
                response = client_ai.models.generate_content(
                    model=model_name, contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                )
            else: return None

            result = extract_json_smart(response.text)
            
            # וידוא ותיקון קטגוריה
            if result:
                cat = result.get('category', '').upper()
                valid_cats = ['TRENDS', 'TECH', 'MARKET', 'LOGISTICS']
                
                # מנגנון תיקון אם ה-AI טועה
                if cat not in valid_cats:
                    title_lower = item_title.lower()
                    if any(x in title_lower for x in ['stock', 'sale', 'revenue', 'ipo', 'business']):
                        result['category'] = 'MARKET'
                    elif any(x in title_lower for x in ['shipping', 'supply', 'chain', 'freight']):
                        result['category'] = 'LOGISTICS'
                    elif any(x in title_lower for x in ['ai', 'digital', 'tech', 'smart']):
                        result['category'] = 'TECH'
                    else:
                        result['category'] = 'TRENDS'
                else:
                    result['category'] = cat # מוודאים שזה אותיות גדולות
                
                return result
            
        except Exception:
            continue 

    return None

# --- 5. מנוע המחסנית והטיוטות (Queue & Drafts) ---

def process_pending_drafts():
    """פתרון 3: מנסה לתקן טיוטות שנכשלו בעבר"""
    print("🛠️ Checking for drafts to repair...", flush=True)
    try:
        # שולף 5 טיוטות
        drafts = supabase.table('news').select("*").eq('needs_full_translation', True).limit(5).execute()
        if not drafts.data: 
            print("✨ No drafts found.", flush=True)
            return

        for item in drafts.data:
            print(f"🔄 Retrying draft: {item['source_url'][:20]}...", flush=True)
            original_title = item['titles'].get('en') if item['titles'] else "News"
            
            ai_data = analyze_content(original_title)
            
            if ai_data and isinstance(ai_data.get('titles'), dict) and 'en' in ai_data['titles']:
                supabase.table('news').update({
                    "category": ai_data.get('category', 'TRENDS'),
                    "titles": ai_data.get('titles'),
                    "summaries": ai_data.get('summaries'),
                    "needs_full_translation": False,
                    "is_public": False # מעביר למחסנית המתנה, לא מפרסם מיד!
                }).eq('id', item['id']).execute()
                print("✅ Draft repaired -> Moved to Queue.", flush=True)
                time.sleep(2)
            else:
                print("⚠️ Retry failed.", flush=True)
            
    except Exception as e:
        print(f"⚠️ Draft Error: {e}")

def harvest_new_content():
    """איסוף מסיבי למחסנית (Harvesting)"""
    print("\n🚜 STARTING HARVEST...", flush=True)
    
    tasks = []
    for f in DIRECT_FEEDS: tasks.append((f, "RSS"))
    
    # לוקחים 8 נושאים אקראיים בכל סבב איסוף כדי לגוון
    topic_samples = random.sample(ALL_TOPICS, min(8, len(ALL_TOPICS)))
    for t in topic_samples: tasks.append((t, "TOPIC"))
        
    random.shuffle(tasks)
    count = 0
    
    for source, s_type in tasks:
        url = source if s_type == "RSS" else f"https://news.google.com/rss/search?q={urllib.parse.quote(source)}&hl=en-US&gl=US&ceid=US:en"
        
        try:
            resp = requests.get(url, timeout=10)
            feed = feedparser.parse(resp.content)
            
            # לוקחים עד 3 מכל מקור
            for entry in feed.entries[:3]:
                if check_recent_duplicate(entry.link): continue

                print(f"🤖 Analyzing: {entry.title[:30]}...", flush=True)
                ai_data = analyze_content(entry.title)
                
                item = {
                    "source_url": entry.link,
                    "created_at": datetime.utcnow().isoformat(),
                    "likes": 0,
                    "is_public": False, # הכל נכנס למחסנית!
                }

                if ai_data and isinstance(ai_data.get('titles'), dict) and 'en' in ai_data['titles']:
                    # הצלחה - מוכן לפרסום
                    item["category"] = ai_data.get('category', 'TRENDS')
                    item["titles"] = ai_data.get('titles')
                    item["summaries"] = ai_data.get('summaries')
                    item["needs_full_translation"] = False
                    print("📥 Saved to READY QUEUE.")
                else:
                    # כישלון - נשמר כטיוטה לתיקון עתידי
                    print("⚠️ AI Failed. Saving as DRAFT.")
                    item["category"] = "Pending"
                    item["titles"] = {"en": entry.title}
                    item["summaries"] = {}
                    item["needs_full_translation"] = True
                
                try:
                    supabase.table('news').insert(item).execute()
                    count += 1
                    time.sleep(1)
                except: pass
        except: continue
    
    print(f"🚜 Harvest Done. +{count} items.\n")

def publish_next_in_queue():
    """מנגנון הטיפטוף (24 שעות)"""
    try:
        # ספירת ממתינים
        response = supabase.table('news').select("id", count='exact') \
            .eq('is_public', False) \
            .eq('needs_full_translation', False) \
            .execute()
        
        pending_count = response.count
        print(f"📊 Queue: {pending_count} ready.", flush=True)

        if pending_count == 0:
            print("😴 Empty queue.", flush=True)
            return False

        # חישוב זמן המתנה דינמי
        # מחלקים את היממה (86400 שניות) במספר הכתבות שנשארו
        sleep_time = int(86400 / max(pending_count, 1))
        # מגבלה: לא פחות מ-5 דקות, לא יותר משעתיים
        sleep_time = max(300, min(sleep_time, 7200))

        # שליפת הכתבה הישנה ביותר
        to_publish = supabase.table('news').select("id, titles") \
            .eq('is_public', False) \
            .eq('needs_full_translation', False) \
            .order('created_at', desc=False) \
            .limit(1) \
            .execute()
            
        if to_publish.data:
            article = to_publish.data[0]
            title = article['titles'].get('en', 'News')
            
            # פרסום!
            supabase.table('news').update({"is_public": True}).eq('id', article['id']).execute()
            print(f"🚀 LIVE: {title[:30]}...", flush=True)
            print(f"⏳ Next post in {sleep_time/60:.1f} mins.", flush=True)
            
            time.sleep(sleep_time)
            return True
            
    except Exception as e:
        print(f"❌ Publisher Error: {e}")
        time.sleep(60)
        return False

# --- 6. הלוגיקה הרציפה (Infinite Loop) ---

def run_continuous_bot():
    print("♾️ Starting Continuous Bot Loop...", flush=True)
    
    last_harvest_time = 0
    HARVEST_INTERVAL = 14400 # כל 4 שעות
    
    while True:
        now = time.time()
        
        # 1. איסוף תוכן (פעם ב-4 שעות)
        if now - last_harvest_time > HARVEST_INTERVAL:
            harvest_new_content()
            process_pending_drafts()
            last_harvest_time = time.time()
        
        # 2. ניהול פרסום (רץ כל הזמן)
        did_publish = publish_next_in_queue()
        
        if not did_publish:
            # אם אין מה לפרסם, נחכה 5 דקות ונבדוק שוב
            time.sleep(300)

if __name__ == "__main__":
    run_continuous_bot()
