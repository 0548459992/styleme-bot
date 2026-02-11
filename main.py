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

client_ai = genai.Client(api_key=GEMINI_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# רשימת 20 השפות
LANG_CODES = ["he", "en", "it", "fr", "zh", "es", "de", "tr", "vi", "bn", "hi", "id", "ja", "ko", "ar", "ru", "pl", "nl", "sv", "pt"]

# --- בנק המקורות והנושאים העצום ---
DIRECT_FEEDS = [
    "https://www.businessoffashion.com/feeds/rss/", "https://www.voguebusiness.com/feed",
    "https://wwd.com/feed/", "https://www.fashionunited.com/rss-feed",
    "https://www.textileworld.com/feed/", "https://www.fashionnetwork.com/rss/feed.xml",
    "https://hypebeast.com/feed", "https://www.apparelresources.com/feed/",
    "https://www.thefashionlaw.com/feed/", "https://www.ecotextile.com/news?format=feed&type=rss"
]

ALL_TOPICS = [
    "Sustainable Textile Innovation", "AI in Fashion Manufacturing", "Luxury Market Analysis 2026",
    "Smart Fabrics Wearables", "Circular Fashion Economy", "Milan Fashion Week Design",
    "Recycled Ocean Plastic Textiles", "Robotic Sewing Assembly", "Digital Product Passports",
    "Mycelium Leather Research", "Textile Raw Material Prices", "Global Apparel Logistics"
    # (כאן ייכנסו כל ה-110 נושאים שנתתי לך קודם)
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
    # קביעת "הילוך" לפי תקציב
    if budget < 800:
        target_langs = LANG_CODES
        needs_more = False
    elif budget < 1300:
        target_langs = ["he", "en", "it", "fr", "zh", "tr"]
        needs_more = True
    else: return None, True

    prompt = f"""
    Analyze this news: {item.title}
    1. Categorize: TRENDS, MARKET, TECH, LOGISTICS, REGULATION.
    2. Summarize in 2 professional sentences for each language code: {', '.join(target_langs)}.
    Return ONLY a valid JSON:
    {{
      "category": "...",
      "titles": {{"he": "...", "en": "...", ...}},
      "summaries": {{"he": "...", "en": "...", ...}}
    }}
    """
    try:
        res = client_ai.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        clean_json = res.text.strip().replace("```json", "").replace("```", "")
        return json.loads(clean_json), needs_more
    except: return None, True

def run_bot():
    budget = get_ai_budget()
    print(f"🚀 StyleMe Global Engine. Budget: {budget}/1500")
    
    collected_intel = []
    # בוחרים 15 משימות אקראיות מתוך הבנק הענק
    tasks = [(f, "RSS") for f in random.sample(DIRECT_FEEDS, 5)] + \
            [(t, "TOPIC") for t in random.sample(ALL_TOPICS, 10)]
    random.shuffle(tasks)

    for source, s_type in tasks:
        if len(collected_intel) >= 12: break
        
        # בחיפוש נושאים - מתרגמים את הנושא לשפה אקראית כדי לקבל תוצאות מקומיות
        if s_type == "TOPIC":
            search_lang = random.choice(["en", "it", "fr", "zh", "tr"])
            url = f"https://news.google.com/rss/search?q={urllib.parse.quote(source)}&hl={search_lang}&gl={search_lang.upper()}&ceid={search_lang.upper()}:en"
        else:
            url = source

        try:
            resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
            feed = feedparser.parse(resp.content)
            for entry in feed.entries[:2]:
                if len(collected_intel) >= 12: break
                
                # בדיקת כפילות
                existing = supabase.table('news').select("id").eq('source_url', entry.link).execute()
                if existing.data: continue

                ai_data, needs_more = analyze_multilingual(entry, budget)
                
                if ai_data:
                    supabase.table('news').insert({
                        "source_url": entry.link,
                        "category": ai_data.get('category'),
                        "titles": ai_data.get('titles'),
                        "summaries": ai_data.get('summaries'),
                        "needs_full_translation": needs_more
                    }).execute()
                    update_ai_budget(1)
                    budget += 1
                    collected_intel.append(entry.link)
                    print(f"✅ Published (Multi): {entry.title[:30]}")
                else:
                    supabase.table('news').insert({
                        "source_url": entry.link,
                        "titles": {"en": entry.title},
                        "needs_full_translation": True
                    }).execute()
                    print(f"📝 Raw Save: {entry.title[:30]}")
        except: continue

if __name__ == "__main__":
    run_bot()
