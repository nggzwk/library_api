import httpx

OPENLIBRARY_SEARCH_URL = "https://openlibrary.org/search.json"

async def search_openlibrary(query: str, author: str = None, limit: int = 5):
    params = {"q": query, "limit": limit}
    if author:
        params["author"] = author
    async with httpx.AsyncClient() as client:
        response = await client.get(OPENLIBRARY_SEARCH_URL, params=params)
        response.raise_for_status()
        return response.json()