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
def get_dynamic_models():
    """
    מושך את כל המודלים מגוגל בזמן אמת,
    אבל מסנן רק את אלו שמתאימים לשימוש חינמי (Flash)
    """
    try:
        print("📡 Asking Google for available models...")
        # 1. שליפת כל המודלים
        all_models = list(client_ai.models.list())
        
        valid_models = []
        for m in all_models:
            name = m.name.lower()
            # 2. סינון קפדני
            # חייב להיות מודל ג'מיני
            if "gemini" not in name: continue
            # חייב לתמוך ביצירת תוכן
            if "generateContent" not in m.supported_actions: continue
            # אסור שיהיה מודל ראייה בלבד
            if "vision" in name: continue
            
            # --- הכלל הכי חשוב: רק FLASH ---
            # אנחנו מסננים החוצה את Pro/Ultra כי הם גומרים את המכסה מיד
            if "flash" in name:
                valid_models.append(m.name)

        # 3. מיון: שמים את גרסה 2.0 למעלה, ואת גרסאות ה-8b (הקלות) בסוף
        # המיון הוא הפוך כדי שהמספרים הגבוהים (2.0) יהיו ראשונים
        valid_models.sort(reverse=True)
        
        print(f"✅ Discovered {len(valid_models)} Flash models: {valid_models}")
        
        if not valid_models:
            # גיבוי למקרה חירום שמשהו השתנה בפורמט השמות
            return ["gemini-2.0-flash", "gemini-1.5-flash"]
            
        return valid_models

    except Exception as e:
        print(f"⚠️ Dynamic discovery failed: {e}. Using fallback.")
        return ["gemini-2.0-flash", "gemini-1.5-flash"]

# טוענים את המודלים פעם אחת בתחילת הריצה
CURRENT_MODELS = get_dynamic_models()

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
    """מחלץ JSON נקי"""
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

def analyze_dynamic_fallback(item_title):
    """משתמש ברשימה הדינמית שמצאנו"""
    prompt = f"""
    Act as a Fashion Editor. Analyze this news title: "{item_title}".
    Return a JSON object ONLY with:
    1. "category": One specific fashion category.
    2. "titles": Translated title in {LANG_CODES}.
    3. "summaries": A 2-sentence summary in {LANG_CODES}.
    Return JSON only.
    """
    
    # עובר על הרשימה הדינמית
    for model_name in CURRENT_MODELS:
        try:
            print(f"🧠 Trying dynamic model: {model_name}...")
            response = client_ai.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            return extract_json_smart(response.text)
            
        except Exception as e:
            err_msg = str(e).lower()
            if "404" in err_msg:
                print(f"⚠️ {model_name} not found (weird for dynamic list). Next...")
                continue
            if "429" in err_msg or "quota" in err_msg:
                print(f"⚠️ {model_name} Quota full. Trying next...")
                continue
            
            print(f"❌ Error: {e}")
            continue

    print("🛑 All dynamic models failed.")
    sys.exit(0)

def run_archive_and_cleanup():
    print("🧹 Cleaning old database entries...")
    try:
        now = datetime.utcnow()
        limit = (now - timedelta(hours=24)).isoformat()
        supabase.table('news').delete().eq('needs_full_translation', True).lt('created_at', limit).execute()
    except: pass

def run_bot():
    print(f"🚀 StyleMe DYNAMIC Engine Active")
    run_archive_and_cleanup()

    tasks = []
    rss_samples = random.sample(DIRECT_FEEDS, 2) 
    for f in rss_samples: tasks.append((f, "RSS"))
        
    topic_samples = random.sample(ALL_TOPICS, 2)
    for t in topic_samples: tasks.append((t, "TOPIC"))
        
    random.shuffle(tasks)
    
    MAX_ARTICLES_PER_RUN = 2
    items_published = 0

    for source, s_type in tasks:
        if items_published >= MAX_ARTICLES_PER_RUN: 
            print("🏁 Batch done.")
            break 
        
        url = source if s_type == "RSS" else f"https://news.google.com/rss/search?q={urllib.parse.quote(source)}&hl=en-US&gl=US&ceid=US:en"
        
        try:
            print(f"📥 Checking source...")
            resp = requests.get(url, timeout=10)
            feed = feedparser.parse(resp.content)
            
            for entry in feed.entries[:1]:
                if items_published >= MAX_ARTICLES_PER_RUN: break
                
                exists = supabase.table('news').select("id").eq('source_url', entry.link).execute()
                if exists.data:
                    print("🔹 Exists.")
                    continue

                ai_data = analyze_dynamic_fallback(entry.title)
                
                if ai_data:
                    item = {
                        "source_url": entry.link,
                        "category": ai_data.get('category', 'General'),
                        "titles": ai_data.get('titles', {}),
                        "summaries": ai_data.get('summaries', {}),
                        "needs_full_translation": False,
                        "is_public": True,
                        "created_at": datetime.utcnow().isoformat()
                    }
                    supabase.table('news').insert(item).execute()
                    print(f"✅ PUBLISHED: {entry.title[:30]}...")
                    items_published += 1
                    time.sleep(10) 
                
        except SystemExit:
            raise 
        except Exception:
            continue

if __name__ == "__main__":
    run_bot()
