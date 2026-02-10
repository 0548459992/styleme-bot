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

# הגדרות ריצה (ביצועים מול עושר תוכן)
MAX_ITEMS_PER_RUN = 18 
WAIT_BETWEEN_AI = 7
TOPICS_PER_SESSION = 15 # כמה נושאים להגריל בכל ריצה

# === בנק המקורות הישירים (מגזינים מובילים) ===
DIRECT_FEEDS = [
    "https://www.businessoffashion.com/feeds/rss/",
    "https://www.voguebusiness.com/feed",
    "https://wwd.com/feed/",
    "https://www.fashionunited.com/rss-feed",
    "https://www.textileworld.com/feed/",
    "https://www.fashionnetwork.com/rss/feed.xml",
    "https://hypebeast.com/feed",
    "https://www.apparelresources.com/feed/",
    "https://www.drapersonline.com/feed",
    "https://www.glossy.co/feed",
    "https://www.fashiondive.com/feeds/news/",
    "https://www.ecotextile.com/news?format=feed&type=rss",
    "https://knittingindustry.com/feed/",
    "https://www.fibre2fashion.com/news/rss-feeds/fashion-news.xml"
]

# === בנק הנושאים העצום (80 נושאים) ===
ALL_TOPICS = [
    # עיצוב ואסתטיקה
    "Avant-Garde Fashion Design", "Haute Couture Collections", "Runway Trends 2026",
    "Minimalist Fashion Aesthetics", "Cyberpunk Fashion Trends", "Sustainable Design Methods",
    "Menswear Tailoring Innovation", "Womenswear Silhouettes Forecast", "Footwear Design Sculpture",
    "Knitwear Texture Innovation", "Bridal Wear Industry Trends", "Childrenswear Market Design",
    "Accessories and Jewelry Design Trends", "Streetwear Subculture Trends", "Vintage Revival Fashion",
    "Costume Design for Film News", "Color Theory in Fashion Design", "Fashion Illustration Masters",
    "Emerging Designers Global Showcase", "Fashion Design Awards Innovation",
    
    # טקסטיל וחומרים
    "Smart Fabrics and Interactive Textiles", "Biodegradable Textile Science", "Recycled Ocean Plastic Fabrics",
    "Spider Silk Textile Innovation", "Mycelium Leather Research", "High-Tech Sportswear Materials",
    "Carbon Fiber Textiles", "Nanotechnology in Fabrics", "Sustainable Dyeing Technology",
    "Denim Weaving Innovation", "Wool Industry Quality Trends", "Luxury Cashmere Market",
    "Digital Textile Printing Progress", "Non-woven Fabric Applications", "Technical Textiles for Aerospace",
    "Cotton Genetic Engineering News", "Linen Production Sustainability", "Textile Finishing Innovation",
    
    # טכנולוגיה ודיגיטל
    "AI-Generated Fashion Design", "3D Body Scanning Fashion", "Virtual Fitting Room UX",
    "Metaverse Fashion Collections", "NFT Luxury Goods Authentication", "Blockchain Supply Chain Textiles",
    "Robotic Garment Assembly", "Digital Product Passports EU", "AI Style Personalization Tech",
    "E-commerce AR Shopping Experience", "Smart Mirrors Retail Tech", "Fashion Data Analytics Trends",
    
    # שוק, כלכלה ולוגיסטיקה
    "Global Fashion Retail Outlook", "Luxury Market Economics 2026", "Apparel Supply Chain Resilience",
    "Textile Raw Material Inflation", "Shipping Port Crisis Fashion", "Last Mile Delivery Apparel",
    "Resale and Second-hand Market Growth", "Rental Fashion Business Models", "Fast Fashion Environmental Impact",
    "Circular Fashion Business Strategy", "Fashion Merchandising AI Tools", "Global Trade Tariffs Textiles",
    "Apparel Sourcing Strategy Vietnam", "Textile Hubs Expansion Turkey", "India Apparel Export Growth",
    
    # קיימות ורגולציה
    "EU Textile Waste Directives", "Fashion Industry Carbon Neutrality", "Water Conservation in Textiles",
    "Ethical Labor Practices Apparel", "Microplastic Shedding Solutions", "Transparency in Fashion Supply",
    "B-Corp Fashion Brands News", "Greenwashing Regulations Global", "Regenerative Agriculture Cotton",
    "Social Responsibility Fashion Industry", "Traceability Technology Fabrics"
]

def get_with_ua(url):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    try:
        response = requests.get(url, headers=headers, timeout=15)
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

    prompt = f"Summarize this fashion industry news in HEBREW (2 professional sentences) and pick ONE category (TRENDS, MARKET, TECH, LOGISTICS, REGULATION): {item.title}"
    
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
        print("      ✅ OK.")
        return "OK"
    except Exception as e:
        if "429" in str(e):
            print("      🛑 Quota Exceeded. Finalizing batch.")
            return "STOP"
        return "FAIL"

def run_bot():
    print(f"🚀 StyleMe PRO: Mega-Bulldozer Started at {datetime.now()}")
    collected_intel = []

    # הגרלת נושאים לריצה הנוכחית
    random_topics = random.sample(ALL_TOPICS, min(TOPICS_PER_SESSION, len(ALL_TOPICS)))
    
    # בניית רשימת המשימות
    tasks = [(f, "RSS") for f in DIRECT_FEEDS] + [(t, "TOPIC") for t in random_topics]
    random.shuffle(tasks)

    for source, s_type in tasks:
        if len(collected_intel) >= MAX_ITEMS_PER_RUN: break
        
        if s_type == "RSS":
            print(f"📡 RSS: {source[:40]}...")
            content = get_with_ua(source)
            if content:
                feed = feedparser.parse(content)
                for item in feed.entries[:2]:
                    status = analyze_item(item, collected_intel)
                    if status in ["MAX", "STOP"]: break
        else:
            print(f"🔎 Search: {source}...")
            encoded = urllib.parse.quote(source)
            url = f"https://news.google.com/rss/search?q={encoded}+when:7d&hl=en-US&gl=US&ceid=US:en"
            content = get_with_ua(url)
            if content:
                feed = feedparser.parse(content)
                for item in feed.entries[:2]:
                    status = analyze_item(item, collected_intel)
                    if status in ["MAX", "STOP"]: break
        
        if status == "STOP": break

    if not collected_intel:
        print("😴 No new items found.")
        return

    print(f"--- Publishing {len(collected_intel)} items ---")
    interval = 28 / len(collected_intel) if len(collected_intel) > 1 else 1
    base_time = datetime.utcnow()

    for i, news in enumerate(collected_intel):
        news['created_at'] = (base_time + timedelta(minutes=i*interval)).isoformat()
        try:
            supabase.table('news').insert(news).execute()
            print(f"   ✅ Published: {news['title'][:30]}")
        except: pass

if __name__ == "__main__":
    run_bot()
