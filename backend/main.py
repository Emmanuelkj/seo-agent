import os
import asyncio
import uuid
from dotenv import load_dotenv
from fastapi import BackgroundTasks
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
from pydantic import BaseModel

# 1. LOAD ENVIRONMENT VARIABLES FIRST
load_dotenv()

# 2. NOW IMPORT INTERNAL SERVICES
from services.local_scraper import scrape_local_seo
from services.pagespeed_api import fetch_pagespeed_seo
from services.github_manager import create_seo_pull_request, get_github_html_files
from services.crawler import find_all_internal_links
from urllib.parse import urlparse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

try:
    supabase: Client = create_client(url, key) if url and key else None
except Exception as e:
    supabase = None
    print("Failed to initialize Supabase:", e)

# --- PYDANTIC MODELS ---

class AuditRecord(BaseModel):
    target_url: str
    overall_score: float | None = None
    response_time: float | None = None
    issues_found: dict | None = None
    pr_url: str | None = None

class AuditRequest(BaseModel):
    target_url: str

class FixRequest(BaseModel):
    target_url: str
    errors: dict

class CrawlRequest(BaseModel):
    base_url: str


# --- BACKGROUND WORKER LOGIC ---

completed_batches = set()

async def process_site_crawl(base_url: str, batch_id: str):
    print(f"🚀 Starting Site Crawl for: {base_url} (Batch: {batch_id})")
    
    # 1. Map out the website
    crawler_data = await find_all_internal_links(base_url, max_pages=100) # Keeping at 100 for safe testing
    urls_to_audit = crawler_data["urls"]
    pagerank_scores = crawler_data["pagerank"]
    
    # 1.5 Cross-reference with GitHub to drop Soft 404s
    REPO_MAPPING = {
        "https://novoxcore.com/": "Emmanuelkj/seo-agent-test",
        "https://www.cinescape.com.kw/": "your-username/cinescape-web"
    }
    parsed = urlparse(base_url)
    base_domain = f"{parsed.scheme}://{parsed.netloc}/"
    repo_name = REPO_MAPPING.get(base_domain) or REPO_MAPPING.get(base_url)
    
    if repo_name:
        print(f"[SEARCH] Cross-referencing discovered pages against GitHub Repo: {repo_name}...")
        github_files = get_github_html_files(repo_name)
        if github_files:
            valid_urls = []
            seen_github_paths = set()
            
            for url in urls_to_audit:
                path = urlparse(url).path.lstrip('/')
                if not path or path == "":
                    path = "index.html"
                elif not path.endswith('.html'):
                    # Handle clean URLs (e.g., /about -> about.html or about/index.html)
                    if f"{path}.html" in github_files:
                        path = f"{path}.html"
                    elif f"{path}/index.html" in github_files:
                        path = f"{path}/index.html"
                
                if path in github_files:
                    # DEDUPLICATION: Only audit each physical GitHub file ONCE!
                    if path not in seen_github_paths:
                        valid_urls.append(url)
                        seen_github_paths.add(path)
                    else:
                        print(f"[DROP] Duplicate mapping for {path}: {url}")
                else:
                    print(f"[DROP] Dropping ghost page (not in GitHub): {url}")
            
            urls_to_audit = valid_urls

    print(f"📋 Found {len(urls_to_audit)} verified pages. Beginning deep-dive audits...")

    # 2. Audit each page one by one
    for target_url in urls_to_audit:
        print(f"⏳ Auditing: {target_url}")
        
        try:
            # Run our existing logic
            scraper_task = asyncio.to_thread(scrape_local_seo, target_url)
            pagespeed_task = asyncio.create_task(fetch_pagespeed_seo(target_url))
            scraper_result, pagespeed_result = await asyncio.gather(scraper_task, pagespeed_task)
            
            # Save directly to Supabase
            if supabase:
                pr_score = pagerank_scores.get(target_url, 0)
                seobility_score = scraper_result.get("seobility_scores", {}).get("on_page_score", 0)
                ps_score = pagespeed_result.get("pagespeed_seo_score", 0)
                final_score = int((seobility_score + ps_score) / 2) if ps_score > 0 else seobility_score
                
                db_record = {
                    "target_url": target_url,
                    "overall_score": final_score,
                    "response_time": scraper_result.get("response_time", 0),
                    "issues_found": {"local": scraper_result, "pagespeed": pagespeed_result, "pagerank_score": pr_score},
                    "batch_id": batch_id 
                }
                supabase.table("seo_audits").insert(db_record).execute()
                print(f"✅ Saved to database: {target_url}")
                
        except Exception as e:
            print(f"❌ Failed to process or save {target_url}: {e}")
        
        # 3. THE RATE LIMITER: Wait 10 seconds before hitting Google PageSpeed and Gemini again
        await asyncio.sleep(10) 
        
    completed_batches.add(batch_id)
    print(f"🎉 Crawl Job {batch_id} Complete!")


# --- API ENDPOINTS ---

@app.get("/api/health")
def health_check():
    return {"status": "ok", "supabase_connected": supabase is not None}

@app.get("/api/audits")
def get_audits():
    if not supabase:
        return {"error": "Supabase not configured"}
    try:
        response = supabase.table("seo_audits").select("*").execute()
        return {"data": response.data}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/audits")
def create_audit(record: AuditRecord):
    if not supabase:
        return {"error": "Supabase not configured"}
    try:
        response = supabase.table("seo_audits").insert(record.dict(exclude_none=True)).execute()
        return {"data": response.data}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/audit")
async def perform_audit(req: AuditRequest):
    target_url = req.target_url
    
    scraper_task = asyncio.to_thread(scrape_local_seo, target_url)
    pagespeed_task = asyncio.create_task(fetch_pagespeed_seo(target_url))
    
    scraper_result, pagespeed_result = await asyncio.gather(scraper_task, pagespeed_task)
    
    seobility_score = scraper_result.get("seobility_scores", {}).get("on_page_score", 0)
    ps_score = pagespeed_result.get("pagespeed_seo_score", 0)
    final_score = int((seobility_score + ps_score) / 2) if ps_score > 0 else seobility_score
    
    return {
        "target_url": target_url,
        "overall_score": final_score,
        "local_scraping": scraper_result,
        "pagespeed_api": pagespeed_result
    }

@app.post("/api/fix")
async def apply_fix(req: FixRequest):
    REPO_MAPPING = {
        "https://novoxcore.com/": "Emmanuelkj/seo-agent-test",
        "https://www.cinescape.com.kw/": "your-username/cinescape-web"
    }
    
    from urllib.parse import urlparse
    parsed = urlparse(req.target_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}/"
    
    repo_name = REPO_MAPPING.get(base_url) or REPO_MAPPING.get(req.target_url)
    if not repo_name:
        return {"error": f"Repository mapping not found for {base_url}"}

    # Dynamically resolve the target_file_path in the repository
    path = parsed.path.lstrip('/')
    if not path or path == "":
        target_file_path = "index.html"
    elif not path.endswith('.html'):
        github_files = get_github_html_files(repo_name)
        if f"{path}.html" in github_files:
            target_file_path = f"{path}.html"
        elif f"{path}/index.html" in github_files:
            target_file_path = f"{path}/index.html"
        else:
            target_file_path = f"{path}.html" # Fallback
    else:
        target_file_path = path

    try:
        pr_link = await asyncio.to_thread(
            create_seo_pull_request, 
            repo_name, 
            req.errors, 
            target_file_path
        )
        return {"status": "success", "pr_link": pr_link}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/crawl")
async def start_site_crawl(req: CrawlRequest, background_tasks: BackgroundTasks):
    # Generate a unique ID for this specific run
    batch_id = str(uuid.uuid4())
    
    # Hand the heavy lifting off to the background thread
    background_tasks.add_task(process_site_crawl, req.base_url, batch_id)
    
    # Instantly reply to the frontend so the UI doesn't freeze
    return {
        "status": "processing",
        "message": f"Spider deployed on {req.base_url}. Check the Master Dashboard shortly.",
        "batch_id": batch_id
    }

@app.get("/api/crawl/status/{batch_id}")
def get_crawl_status(batch_id: str):
    if batch_id in completed_batches:
        return {"status": "completed"}
    return {"status": "processing"}