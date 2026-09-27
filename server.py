"""Jev-powered emoji chooser: one Noul per emoji, fanned out in parallel requests, streamed as they land."""

import asyncio
import json
from pathlib import Path

import httpx2
from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.routing import Route
from typesafe_sdk import AsyncTypeSafeClient, Noul

load_dotenv()

STATIC = Path(__file__).parent / "static"
CATALOG = json.loads((STATIC / "emoji.json").read_text())
MAX_CHUNK = 255  # Nouls per request; chunks run in parallel
THRESHOLD = 0.5  # minimum yes-probability to show an emoji
LIMIT = 12
USD_PER_INPUT_TOKEN = 0.042 / 1_000_000  # jev-1.13 pricing; output tokens are free

# fewest requests that fit MAX_CHUNK, split evenly so no chunk is a straggler by size
N_CHUNKS = -(-len(CATALOG) // MAX_CHUNK)
CHUNKS = [range(len(CATALOG) * k // N_CHUNKS, len(CATALOG) * (k + 1) // N_CHUNKS) for k in range(N_CHUNKS)]

# keep the per-chunk TLS connections open between searches; httpx's default 5s idle expiry
# means a pause while typing costs a fresh handshake on every chunk (~150-300ms)
client = AsyncTypeSafeClient(http_client=httpx2.AsyncClient(
    timeout=10,
    limits=httpx2.Limits(max_keepalive_connections=2 * N_CHUNKS, keepalive_expiry=300),
))


def related(item: dict) -> Noul:
    return Noul(
        instructions=(
            f'Is the emoji {item["e"]} "{item["n"]}" strongly associated with `query`, '
            "so that someone searching for `query` would want to pick it?"
        ),
    )


async def ask(query: str, items: range) -> tuple[dict[int, float], int]:
    response = await client.system_one(
        state={"query": query},
        questions={str(i): related(CATALOG[i]) for i in items},
    )
    scores = {int(k): a.noul for k, a in response.nouls.items()}
    return scores, response.usage.input_tokens


def top(scores: dict[int, float]) -> list[dict]:
    ranked = sorted((i for i, p in scores.items() if p >= THRESHOLD), key=scores.get, reverse=True)
    return [{**CATALOG[i], "p": round(scores[i], 3)} for i in ranked[:LIMIT]]


async def search(request):
    """Streams NDJSON: one line per finished chunk with the running top hits."""
    query = (await request.json()).get("query", "").strip()
    if not query:
        return JSONResponse({"hits": [], "tokens": 0, "usd": 0, "done": 0, "total": 0})

    async def lines():
        tasks = [asyncio.create_task(ask(query, items)) for items in CHUNKS]
        scores, tokens = {}, 0
        try:
            for done, next_part in enumerate(asyncio.as_completed(tasks), 1):
                part, t = await next_part
                scores |= part
                tokens += t
                yield json.dumps({
                    "hits": top(scores),
                    "tokens": tokens,
                    "usd": tokens * USD_PER_INPUT_TOKEN,
                    "done": done,
                    "total": len(tasks),
                }) + "\n"
        finally:
            for task in tasks:
                task.cancel()  # client went away mid-stream

    return StreamingResponse(lines(), media_type="application/x-ndjson")


app = Starlette(
    routes=[
        Route("/", lambda _: FileResponse(STATIC / "index.html")),
        Route("/search", search, methods=["POST"]),
    ]
)
