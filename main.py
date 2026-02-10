import os
import time
import feedparser
from google import genai
from supabase import create_client
import urllib.parse
from datetime import datetime, timedelta
import random
import requests

# --- הגדרות מערכת ---
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

client_ai = genai.Client(api_key=GEMINI_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# הגדרות בטיחות (Quota & Content)
MAX_ITEMS_PER_RUN = 15  # כמות מכובדת לכל חצי שעה
WAIT_BETWEEN_AI = 10    # השהייה בסיסית למניעת חסימה
RUN_INTERVAL_MINUTES = 29

# --- בנק נושאים ענק (ללא מותגים) ---
ALL_TOPICS = [
    # עיצוב ואמנות
    "Fashion Design Trends 2026", "Haute Couture Innovation", "Runway Collection Analysis",
    "Avant-Garde Design Trends", "Streetwear Design Evolution", "Menswear Style Forecast",
    "Womenswear Silhouette Trends", "Bridal Fashion Industry News", "Footwear Design Innovation",
    "Activewear Material Trends", "Knitwear Design Techniques", "Lingerie Industry Trends",
    
    # טקסטיל וחומרים
    "Sustainable Textile Technology", "Fabric Material Science News", "Smart Fabrics Wearables",
    "Recycled Polyester Innovation", "Organic Cotton Market Trends", "Bio-Engineered Textiles",
    "Future of Silk Production", "Eco-friendly Dyeing Processes", "Non-woven Fabric Innovation",
    "Denim Manufacturing Technology", "Leather Alternative Materials", "Technical Textiles Market",
    
    # טכנולוגיה וחדשנות
    "AI in Fashion Manufacturing", "3D Printing Garments", "Digital Fashion Metaverse",
    "Virtual Fitting Room Tech", "Automated Sewing Machines AI", "Fashion Supply Chain Blockchain",
    "On-Demand Apparel Production", "Digital Product Passport Textiles", "Fashion E-commerce Tech",
    
    # שוק ועסקים
    "Global Apparel Market Analysis", "Luxury Fashion Economic Outlook", "Textile Import Export Tariffs",
    "Fashion Logistics Challenges", "Retail Inventory Management Tech", "Apparel Sourcing Vietnam Bangladesh",
    "Textile Raw Material Price Trends", "Global Shipping Freight Rates Textile",
    "Circular Economy Fashion Business", "Ethical Labor Standards Apparel",
    
    # אירועים ותערוכות
    "Global Textile Trade Shows", "Fashion Week Industry Highlights", "Textile Innovation Awards",
    "Emerging Designer Competitions", "Fashion Business Conferences", "Textile Expo Worldwide",
    "Museum Fashion Exhibitions", "Costume Design Industry News"
]

DIRECT_FEEDS = [
    "https://www.businessoffashion.com/feeds/rss/",
    "https://www.voguebusiness.com/feed",
    "https://wwd.com/feed/",
    "https://www.fashionunited.com/rss-feed",
    "https://www.textileworld.com/feed/",
    "https://www.fashionnetwork.com/rss/feed.xml"
]

def get_with_ua(url):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    try:
        response = requests.get(url, headers=headers, timeout=20)
        return response.content
    except: return None

def analyze_item(item, collected_intel):
    if len(collected_intel) >= MAX_ITEMS_PER_RUN: return "MAX"
    if any(c['title'] == item.title for c in collected_intel): return "DUP"
    
    try:
        existing = supabase.table('news').select("id").eq('title', item.title).execute()
        if existing.data: return "EXISTS"
    except: pass

    print(f"   ✨ Analyzing: {item.title[:45]}...")
    time.sleep(WAIT_BETWEEN_AI)

    prompt = f"Summarize this fashion news in HEBREW (2 professional sentences) and pick ONE category (TRENDS, MARKET, TECH, LOGISTICS, REGULATION): {item.title}"
    
    # מנגנון ניסיון חוזר חכם
    for attempt in range(3):
        try:
            res = client_ai.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            text = res.text
            
            category = "TRENDS"
            for cat in ['MARKET', 'TECH', 'LOGISTICS', 'REGULATION']:
                if cat in text.upper(): category = cat

            collected_intel.append({
                "title": item.title, "content": text.replace("**", "").strip(),
                "category": category, "source_url": item.link, "likes": 0, "is_public": True
            })
            print(f"      ✅ Success.")
            return "OK"
        except Exception as e:
            if "429" in str(e):
                wait_time = 30 * (attempt + 1)
                print(f"      🛑 Quota exceeded. Sleeping {wait_time}s...")
                time.sleep(wait_time)
            else:
                print(f"      ❌ AI Error: {e}")
                break
    return "FAIL"

def run_bot():
    print(f"🚀 StyleMe PRO: Mega-Bulldozer Started at {datetime.now()}")
    collected_intel = []

    # איסוף מכל המקורות
    sources = [(f, "RSS") for f in DIRECT_FEEDS] + [(t, "TOPIC") for t in ALL_TOPICS]
    random.shuffle(sources)

    for source, s_type in sources:
        if len(collected_intel) >= MAX_ITEMS_PER_RUN: break
        
        if s_type == "RSS":
            content = get_with_ua(source)
            if content:
                feed = feedparser.parse(content)
                for item in feed.entries[:3]:
                    if analyze_item(item, collected_intel) == "MAX": break
        else:
            encoded = urllib.parse.quote(source)
            url = f"https://news.google.com/rss/search?q={encoded}+when:7d&hl=en-US&gl=US&ceid=US:en"
            content = get_with_ua(url)
            if content:
                feed = feedparser.parse(content)
                for item in feed.entries[:2]:
                    if analyze_item(item, collected_intel) == "MAX": break

    # הפצה
    if not collected_intel:
        print("😴 No new items processed.")
        return

    print(f"--- Publishing {len(collected_intel)} items ---")
    interval = RUN_INTERVAL_MINUTES / len(collected_intel) if len(collected_intel) > 1 else 1
    base_time = datetime.utcnow()

    for i, news in enumerate(collected_intel):
        news['created_at'] = (base_time + timedelta(minutes=i*interval)).isoformat()
        try:
            supabase.table('news').insert(news).execute()
            print(f"   ✅ Published: {news['title'][:30]}")
        except Exception as e: print(f"❌ DB Error: {e}")

if __name__ == "__main__":
    run_bot()
