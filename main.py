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

# הגדרות ביצועים
MAX_ITEMS_PER_RUN = 15 
WAIT_BETWEEN_AI = 10 
TASKS_PER_SESSION = 30 # הגדלתי את כמות המשימות הנדגמות לריצה

# === 20 מקורות RSS ישירים (מגזינים ופורטלים מובילים) ===
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
    "https://www.fibre2fashion.com/news/rss-feeds/fashion-news.xml",
    "https://www.thefashionlaw.com/feed/",
    "https://www.just-style.com/feed/",
    "https://www.fashion-history.com/feed",
    "https://www.insidefashion.com/feed",
    "https://www.fashionrevelation.com/feed",
    "https://www.sportswear-international.com/feed"
]

# === בנק 110 נושאים (The Intelligence Bank) ===
ALL_TOPICS = [
    # --- DESIGN & ART (עיצוב ואסתטיקה) ---
    "Avant-Garde Fashion Design Trends", "Haute Couture Craftsmanship News", "Runway Color Forecast 2026",
    "Minimalist Fashion Movement", "Cyberpunk & Techwear Aesthetics", "Sustainable Couture Techniques",
    "Bespoke Tailoring Industry News", "Womenswear Silhouette Innovation", "Footwear Sculpture & Design",
    "Knitwear Structure Innovation", "Luxury Bridal Market Trends", "Experimental Accessories Design",
    "Streetwear Subculture Research", "Vintage & Archival Fashion Market", "Costume Design & Cinema Art",
    "Fashion Illustration Modern Masters", "Emerging Designers Global Talent", "Textile Pattern Design Trends",
    "Gender-Neutral Fashion Design", "Artisanal Embroidery Techniques", "Deconstruction in Fashion Design",
    
    # --- TEXTILES & MATERIALS (טקסטיל וחומרים) ---
    "Smart Fabrics & Electronic Textiles", "Biodegradable Synthetic Fibers", "Recycled Ocean Plastic Textiles",
    "Spider Silk Bio-Engineering", "Mycelium & Mushroom Leather", "High-Performance Sportswear Fabrics",
    "Carbon Fiber Apparel Applications", "Nanotechnology in Textile Finishing", "Waterless Dyeing Technology",
    "Denim Indigo Weaving Innovations", "Merino Wool Sustainability Trends", "Cashmere Supply Chain Ethics",
    "Digital Inkjet Textile Printing", "Non-woven Medical Textiles", "Aerospace Grade Technical Fabrics",
    "Cotton Genetic Modification News", "Industrial Hemp Fiber Processing", "Antibacterial Fabric Innovation",
    "Fire-Retardant Textile Research", "Phase Change Materials in Clothing", "3D Weaving Technology News",
    
    # --- TECH & DIGITAL (טכנולוגיה ודיגיטל) ---
    "Generative AI in Apparel Design", "3D Body Modeling & Fit Tech", "Virtual Try-On UX Innovation",
    "Metaverse Luxury Collections", "Blockchain for Luxury Authentication", "NFT Fashion Assets Regulation",
    "Robotic Sewing & Assembly Lines", "Digital Product Passports Textiles", "Big Data in Fashion Retail",
    "AR-Powered Retail Experiences", "Artificial Intelligence Style Curators", "Fashion E-commerce Algorithm Trends",
    "Livestream Shopping Tech Global", "Interactive Garment QR Codes", "Smart Warehouse Logistics Fashion",
    
    # --- MARKET & ECONOMY (שוק וכלכלה) ---
    "Global Fashion Retail Growth 2026", "Luxury Sector Financial Outlook", "Apparel Supply Chain Resilience",
    "Raw Material Price Volatility", "Logistics Shipping Port Delays", "Air Freight Trends for Fashion",
    "Resale & Circular Economy Growth", "Clothing Rental Subscription Models", "Direct-to-Consumer Strategy News",
    "Department Store Revival Strategies", "Luxury Market in Southeast Asia", "Emerging Textile Hubs Ethiopia",
    "Post-Fast Fashion Business Models", "Merchandising Planning AI Software", "Impact of Inflation on Fashion",
    
    # --- SUSTAINABILITY & LAW (קיימות ורגולציה) ---
    "EU EPR Legislation for Textiles", "Fashion Carbon Footprint Metrics", "Water Scarcity in Textile Zones",
    "Fair Trade Labor Standards News", "Microplastic Filtration Solutions", "Supply Chain Traceability Software",
    "B-Corp Certified Fashion Brands", "Anti-Greenwashing Marketing Laws", "Regenerative Cotton Farming News",
    "Animal Welfare in Fashion Industry", "Zero-Waste Pattern Making Tech", "Chemical Safety in Textile Dyeing",
    "Fashion Intellectual Property Law", "Copyright Protection for Designs", "Counterfeit Detection Technology"
]

def get_with_ua(url):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36'}
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

    prompt = f"Summarize this industry news in HEBREW (2 professional sentences) and pick ONE category (TRENDS, MARKET, TECH, LOGISTICS, REGULATION): {item.title}"
    
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
        if "429" in str(e): return "STOP"
        return "FAIL"

def run_bot():
    print(f"🚀 StyleMe PRO: Total Intelligence Engine Started at {datetime.now()}")
    collected_intel = []

    # הגרלת משימות מהבנק העצום
    random_topics = random.sample(ALL_TOPICS, min(TASKS_PER_SESSION // 2, len(ALL_TOPICS)))
    random_feeds = random.sample(DIRECT_FEEDS, min(TASKS_PER_SESSION // 2, len(DIRECT_FEEDS)))
    
    tasks = [(f, "RSS") for f in random_feeds] + [(t, "TOPIC") for t in random_topics]
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
            url = f"https://news.google.com/rss/search?q={urllib.parse.quote(source)}+when:7d&hl=en-US&gl=US&ceid=US:en"
            content = get_with_ua(url)
            if content:
                feed = feedparser.parse(content)
                for item in feed.entries[:2]:
                    status = analyze_item(item, collected_intel)
                    if status in ["MAX", "STOP"]: break
        
        if status == "STOP": 
            print("🛑 API Quota Limit. Moving to publish phase.")
            break

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
