import os
import time
import feedparser
import google.generativeai as genai
from supabase import create_client
import urllib.parse

# קריאת המפתחות מהסביבה המאובטחת של גיטהאב
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

# הגדרות
genai.configure(api_key=GEMINI_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
TOPICS = ["Textile Supply Chain", "Cotton Prices", "Fashion Tech", "Sustainable Fashion EU", "Textile Automation"]

def get_google_news_url(query):
    encoded = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={encoded}+when:1d&hl=en-US&gl=US&ceid=US:en"

RSS_FEEDS = [get_google_news_url(t) for t in TOPICS]

def run_bot():
    print("🚀 Bot started...")
    # בחירת מודל
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        model = genai.GenerativeModel(models[0])
    except:
        model = genai.GenerativeModel('gemini-pro')

    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            if not feed.entries: continue
            item = feed.entries[0]

            # בדיקת כפילות
            existing = supabase.table('news').select("*").eq('title', item.title).execute()
            if existing.data: continue

            print(f"New item: {item.title[:20]}...")
            time.sleep(5) # השהייה קצרה

            prompt = f"""
            Analyze for fashion exec. Summarize in Hebrew (max 2 sentences).
            Categorize: LOGISTICS, MATERIALS, REGULATION, TECH, MARKET.
            Format: Category: [CAT]\nSummary: [HEBREW]
            News: {item.title}\nLink: {item.link}
            """
            res = model.generate_content(prompt)
            text = res.text
            
            category = "GLOBAL"
            content = text
            if "Category:" in text:
                parts = text.split("Summary:")
                category = parts[0].replace("Category:", "").strip()
                content = parts[1].strip()

            supabase.table('news').insert({
                "title": item.title,
                "content": content,
                "category": category,
                "source_url": item.link,
                "is_public": True
            }).execute()
            print("✅ Saved.")
            
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    run_bot()
