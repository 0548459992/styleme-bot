import os
import time
import feedparser
from google import genai
import json
from supabase import create_client
import urllib.parse
from datetime import datetime, timedelta
import random
import requests

# --- הגדרות מערכת ---
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

# שימוש במודל 1.5 פלאש למכסה מקסימלית בחינם (1,500 ליום)
MODEL_NAME = "gemini-2.0-flash"

client_ai = genai.Client(api_key=GEMINI_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# רשימת 20 השפות לתמיכה גלובלית
LANG_CODES = ["he", "en", "it", "fr", "zh", "es", "de", "tr", "vi", "bn", "hi", "id", "ja", "ko", "ar", "ru", "pl", "nl", "sv", "pt"]

# --- בנק המקורות הישירים ---
DIRECT_FEEDS = [
    "https://www.businessoffashion.com/feeds/rss/", 
    "https://www.voguebusiness.com/feed",
    "https://wwd.com/feed/", 
    "https://www.fashionunited.com/rss-feed",
    "https://www.textileworld.com/feed/", 
    "https://www.fashionnetwork.com/rss/feed.xml",
    "https://hypebeast.com/feed", 
    "https://www.apparelresources.com/feed/",
    "https://www.thefashionlaw.com/feed/", 
    "https://www.ecotextile.com/news?format=feed&type=rss"
]

# --- בנק 110 הנושאים המלא ---
ALL_TOPICS = [
    "Avant-Garde Fashion Design Trends", "Haute Couture Craftsmanship News", "Runway Color Forecast 2026", "Runway Color Forecast 2027",
    "Minimalist Fashion Movement", "Cyberpunk & Techwear Aesthetics", "Sustainable Couture Techniques",
    "Bespoke Tailoring Industry News", "Womenswear Silhouette Innovation", "Footwear Sculpture & Design",
    "Knitwear Structure Innovation", "Luxury Bridal Market Trends", "Experimental Accessories Design",
    "Streetwear Subculture Research", "Vintage & Archival Fashion Market", "Costume Design & Cinema Art",
    "Fashion Illustration Modern Masters", "Emerging Designers Global Talent", "Textile Pattern Design Trends",
    "Gender-Neutral Fashion Design", "Artisanal Embroidery Techniques", "Deconstruction in Fashion Design",
    "Modest Fashion Global Trends", "Resort Wear Design Innovation",
    "Smart Fabrics & Electronic Textiles", "Biodegradable Synthetic Fibers", "Recycled Ocean Plastic Textiles",
    "Spider Silk Bio-Engineering", "Mycelium & Mushroom Leather", "High-Performance Sportswear Fabrics",
    "Carbon Fiber Apparel Applications", "Nanotechnology in Textile Finishing", "Waterless Dyeing Technology",
    "Denim Indigo Weaving Innovations", "Merino Wool Sustainability Trends", "Cashmere Supply Chain Ethics",
    "Digital Inkjet Textile Printing", "Non-woven Medical Textiles", "Aerospace Grade Technical Fabrics",
    "Cotton Genetic Modification News", "Industrial Hemp Fiber Processing", "Antibacterial Fabric Innovation",
    "Fire-Retardant Textile Research", "Phase Change Materials in Clothing", "3D Weaving Technology News",
    "Bio-based Polymers for Fashion", "Textile Waste Upcycling Tech",
    "Generative AI in Apparel Design", "3D Body Modeling & Fit Tech", "Virtual Try-On UX Innovation",
    "Metaverse Luxury Collections", "Blockchain for Luxury Authentication", "NFT Fashion Assets Regulation",
    "Robotic Sewing & Assembly Lines", "Digital Product Passports Textiles", "Big Data in Fashion Retail",
    "AR-Powered Retail Experiences", "Artificial Intelligence Style Curators", "Fashion E-commerce Algorithm Trends",
    "Livestream Shopping Tech Global", "Interactive Garment QR Codes", "Smart Warehouse Logistics Fashion",
    "Automated Textile Quality Control", "Predictive Analytics for Fashion Trends",
    "Global Fashion Retail Growth 2026", "Global Fashion Retail Growth 2027", "Luxury Sector Financial Outlook", "Apparel Supply Chain Resilience",
    "Raw Material Price Volatility", "Logistics Shipping Port Delay", "Air Freight Trends for Fashion",
    "Resale & Circular Economy Growth", "Clothing Rental Subscription Models", "Direct-to-Consumer Strategy News",
    "Department Store Revival Strategies", "Luxury Market in Southeast Asia", "Emerging Textile Hubs Ethiopia",
    "Post-Fast Fashion Business Models", "Merchandising Planning AI Software", "Impact of Inflation on Fashion",
    "Apparel Sourcing Strategy Vietnam", "India Textile Export Growth", "Turkey Apparel Manufacturing News",
    "Global Cotton Stock Index", "EU EPR Legislation for Textiles", "Fashion Carbon Footprint Metrics", "Water Scarcity in Textile Zones",
    "Fair Trade Labor Standards News", "Microplastic Filtration Solutions", "Supply Chain Traceability Software",
    "B-Corp Certified Fashion Brands", "Anti-Greenwashing Marketing Laws", "Regenerative Cotton Farming News",
    "Animal Welfare in Fashion Industry", "Zero-Waste Pattern Making Tech", "Chemical Safety in Textile Dyeing",
    "Fashion Intellectual Property Law", "Copyright Protection for Designs", "Counterfeit Detection Technology",
    "Garment Worker Minimum Wage News", "Textile Recycling Infrastructure EU",
    "Global Fashion Week Highlights", "Textile Innovation Trade Shows", "Museum Costume Exhibitions",
    "Fashion History Research News", "Iconic Designer Retrospectives", "Subculture Influence on High Fashion",
    "Ethno-Fashion Design Preservation", "Fashion Photography New Trends", "Luxury Hospitality & Fashion Collabs",
    "Sustainable Fashion Awards 2026", "Sustainable Fashion Awards 2027", "Global Textile Machinery Expo"
]

def get_ai_budget():
    try:
        res = supabase.table('ai_budget').select("*").eq('id', 1).single().execute()
        budget = res.data
        last_reset = datetime.fromisoformat(budget['last_reset'].replace('Z', '+00:00'))
        if datetime.now(last_reset.tzinfo) - last_reset > timedelta(days=1):
            supabase.table('ai_budget').update({"requests_today": 0, "last_reset": datetime.now().isoformat()}).eq('id', 1).execute()
            return 0
        return budget['requests_today']
    except: return 0

def update_ai_budget(count):
    current = get_ai_budget()
    supabase.table('ai_budget').update({"requests_today": current + count}).eq('id', 1).execute()

def analyze_multilingual(item, budget):
    # המתנה קצרה למניעת חסימת RPM במסלול החינמי
    time.sleep(15)
    
    # מכסה של 1500 ליום מאפשרת לנו לעבוד בחופשיות יחסית
    if budget < 1400:
        target_langs = LANG_CODES if budget < 1000 else ["he", "en", "it", "fr", "zh", "tr"]
        needs_more = budget >= 1000
    else:
        return None, True

    prompt = f"""
    Analyze this news: {item.title}
    1. Categorize exactly as one of: TRENDS, MARKET, TECH, LOGISTICS, REGULATION.
    2. Provide a professional 2-sentence summary for each code: {', '.join(target_langs)}.
    Return ONLY a valid JSON object:
    {{
      "category": "...",
      "titles": {{"he": "...", "en": "...", ...}},
      "summaries": {{"he": "...", "en": "...", ...}}
    }}
    """
    try:
        res = client_ai.models.generate_content(model=MODEL_NAME, contents=prompt)
        clean_json = res.text.strip().replace("```json", "").replace("```", "")
        return json.loads(clean_json), needs_more
    except Exception as e:
        print(f"AI Error: {e}")
        return None, True

def run_bot():
    budget = get_ai_budget()
    print(f"🚀 StyleMe Global Engine (Broad Scan Mode). Budget: {budget}/1500")
    
    items_to_publish = []
    
    # הגרלת משימות מהבנק
    selected_feeds = random.sample(DIRECT_FEEDS, min(6, len(DIRECT_FEEDS)))
    selected_topics = random.sample(ALL_TOPICS, min(12, len(ALL_TOPICS)))
    tasks = [(f, "RSS") for f in selected_feeds] + [(t, "TOPIC") for t in selected_topics]
    random.shuffle(tasks)

    for source, s_type in tasks:
        if len(items_to_publish) >= 15: break
        
        if s_type == "TOPIC":
            search_lang = random.choice(["en", "it", "fr", "zh", "tr"])
            encoded_query = urllib.parse.quote(source)
            url = f"https://news.google.com/rss/search?q={encoded_query}&hl={search_lang}&gl={search_lang.upper()}&ceid={search_lang.upper()}:en"
        else:
            url = source

        try:
            resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=12)
            feed = feedparser.parse(resp.content)
            
            # סורקים את כל הפיד כדי לא לפספס כלום
            for entry in feed.entries:
                if len(items_to_publish) >= 15: break
                
                # בדיקת כפילות ב-DB - מהיר וחינמי
                existing = supabase.table('news').select("id").eq('source_url', entry.link).execute()
                if existing.data: continue

                # רק ידיעה חדשה באמת עוברת לניתוח AI
                ai_data, needs_more = analyze_multilingual(entry, budget)
                
                if ai_data:
                    items_to_publish.append({
                        "source_url": entry.link,
                        "category": ai_data.get('category', 'TRENDS'),
                        "titles": ai_data.get('titles', {"en": entry.title}),
                        "summaries": ai_data.get('summaries', {}),
                        "needs_full_translation": needs_more,
                        "is_public": True
                    })
                    budget += 1
                else:
                    # שמירה גולמית אם ה-AI בחיסכון או תקול - למניעת פספוסים
                    items_to_publish.append({
                        "source_url": entry.link,
                        "titles": {"en": entry.title},
                        "summaries": {"en": "AI summary in progress..."},
                        "needs_full_translation": True,
                        "is_public": True
                    })
        except Exception as e:
            print(f"Error processing {url[:30]}: {e}")
            continue

    # --- DRIP FEEDING ---
    if items_to_publish:
        print(f"🕒 Scheduling {len(items_to_publish)} items over 28 minutes...")
        interval = 28 / len(items_to_publish) if len(items_to_publish) > 1 else 0
        start_time = datetime.utcnow()

        for i, item in enumerate(items_to_publish):
            scheduled_time = start_time + timedelta(minutes=i * interval)
            item["created_at"] = scheduled_time.isoformat()
            try:
                supabase.table('news').insert(item).execute()
                print(f"✅ Scheduled: {scheduled_time.strftime('%H:%M:%S')} | {list(item['titles'].values())[0][:30]}")
            except: pass

        update_ai_budget(len(items_to_publish))
    else:
        print("😴 No new items found.")

if __name__ == "__main__":
    run_bot()
