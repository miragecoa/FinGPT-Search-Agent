import uvicorn
import requests
from typing import Dict, Any
# from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP
# from fastapi.middleware.cors import CORSMiddleware

# app = FastAPI(title="Echo MCP Server with CORS")

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_methods=["GET", "POST"],
#     allow_headers=["*"],
#     expose_headers=["Mcp-Session-Id"],  # so client can read the session header
# )

mcp = FastMCP(
    name="FinGPT MCP Server",
    port=9000
)

@mcp.tool()
def greet(name: str) -> str:
    print(f"[DEBUG] greet tool called with name: {name}")
    result = f"Hello, {name}!"
    print(f"[DEBUG] greet tool returning: {result}")
    return result

@mcp.tool()
def browser_navigate(url: str) -> Dict[str, Any]:
    """
    Navigate to a URL and return information about the page.

    Args:
        url: The URL to navigate to

    Returns:
        Dictionary containing page information including title, content summary, and metadata
    """
    print(f"[DEBUG] browser_navigate tool called with URL: {url}")

    try:
        # Make HTTP request to get page content
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        # Basic content extraction (you could enhance this with BeautifulSoup for better parsing)
        content = response.text
        title = "Unknown"

        # Extract title
        if "<title>" in content and "</title>" in content:
            title_start = content.find("<title>") + 7
            title_end = content.find("</title>", title_start)
            title = content[title_start:title_end].strip()

        # Get content length and basic info
        content_length = len(content)
        status_code = response.status_code

        # Create summary
        summary = f"Successfully navigated to {url}. Page title: '{title}'. Content length: {content_length} characters. Status: {status_code}"

        result = {
            "success": True,
            "url": url,
            "title": title,
            "status_code": status_code,
            "content_length": content_length,
            "summary": summary,
            "headers": dict(response.headers)
        }

        print(f"[DEBUG] browser_navigate tool returning: {result}")
        return result

    except requests.exceptions.RequestException as e:
        error_msg = f"Failed to navigate to {url}: {str(e)}"
        print(f"[DEBUG] browser_navigate tool error: {error_msg}")

        result = {
            "success": False,
            "url": url,
            "error": error_msg,
            "summary": f"Navigation to {url} failed: {str(e)}"
        }

        return result

if __name__ == "__main__":
    # uvicorn.run(app, host="127.0.0.1", port=9000, log_level="debug")
    mcp.run(transport="sse")
