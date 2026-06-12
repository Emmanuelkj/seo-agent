import asyncio
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import warnings
from bs4 import XMLParsedAsHTMLWarning
import networkx as nx

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

async def find_all_internal_links(base_url: str, max_pages: int = 100) -> dict:
    # 1. BFS Queue Initialization
    visited = set()
    results = []
    queue = [base_url]
    
    # Track edges for Link Graphing (PageRank)
    edges = []
    
    ignore_exts = ('.pdf', '.jpg', '.jpeg', '.png', '.gif', '.svg', '.css', '.js', '.mp4')

    async with httpx.AsyncClient() as client:
        # 2. Fetching and Processing Each Page
        while queue and len(results) < max_pages:
            current_url = queue.pop(0)
            
            if current_url in visited:
                continue
                
            visited.add(current_url)

            # 5. Graceful Error Handling
            try:
                # Must follow redirects, otherwise 301s will fail the 200 OK check
                response = await client.get(current_url, timeout=10.0, follow_redirects=True)
                
                # Only process and add to results if successful
                if response.status_code == 200:
                    results.append(current_url)
                    print(f"✅ Spider verified: {current_url}")
                    
                    # 3. Extracting and Filtering Internal Links
                    soup = BeautifulSoup(response.text, 'html.parser')
                    for link in soup.find_all('a', href=True):
                        href = link['href']
                        
                        # Filter out mailto:, tel:, and simple hashes
                        if href.startswith(('mailto:', 'tel:', '#')):
                            continue
                            
                        # Normalize relative links to absolute, remove hash fragments
                        absolute_url = urljoin(str(response.url), href).split('#')[0]
                        
                        abs_domain = urlparse(absolute_url).netloc.replace('www.', '')
                        base_domain = urlparse(base_url).netloc.replace('www.', '')
                        
                        if abs_domain == base_domain:
                            # Record the edge for PageRank analysis
                            edges.append((current_url, absolute_url))
                            
                            if (absolute_url not in visited and 
                                absolute_url not in queue and
                                not absolute_url.lower().endswith(ignore_exts)):
                                queue.append(absolute_url)
                                
            except Exception as e:
                print(f"Warning: Failed to fetch {current_url} - {e}")

    # 6. Calculate Internal Link Juice (PageRank)
    G = nx.DiGraph()
    G.add_edges_from(edges)
    pagerank_scores = {}
    try:
        if len(G.nodes) > 0:
            pagerank_scores = nx.pagerank(G)
    except Exception as e:
        print(f"PageRank calculation failed: {e}")

    return {
        "urls": results,
        "pagerank": pagerank_scores
    }