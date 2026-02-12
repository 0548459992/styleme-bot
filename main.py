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
import math 

# --- הגדרות מערכת ---
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

client_ai = genai.Client(api_key=GEMINI_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

LANG_CODES = ["he", "en", "it", "fr", "zh", "es", "de", "tr", "vi", "bn", "hi", "id", "ja", "ko", "ar", "ru", "pl", "nl", "sv", "pt"]
EMBEDDING_MODEL = "text-embedding-004"

# --- בנק 110 הנושאים המלא (ללא קיצורים) ---
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

DIRECT_FEEDS = [
    "https://www.businessoffashion.com/feeds/rss/", "https://www.voguebusiness.com/feed",
    "https://wwd.com/feed/", "https://www.fashionunited.com/rss-feed",
    "https://www.textileworld.com/feed/", "https://www.fashionnetwork.com/rss/feed.xml"
]

def cosine_similarity(v1, v2):
    try:
        sumxx, sumyy, sumxy = 0, 0, 0
        for i in range(len(v1)):
            x, y = v1[i], v2[i]
            sumxx += x*x; sumyy += y*y; sumxy += x*y
        return sumxy / math.sqrt(sumxx*sumyy)
    except: return 0

def get_live_models():
    """שולף דינמית את המודלים הזמינים ומדרג אותם לפי איכות"""
    try:
        models = [m.name for m in client_ai.models.list() if "generateContent" in m.supported_actions and "gemini" in m.name]
        # סדר עדיפות: 2.0 פלאש, אחר כך 1.5 פלאש, אחר כך 1.5 פלאש-8B
        models.sort(key=lambda x: ("2.0" in x, "1.5" in x, "8b" in x), reverse=True)
        return models
    except: return ["models/gemini-2.0-flash", "models/gemini-1.5-flash"]

def analyze_and_translate_dynamic(item_title, budget, model_list):
    time.sleep(12) 
    if budget >= 1450: return None
    prompt = f"Analyze fashion news and return JSON (titles/summaries in {LANG_CODES}): {item_title}"
    
    for model_name in model_list:
        try:
            print(f"📡 Trying {model_name}...")
            res = client_ai.models.generate_content(model=model_name, contents=prompt)
            text = res.text.strip().replace("```json", "").replace("```", "")
            return json.loads(text)
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                print(f"⚠️ {model_name} quota hit, switching...")
                continue
            print(f"❌ {model_name} Error: {e}")
    return None

def run_bot():
    print(f"🚀 StyleMe Pro Engine Started.")
    live_models = get_live_models()
    budget = 0 # נטען דינמית בתוך הפונקציות במידת הצורך
    
    # Catch-up (Priority)
    try:
        pending = supabase.table('news').select("*").eq('needs_full_translation', True).limit(1).execute()
        if pending.data:
            item = pending.data[0]
            title_obj = item.get('titles', {})
            title = next(iter(title_obj.values())) if title_obj else "Update"
            print(f"🔄 Catching up: {title[:30]}")
            ai_data = analyze_and_translate_dynamic(title, 0, live_models)
            if ai_data:
                supabase.table('news').update({
                    "category": ai_data.get('category'), "titles": ai_data.get('titles'),
                    "summaries": ai_data.get('summaries'), "needs_full_translation": False
                }).eq('id', item['id']).execute()
    except Exception as e: print(f"Catch-up Error: {e}")

    # New Global Scan
    yesterday = (datetime.utcnow() - timedelta(days=1)).isoformat()
    try:
        recent = supabase.table('news').select('embedding').gte('created_at', yesterday).execute()
        existing_embs = [item['embedding'] for item in recent.data if item['embedding']]
    except: existing_embs = []

    items_to_publish = []
    tasks = [(f, "RSS") for f in random.sample(DIRECT_FEEDS, 6)] + [(t, "TOPIC") for t in random.sample(ALL_TOPICS, 15)]
    random.shuffle(tasks)

    for source, s_type in tasks:
        if len(items_to_publish) >= 15: break
        url = source if s_type == "RSS" else f"https://news.google.com/rss/search?q={urllib.parse.quote(source)}&hl=en-US&gl=US&ceid=US:en"
        try:
            resp = requests.get(url, timeout=12)
            feed = feedparser.parse(resp.content)
            for entry in feed.entries:
                if len(items_to_publish) >= 15: break
                if supabase.table('news').select("id").eq('source_url', entry.link).execute().data: continue

                try:
                    res_emb = client_ai.models.embed_content(model=EMBEDDING_MODEL, contents=entry.title)
                    new_vec = res_emb.embeddings[0].values
                    if any(cosine_similarity(new_vec, old) > 0.88 for old in existing_embs): continue
                except: new_vec = None

                ai_data = analyze_and_translate_dynamic(entry.title, 0, live_models)
                if ai_data:
                    items_to_publish.append({
                        "source_url": entry.link, "category": ai_data.get('category'),
                        "titles": ai_data.get('titles'), "summaries": ai_data.get('summaries'),
                        "embedding": new_vec, "needs_full_translation": False, "is_public": True
                    })
                else:
                    items_to_publish.append({
                        "source_url": entry.link, "titles": {"en": entry.title},
                        "embedding": new_vec, "needs_full_translation": True, "is_public": True
                    })
        except: continue

    if items_to_publish:
        for i, item in enumerate(items_to_publish):
            item["created_at"] = (datetime.utcnow() + timedelta(minutes=i*2)).isoformat()
            try: supabase.table('news').insert(item).execute()
            except: pass

if __name__ == "__main__":
    run_bot()
