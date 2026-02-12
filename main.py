import sys
import time
import os
import json
import random
import re
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

# --- הגדרות תוכן ---
LANG_CODES = ["he", "en", "it", "fr", "es", "de", "jp"]

DIRECT_FEEDS = [
    "https://www.businessoffashion.com/feeds/rss/",
    "https://www.voguebusiness.com/feed",
    "https://wwd.com/feed/",
    "https://www.fashionunited.com/rss-feed",
    "https://www.fashionnetwork.com/rss/feed.xml"
]

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

def extract_json_smart(text):
    """מחלץ JSON נקי גם אם המודל הוסיף מחשבות או טקסט נוסף"""
    try:
        # ניסיון ראשון: פענוח ישיר
        return json.loads(text)
    except:
        try:
            # ניסיון שני: חיפוש הסוגריים המסולסלים החיצוניים
            start = text.find('{')
            end = text.rfind('}') + 1
            if start != -1 and end != -1:
                clean_text = text[start:end]
                return json.loads(clean_text)
            return None
        except:
            return None

def analyze_with_flash(item_title):
    """ניתוח מהיר עם המודל היציב ביותר"""
    prompt = f"""
    Act as a Fashion Editor. Analyze this news title: "{item_title}".
    Return a JSON object ONLY with:
    1. "category": One specific fashion category (e.g., "Textile Innovation", "Luxury Business").
    2. "titles": Translated title in {LANG_CODES}.
    3. "summaries": A 2-sentence summary in {LANG_CODES}.
    
    IMPORTANT: Return ONLY the JSON. Do not include markdown code blocks.
    """
    
    # שימוש ברשימת מודלים קשיחה ויציבה
    models_to_try = ["gemini-2.0-flash", "gemini-1.5-flash"]
    
    for model in models_to_try:
        try:
            print(f"⚡ Analyzing with {model}...")
            response = client_ai.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            
            data = extract_json_smart(response.text)
            if data:
                return data
                
        except Exception as e:
            print(f"⚠️ Model {model} error: {e}")
            continue
            
    return None

def run_archive_and_cleanup():
    print("🧹 Running Maintenance...")
    now = datetime.utcnow()
    try:
        # ניקוי כתבות ישנות מאוד (שנה אחורה)
        one_year_ago = (now - timedelta(days=365)).isoformat()
        supabase.table('news').delete().lt('created_at', one_year_ago).execute()
        
        # ניקוי כתבות שנתקעו במצב טיוטה יותר מ-24 שעות
        limit_24h = (now - timedelta(days=1)).isoformat()
        supabase.table('news').delete().eq('needs_full_translation', True).lt('created_at', limit_24h).execute()
    except: pass

def run_bot():
    print(f"🚀 StyleMe Pro Engine Active - {datetime.utcnow()}")
    run_archive_and_cleanup()

    # --- יצירת רשימת משימות מעורבת ---
    # לוקחים קצת מ-RSS וקצת מנושאים כלליים
    tasks = []
    
    # 1. RSS Feeds (עד 6 מקורות רנדומליים)
    rss_samples = random.sample(DIRECT_FEEDS, min(len(DIRECT_FEEDS), 6))
    for f in rss_samples:
        tasks.append((f, "RSS"))
        
    # 2. Google News Topics (עד 10 נושאים רנדומליים)
    topic_samples = random.sample(ALL_TOPICS, min(len(ALL_TOPICS), 10))
    for t in topic_samples:
        tasks.append((t, "TOPIC"))
        
    random.shuffle(tasks)
    items_published = 0

    for source, s_type in tasks:
        if items_published >= 10: break # מגבלה כדי לא להעמיס על הריצה
        
        url = source if s_type == "RSS" else f"https://news.google.com/rss/search?q={urllib.parse.quote(source)}&hl=en-US&gl=US&ceid=US:en"
        
        try:
            print(f"📥 Fetching: {source[:40]}...")
            resp = requests.get(url, timeout=10)
            feed = feedparser.parse(resp.content)
            
            # לוקחים רק את הכתבה הראשונה מכל מקור כדי לגוון
            for entry in feed.entries[:1]:
                if items_published >= 10: break
                
                # בדיקת כפילויות
                exists = supabase.table('news').select("id").eq('source_url', entry.link).execute()
                if exists.data:
                    print("🔹 Skipping duplicate.")
                    continue

                # שליחה לניתוח
                ai_data = analyze_with_flash(entry.title)
                
                if ai_data:
                    item = {
                        "source_url": entry.link,
                        "category": ai_data.get('category', 'General'),
                        "titles": ai_data.get('titles', {}),
                        "summaries": ai_data.get('summaries', {}),
                        "needs_full_translation": False,
                        "is_public": True,
                        "missing_reports": 0,
                        "retry_count": 0,
                        "created_at": datetime.utcnow().isoformat()
                    }
                    supabase.table('news').insert(item).execute()
                    print(f"✅ Published: {entry.title[:30]}")
                    items_published += 1
                    time.sleep(2) # השהייה קטנה למנוע עומס
                else:
                    print("❌ AI Analysis failed.")
                    
        except Exception as e:
            print(f"⚠️ Feed error: {e}")
            continue

if __name__ == "__main__":
    run_bot()
