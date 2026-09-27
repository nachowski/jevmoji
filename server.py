"""Jev-powered emoji chooser: one Noul per emoji, fanned out in parallel requests."""

import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route
from typesafe_sdk import AsyncTypeSafeClient, Noul

load_dotenv()

STATIC = Path(__file__).parent / "static"
CATALOG = json.loads((STATIC / "emoji.json").read_text())
CHUNK = 255  # Nouls per request; chunks run in parallel
THRESHOLD = 0.5  # minimum yes-probability to show an emoji
LIMIT = 12
USD_PER_INPUT_TOKEN = 0.042 / 1_000_000  # jev-1.13 pricing; output tokens are free

client = AsyncTypeSafeClient()


def related(item: dict) -> Noul:
    return Noul(
        instructions=(
            f'Is the emoji {item["e"]} "{item["n"]}" strongly associated with `query`, '
            "so that someone searching for `query` would want to pick it?"
        ),
    )


async def ask(query: str, start: int) -> tuple[dict[int, float], int]:
    items = range(start, min(start + CHUNK, len(CATALOG)))
    response = await client.system_one(
        state={"query": query},
        questions={str(i): related(CATALOG[i]) for i in items},
    )
    scores = {int(k): a.noul for k, a in response.nouls.items()}
    return scores, response.usage.input_tokens


async def search(request):
    query = (await request.json()).get("query", "").strip()
    if not query:
        return JSONResponse({"hits": [], "tokens": 0, "usd": 0})
    parts = await asyncio.gather(*(ask(query, s) for s in range(0, len(CATALOG), CHUNK)))
    scores = {i: p for part, _ in parts for i, p in part.items()}
    tokens = sum(t for _, t in parts)
    ranked = sorted((i for i, p in scores.items() if p >= THRESHOLD), key=scores.get, reverse=True)
    return JSONResponse({
        "hits": [{**CATALOG[i], "p": round(scores[i], 3)} for i in ranked[:LIMIT]],
        "tokens": tokens,
        "usd": tokens * USD_PER_INPUT_TOKEN,
    })


app = Starlette(
    routes=[
        Route("/", lambda _: FileResponse(STATIC / "index.html")),
        Route("/search", search, methods=["POST"]),
    ]
)
