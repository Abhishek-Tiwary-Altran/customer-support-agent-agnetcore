"""
Web Search Tool for AgentCore Agents

Provides web search capabilities using DuckDuckGo search.
"""

import logging
from strands import tool

logger = logging.getLogger(__name__)


@tool
def web_search_tool(query: str, max_results: int = 5, region: str = "us-en") -> str:
    """
    Search the web for information using DuckDuckGo.
    
    Args:
        query: Search query
        max_results: Maximum number of results to return (1-10)
        region: Search region (us-en, uk-en, etc.)
    
    Returns:
        Formatted search results
    """
    try:
        from duckduckgo_search import DDGS
        from duckduckgo_search.exceptions import DDGSException, RatelimitException
        
        # Validate inputs
        max_results = min(max(1, max_results), 10)  # Clamp between 1-10
        
        results = DDGS().text(query, region=region, max_results=max_results)
        
        if not results:
            return "No search results found for the query."
        
        # Format results
        formatted_results = []
        for i, result in enumerate(results, 1):
            title = result.get('title', 'No title')
            body = result.get('body', 'No description')
            url = result.get('href', 'No URL')
            
            formatted_results.append(
                f"{i}. **{title}**\n"
                f"   {body}\n"
                f"   Source: {url}"
            )
        
        return "\n\n".join(formatted_results)
        
    except RatelimitException:
        logger.warning("DuckDuckGo rate limit reached")
        return "Search rate limit reached. Please try again in a moment."
    
    except DDGSException as e:
        logger.error(f"DuckDuckGo search error: {e}")
        return f"Search service error: {str(e)}"
    
    except ImportError:
        logger.error("duckduckgo-search package not installed")
        return "Web search is not available. Please install the duckduckgo-search package."
    
    except Exception as e:
        logger.error(f"Unexpected web search error: {e}")
        return f"Search error: {str(e)}"


@tool
def search_news(query: str, max_results: int = 3) -> str:
    """
    Search for recent news articles.
    
    Args:
        query: News search query
        max_results: Maximum number of news articles to return
    
    Returns:
        Formatted news results
    """
    try:
        from duckduckgo_search import DDGS
        
        # Add "news" to the query for better news results
        news_query = f"{query} news"
        
        results = DDGS().text(news_query, region="us-en", max_results=max_results)
        
        if not results:
            return f"No recent news found for: {query}"
        
        # Format news results
        formatted_results = []
        for i, result in enumerate(results, 1):
            title = result.get('title', 'No title')
            body = result.get('body', 'No description')
            url = result.get('href', 'No URL')
            
            formatted_results.append(
                f"📰 **{title}**\n"
                f"   {body}\n"
                f"   Read more: {url}"
            )
        
        return f"Recent news for '{query}':\n\n" + "\n\n".join(formatted_results)
        
    except Exception as e:
        logger.error(f"News search error: {e}")
        return f"News search error: {str(e)}"


@tool
def search_images(query: str, max_results: int = 3) -> str:
    """
    Search for images (returns image URLs and descriptions).
    
    Args:
        query: Image search query
        max_results: Maximum number of images to return
    
    Returns:
        Formatted image search results
    """
    try:
        from duckduckgo_search import DDGS
        
        results = DDGS().images(query, region="us-en", max_results=max_results)
        
        if not results:
            return f"No images found for: {query}"
        
        # Format image results
        formatted_results = []
        for i, result in enumerate(results, 1):
            title = result.get('title', 'No title')
            image_url = result.get('image', 'No URL')
            source = result.get('source', 'Unknown source')
            
            formatted_results.append(
                f"🖼️ **{title}**\n"
                f"   Image URL: {image_url}\n"
                f"   Source: {source}"
            )
        
        return f"Images for '{query}':\n\n" + "\n\n".join(formatted_results)
        
    except Exception as e:
        logger.error(f"Image search error: {e}")
        return f"Image search error: {str(e)}"


# Export the main tool for easy import
web_search = web_search_tool
