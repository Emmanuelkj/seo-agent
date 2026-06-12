import os
import httpx

async def fetch_pagespeed_seo(url: str) -> dict:
    api_key = os.getenv("PAGESPEED_API_KEY")
    if not api_key:
        return {"error": "PAGESPEED_API_KEY is missing from environment variables"}

    api_url = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
    params = {
        "url": url,
        "category": "seo",
        "key": api_key
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(api_url, params=params, timeout=60.0)
            
            # If Google rejects the request, intercept their exact JSON error message
            if response.status_code != 200:
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error", {}).get("message", f"HTTP {response.status_code}")
                    return {"error": f"Google API Error: {error_msg}"}
                except Exception:
                    return {"error": f"HTTP {response.status_code}: Could not read Google's error response."}
            
            data = response.json()
            
            if "lighthouseResult" not in data:
                return {"error": "Response does not contain a 'lighthouseResult'"}
                
            # Extract the overall score
            raw_score = data["lighthouseResult"]["categories"]["seo"]["score"]
            final_score = int(raw_score * 100) if raw_score is not None else 0
            
            # Extract specific warnings
            audits = data["lighthouseResult"]["audits"]
            seo_refs = data["lighthouseResult"]["categories"]["seo"]["auditRefs"]
            
            specific_warnings = []
            for ref in seo_refs:
                audit_id = ref["id"]
                audit_data = audits.get(audit_id, {})
                score = audit_data.get("score")
                
                if score is not None and score < 1:
                    specific_warnings.append(audit_data.get("title", f"Fix issue: {audit_id}"))
            
            return {
                "pagespeed_seo_score": final_score,
                "specific_warnings": specific_warnings
            }
            
        except httpx.ReadTimeout:
            return {"error": "Google PageSpeed API timed out (took longer than 60 seconds)."}
        except Exception as e:
            return {"error": f"Internal Python Error: {repr(e)}"}