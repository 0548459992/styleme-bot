import os
import time
import feedparser
from google import genai
from google.genai import types
import json
from supabase import create_client
import urllib.parse
from datetime import datetime, timedelta
import random
import requests
import math 
import sys 
import re # חובה עבור ניקוי JSON

# --- הגדרות מערכת ---
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

client_ai = genai.Client(api_key=GEMINI_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

LANG_CODES = ["he", "en", "it", "fr", "zh", "es", "de", "tr", "vi", "bn", "hi", "id", "ja", "ko", "ar", "ru", "pl", "nl", "sv", "pt"]

# רשימת הנושאים (קוצרה לתצוגה, הקוד המלא מכיל את כולם)
ALL_TOPICS = [
    "Avant-Garde Fashion Design Trends", "Haute Couture Craftsmanship News", "Runway Color Forecast 2026",
    "Sustainable Couture Techniques", "Bespoke Tailoring Industry News", "Womenswear Silhouette Innovation",
    "Footwear Sculpture & Design", "Knitwear Structure Innovation", "Luxury Bridal Market Trends",
    "Experimental Accessories Design", "Streetwear Subculture Research", "Vintage & Archival Fashion Market",
    "Costume Design & Cinema Art", "Fashion Illustration Modern Masters", "Emerging Designers Global Talent",
    "Textile Pattern Design Trends", "Gender-Neutral Fashion Design", "Artisanal Embroidery Techniques",
    "Deconstruction in Fashion Design", "Modest Fashion Global Trends", "Resort Wear Design Innovation",
    "Smart Fabrics & Electronic Textiles", "Biodegradable Synthetic Fibers", "Recycled Ocean Plastic Textiles",
    "Spider Silk Bio-Engineering", "Mycelium & Mushroom Leather", "High-Performance Sportswear Fabrics",
    "Carbon Fiber Apparel Applications", "Nanotechnology in Textile Finishing", "Waterless Dyeing Technology",
    "Denim Indigo Weaving Innovations", "Merino Wool Sustainability Trends", "Cashmere Supply Chain Ethics",
    "Digital Inkjet Textile Printing", "Non-woven Medical Textiles", "Aerospace Grade Technical Fabrics",
    "Cotton Genetic Modification News", "Industrial Hemp Fiber Processing", "Antibacterial Fabric Innovation",
    "Fire-Retardant Textile Research", "Phase Change Materials in Clothing", "3D Weaving Technology News",
    "Bio-based Polymers for Fashion", "Textile Waste Upcycling Tech", "Generative AI in Apparel Design",
    "3D Body Modeling & Fit Tech", "Virtual Try-On UX Innovation", "Metaverse Luxury Collections",
    "Blockchain for Luxury Authentication", "NFT Fashion Assets Regulation", "Robotic Sewing & Assembly Lines",
    "Digital Product Passports Textiles", "Big Data in Fashion Retail", "AR-Powered Retail Experiences",
    "Artificial Intelligence Style Curators", "Fashion E-commerce Algorithm Trends", "Livestream Shopping Tech Global",
    "Interactive Garment QR Codes", "Smart Warehouse Logistics Fashion", "Automated Textile Quality Control",
    "Predictive Analytics for Fashion Trends", "Global Fashion Retail Growth 2026", "Luxury Sector Financial Outlook",
    "Apparel Supply Chain Resilience", "Raw Material Price Volatility", "Logistics Shipping Port Delay",
    "Air Freight Trends for Fashion", "Resale & Circular Economy Growth", "Clothing Rental Subscription Models",
    "Direct-to-Consumer Strategy News", "Department Store Revival Strategies", "Luxury Market in Southeast Asia",
    "Emerging Textile Hubs Ethiopia", "Post-Fast Fashion Business Models", "Merchandising Planning AI Software",
    "Impact of Inflation on Fashion", "Apparel Sourcing Strategy Vietnam", "India Textile Export Growth",
    "Turkey Apparel Manufacturing News", "Global Cotton Stock Index", "EU EPR Legislation for Textiles",
    "Fashion Carbon Footprint Metrics", "Water Scarcity in Textile Zones", "Fair Trade Labor Standards News",
    "Microplastic Filtration Solutions", "Supply Chain Traceability Software", "B-Corp Certified Fashion Brands",
    "Anti-Greenwashing Marketing Laws", "Regenerative Cotton Farming News", "Animal Welfare in Fashion Industry",
    "Zero-Waste Pattern Making Tech", "Chemical Safety in Textile Dyeing", "Fashion Intellectual Property Law",
    "Copyright Protection for Designs", "Counterfeit Detection Technology", "Garment Worker Minimum Wage News",
    "Textile Recycling Infrastructure EU", "Global Fashion Week Highlights", "Textile Innovation Trade Shows",
    "Museum Costume Exhibitions", "Fashion History Research News", "Iconic Designer Retrospectives",
    "Subculture Influence on High Fashion", "Ethno-Fashion Design Preservation", "Fashion Photography New Trends",
    "Luxury Hospitality & Fashion Collabs", "Sustainable Fashion Awards 2026", "Global Textile Machinery Expo"
]

DIRECT_FEEDS = ["https://www.businessoffashion.com/feeds/rss/", "https://www.voguebusiness.com/feed", "https://wwd.com/feed/", "https://www.fashionunited.com/rss-feed", "https://www.fashionnetwork.com/rss/feed.xml"]

def get_live_models():
    """Discover models dynamically but prioritize stability (1.5) over bleeding edge (2.0)"""
    try:
        raw_list = [m.name for m in client_ai.models.list() 
                    if "generateContent" in m.supported_actions 
                    and "gemini" in m.name 
                    and not any(x in m.name for x in ["vision", "image", "robotics"])]
        
        unique_families = {}
        for m in raw_list:
            parts = m.split('-')
            family_key = "-".join(parts[:3]) if len(parts) > 2 else m
            if family_key not in unique_families:
                unique_families[family_key] = m
        
        final_list = list(unique_families.values())
        
        # אסטרטגיית מיון חדשה:
        # 1. תן עדיפות לגרסה 1.5 (הכי יציבה)
        # 2. תן עדיפות ל-Flash
        # 3. דחף את Lite לסוף (הוא גורם לשגיאות JSON)
        final_list.sort(key=lambda x: (
            "lite" in x.lower(),      # Lite ילך לסוף (False בא לפני True במיון)
            not "1.5" in x,           # 1.5 ילך להתחלה
            not "flash" in x          # Flash ילך להתחלה
        ))
        
        print(f"🤖 Smart Sorted Models: {final_list}")
        return final_list
    except: return []

def clean_json_text(text):
    """מנקה שגיאות נפוצות של מודלים חלשים"""
    text = text.strip()
    if text.startswith("```json"): text = text[7:]
    if text.endswith("```"): text = text[:-3]
    # תיקון escape chars בעייתיים שגרמו לקריסה בלוג שלך
    text = text.replace("\\", "\\\\") 
    return text

def analyze_dynamic_with_protection(item_title, model_list):
    if not model_list: return None

    prompt = f"Analyze fashion news and return JSON (titles/summaries in {LANG_CODES}): {item_title}"
    json_config = types.GenerateContentConfig(response_mime_type="application/json")
    
    for model_name in model_list[:6]: # מנסים עד 6 מודלים שונים
        try:
            print(f"📡 Testing: {model_name}...")
            res = client_ai.models.generate_content(
                model=model_name, 
                contents=prompt,
                config=json_config
            )
            
            if res.text:
                try:
                    # ניסיון ראשון: קריאה ישירה
                    return json.loads(res.text)
                except json.JSONDecodeError:
                    # ניסיון שני: ניקוי ותיקון
                    print(f"⚠️ JSON fix needed for {model_name}...")
                    cleaned = clean_json_text(res.text)
                    try:
                        return json.loads(cleaned)
                    except:
                        print(f"❌ JSON unfixable from {model_name}. Skipping.")
                        continue # עוברים למודל הבא במקום לקרוס!
                
        except Exception as e:
            err_str = str(e).upper()
            if any(x in err_str for x in ["429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE"]):
                print(f"⚠️ {model_name} overloaded. Waiting 20s...")
                time.sleep(20)
                continue
            
            print(f"❌ Error with {model_name}: {e}. Next...")
            continue

    print("🛑 All models failed.")
    return None

def run_archive_and_cleanup():
    print("🧹 Running Maintenance...")
    now = datetime.utcnow()
    try:
        supabase.table('news').delete().gte('missing_reports', 3).execute()
        one_year_ago = (now - timedelta(days=365)).isoformat()
        supabase.table('news').delete().lt('created_at', one_year_ago).execute()
        limit_24h = (now - timedelta(days=1)).isoformat()
        supabase.table('news').delete().eq('needs_full_translation', True).lt('created_at', limit_24h).execute()
    except: pass

def run_bot():
    print(f"🚀 StyleMe Pro Engine Active.")
    run_archive_and_cleanup()
    live_models = get_live_models()

    if not live_models:
        print("❌ No models found.")
        return

    # --- Step 1: Catch-up ---
    try:
        pending = supabase.table('news').select("*").eq('needs_full_translation', True).limit(1).execute()
        if pending.data and len(pending.data) > 0:
            item = pending.data[0]
            retry_count = item.get('retry_count', 0)
            
            if retry_count > 5: # הגדלתי ל-5 ניסיונות
                print(f"🗑️ Deleting toxic article: {item['id']}")
                supabase.table('news').delete().eq('id', item['id']).execute()
            else:
                titles = item.get('titles')
                title = list(titles.values())[0] if titles else "News Update"
                
                print(f"🔄 Catching up (Attempt {retry_count + 1}): {title[:30]}...")
                ai_data = analyze_dynamic_with_protection(title, live_models)
                
                if ai_data:
                    supabase.table('news').update({
                        "category": ai_data.get('category'), "titles": ai_data.get('titles'),
                        "summaries": ai_data.get('summaries'), "needs_full_translation": False,
                        "retry_count": 0
                    }).eq('id', item['id']).execute()
                    print("✅ Catch-up complete.")
                else:
                    supabase.table('news').update({"retry_count": retry_count + 1}).eq('id', item['id']).execute()
    except Exception as e: print(f"Catch-up Error: {e}")

    # --- Step 2: New Scan ---
    yesterday = (datetime.utcnow() - timedelta(days=1)).isoformat()
    try:
        recent = supabase.table('news').select('embedding').gte('created_at', yesterday).execute()
        existing_embs = [item['embedding'] for item in recent.data if item['embedding']]
    except: existing_embs = []

    items_to_publish = []
    tasks = [(f, "RSS") for f in random.sample(DIRECT_FEEDS, min(len(DIRECT_FEEDS), 6))] + \
            [(t, "TOPIC") for t in random.sample(ALL_TOPICS, 15)]
    random.shuffle(tasks)

    for source, s_type in tasks:
        if len(items_to_publish) >= 12: break
        url = source if s_type == "RSS" else f"https://news.google.com/rss/search?q={urllib.parse.quote(source)}&hl=en-US&gl=US&ceid=US:en"
        try:
            resp = requests.get(url, timeout=12)
            feed = feedparser.parse(resp.content)
            for entry in feed.entries[:2]:
                if len(items_to_publish) >= 12: break
                
                if supabase.table('news').select("id").eq('source_url', entry.link).execute().data: continue

                ai_data = analyze_dynamic_with_protection(entry.title, live_models)
                if ai_data:
                    items_to_publish.append({
                        "source_url": entry.link, "category": ai_data.get('category'),
                        "titles": ai_data.get('titles'), "summaries": ai_data.get('summaries'),
                        "needs_full_translation": False, "is_public": True, "missing_reports": 0, "retry_count": 0
                    })
                else:
                    items_to_publish.append({
                        "source_url": entry.link, "titles": {"en": entry.title},
                        "needs_full_translation": True, "is_public": True, "missing_reports": 0, "retry_count": 0
                    })
        except: continue

    if items_to_publish:
        interval = 28 / len(items_to_publish)
        start_time = datetime.utcnow()
        for i, item in enumerate(items_to_publish):
            item["created_at"] = (start_time + timedelta(minutes=i * interval)).isoformat()
            try: supabase.table('news').insert(item).execute()
            except: pass

if __name__ == "__main__":
    run_bot()
