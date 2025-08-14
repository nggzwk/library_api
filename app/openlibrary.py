import httpx
from fastapi import HTTPException

async def search_openlibrary(title_or_author, author=None, limit=5):
    url = "https://openlibrary.org/search.json"
    params = {"limit": limit}
    if author:
        params["author"] = author
    if title_or_author:
        params["q"] = title_or_author

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params=params)
            if response.status_code == 429:
                raise HTTPException(
                    status_code=503,
                    detail="Open Library API rate limit exceeded. Please try again later.",
                )
            if response.status_code != 200:
                raise HTTPException(
                    status_code=502,
                    detail=f"Open Library API error: {response.status_code} {response.reason_phrase}",
                )
            return response.json()
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Error connecting to Open Library API: {exc}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error: {exc}",
        )