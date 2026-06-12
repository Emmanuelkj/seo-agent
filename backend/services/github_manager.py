import os
from github import Github, Auth
from google import genai
from google.genai import types

def parse_seo_errors_and_generate_html(errors: dict, current_html: str) -> str:
    """
    Uses Gemini to parse the specific SEO errors, analyze the current_html, 
    and generate an updated HTML string fixing the issues.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set")
        
    client = genai.Client(api_key=api_key)
    
    system_instruction = (
        "You are an expert SEO specialist and HTML parser. "
        "You will be provided with the current HTML code and a list of specific SEO errors to fix. "
        "Your task is to resolve all of the provided SEO errors directly within the HTML string. "
        "Return ONLY the raw, completely updated HTML code. "
        "Do not include any markdown formatting, do not wrap it in code blocks or backticks, and do not provide any explanations."
    )
    
    prompt = f"SEO Errors to fix:\n{errors}\n\nCurrent HTML:\n{current_html}"
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.1
        )
    )
    
    # Clean up just in case the model outputs markdown backticks anyway
    result = response.text.strip()
    if result.startswith("```html"):
        result = result[7:]
    elif result.startswith("```"):
        result = result[3:]
    if result.endswith("```"):
        result = result[:-3]
        
    return result.strip()

def get_github_html_files(repo_name: str) -> list[str]:
    """
    Fetches the repository tree and returns a list of all .html file paths.
    """
    token = os.environ.get("GITHUB_PAT")
    if not token:
        return []
        
    auth = Auth.Token(token)
    g = Github(auth=auth)
    html_files = []
    try:
        repo = g.get_repo(repo_name)
        main_branch = repo.get_branch("main")
        tree = repo.get_git_tree(sha=main_branch.commit.sha, recursive=True)
        for element in tree.tree:
            if element.type == "blob" and element.path.endswith(".html"):
                html_files.append(element.path)
    except Exception as e:
        print(f"Warning: Failed to fetch GitHub tree for {repo_name}: {e}")
    finally:
        g.close()
    return html_files

def create_seo_pull_request(repo_name: str, errors: dict, target_file_path: str = "index.html") -> str:
    """
    Connects to GitHub, creates a branch, modifies index.html, and opens a PR.
    Returns the PR URL.
    """
    token = os.environ.get("GITHUB_PAT")
    if not token:
        raise ValueError("GITHUB_PAT environment variable not set")
    
    # 1. Access repository via Personal Access Token
    auth = Auth.Token(token)
    g = Github(auth=auth)
    
    try:
        repo = g.get_repo(repo_name)
        
        # Get the base main branch
        main_branch = repo.get_branch("main")
        
        # 2. Create a new branch named 'seo-automated-patch'
        new_branch_name = "seo-automated-patch"
        try:
            repo.create_git_ref(ref=f"refs/heads/{new_branch_name}", sha=main_branch.commit.sha)
        except Exception:
            # It's possible the branch already exists, we could handle or overwrite.
            pass
            
        # Fetch current contents of the target file
        file_contents = repo.get_contents(target_file_path, ref=main_branch.commit.sha)
        current_html = file_contents.decoded_content.decode("utf-8")
        
        # Generate the updated HTML string with placeholder LLM
        updated_html = parse_seo_errors_and_generate_html(errors, current_html)
        
        # 3. Update the contents of the file and commit the changes
        repo.update_file(
            path=file_contents.path,
            message="Automated SEO Remediation",
            content=updated_html,
            sha=file_contents.sha,
            branch=new_branch_name
        )
        
        # 4. Open a Pull Request against the main branch
        pr = repo.create_pull(
            title="Automated SEO Remediation Patch",
            body="This PR automatically resolves several SEO errors detected by the SEO Agent.",
            head=new_branch_name,
            base="main"
        )
        
        return pr.html_url
        
    finally:
        g.close()
