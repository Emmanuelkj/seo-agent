import requests
from bs4 import BeautifulSoup
import re
import textstat
from .ai_seo import analyze_content_ai

def scrape_local_seo(url: str) -> dict:
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        response_time = response.elapsed.total_seconds()
    except Exception as e:
        return {"error": str(e)}

    soup = BeautifulSoup(response.text, "html.parser")
    
    title_tag = soup.title
    title = title_tag.string.strip() if title_tag and title_tag.string else None
    
    meta_desc = soup.find("meta", attrs={"name": "description"})
    description = meta_desc["content"] if meta_desc and "content" in meta_desc.attrs else None
    
    canonical_tag = soup.find("link", rel="canonical")
    has_canonical = canonical_tag is not None
    
    html_tag = soup.find("html")
    has_lang = html_tag and html_tag.has_attr("lang")
    
    images = soup.find_all("img")
    missing_alt_images = [img.get("src", "") for img in images if not img.get("alt")]
    
    text = soup.get_text(separator=" ")
    word_count = len(re.findall(r'\b\w+\b', text))
    
    readability_score = textstat.flesch_reading_ease(text)
    
    text_sample = text[:3000]
    ai_insights = analyze_content_ai(title or "", description or "", text_sample)
    
    headings = {
        "h1": len(soup.find_all("h1")),
        "h2": len(soup.find_all("h2")),
        "h3": len(soup.find_all("h3")),
        "h4": len(soup.find_all("h4")),
        "h5": len(soup.find_all("h5")),
        "h6": len(soup.find_all("h6")),
    }
    
    semantic_tags = {
        "main": len(soup.find_all("main")) > 0,
        "nav": len(soup.find_all("nav")) > 0,
        "header": len(soup.find_all("header")) > 0,
        "footer": len(soup.find_all("footer")) > 0,
    }

    # CALCULATE CUSTOM ON-PAGE SCORES
    
    # 1. Meta Score (Max 100)
    meta_score = 0
    if title:
        meta_score += 40 if 30 <= len(title) <= 65 else 20
    if description:
        meta_score += 40 if 120 <= len(description) <= 165 else 20
    if has_canonical: meta_score += 10
    if has_lang: meta_score += 10
        
    # 2. Quality Score (Max 100)
    quality_score = 0
    if word_count > 300: quality_score += 50
    elif word_count > 100: quality_score += 25
    if len(missing_alt_images) == 0: quality_score += 30
    if readability_score > 40: quality_score += 20
        
    # 3. Structure Score (Max 100)
    structure_score = 0
    if headings["h1"] == 1: structure_score += 40
    elif headings["h1"] > 1: structure_score += 20
    if headings["h2"] > 0: structure_score += 30
    semantic_count = sum(1 for v in semantic_tags.values() if v)
    structure_score += min(30, semantic_count * 10)
    
    # 4. Server Score (Max 100)
    server_score = 100
    if response_time > 2.0: server_score = 40
    elif response_time > 1.0: server_score = 70
    elif response_time > 0.5: server_score = 90
    
    # Aggregate On-Page Score
    on_page_score = int((meta_score + quality_score + structure_score + server_score) / 4)
    
    return {
        "title": title,
        "description": description,
        "word_count": word_count,
        "images_missing_alt": missing_alt_images,
        "images_missing_alt_count": len(missing_alt_images),
        "response_time": response_time,
        "headings": headings,
        "readability_score": readability_score,
        "search_intent": ai_insights.get("intent", "Unknown"),
        "schema_markup_suggestion": ai_insights.get("schema", ""),
        "seobility_scores": {
            "on_page_score": on_page_score,
            "meta_data": meta_score,
            "page_quality": quality_score,
            "page_structure": structure_score,
            "server": server_score
        }
    }
