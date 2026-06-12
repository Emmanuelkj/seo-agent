import os
import json
import time
from google import genai
from google.genai import types
from google.genai.errors import APIError

def analyze_content_ai(title: str, description: str, text_sample: str) -> dict:
    """
    Uses Gemini to analyze the text sample for Search Intent 
    and automatically generate JSON-LD schema markup.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return {"intent": "Unknown (No API Key)", "schema": ""}
        
    client = genai.Client(api_key=api_key)
    
    system_instruction = (
        "You are an expert SEO specialist. Analyze the provided webpage content. "
        "1. Identify the Search Intent (Informational, Navigational, Transactional, or Commercial). "
        "2. Generate appropriate JSON-LD Schema.org markup (e.g., Article, FAQPage, or LocalBusiness) based on the content. "
        "Return the result as a raw JSON object with exactly two keys: 'intent' (a string) and 'schema' (the raw JSON-LD schema code as a string). "
        "Do not use markdown blocks, return ONLY valid JSON."
    )
    
    prompt = f"Title: {title}\nDescription: {description}\nContent Sample: {text_sample}"
    
    max_retries = 3
    base_delay = 5
    
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.1,
                    response_mime_type="application/json",
                )
            )
            
            result_text = response.text.strip()
            data = json.loads(result_text)
            return {
                "intent": data.get("intent", "Unknown"),
                "schema": data.get("schema", "")
            }
        except APIError as e:
            if e.code in [429, 503] and attempt < max_retries - 1:
                sleep_time = base_delay * (2 ** attempt)
                print(f"AI API busy (Error {e.code}). Retrying in {sleep_time}s...")
                time.sleep(sleep_time)
            else:
                print(f"AI Analysis Failed: {e}")
                return {"intent": "Error during AI analysis", "schema": ""}
        except Exception as e:
            print(f"AI Analysis Failed: {e}")
            return {"intent": "Error during AI analysis", "schema": ""}
            
    return {"intent": "Error during AI analysis", "schema": ""}
