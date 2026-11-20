import asyncio
import os
import re
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from rag import Retriever, _load_env

_load_env()

BASE = os.path.dirname(os.path.abspath(__file__))
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-120b")
TOP_K = 12
REQUEST_TIMEOUT = 60.0

SYSTEM_PROMPT = """You answer questions about DarGlobal and Wasalt using only the provided context.
If the answer is not present in the context, reply exactly: "I do not have that information in the available data."
Do not use outside knowledge. Never state any number, currency amount, date,
or proper name that does not appear verbatim in the context. If a figure is not
in the context, say you do not have that information instead of guessing.
Keep the answer concise. Cite supporting sources only as [1], [2], etc.
Never use any other citation format such as 【】 or markers with line numbers.
Do not write a sources section or repeat source names; the interface displays sources separately."""


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.retriever = await asyncio.to_thread(Retriever)
    app.state.client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)
    try:
        yield
    finally:
        await app.state.client.aclose()


app = FastAPI(
    title="DarGlobal and Wasalt Chatbot",
    description="Retrieval-augmented chatbot over public DarGlobal and Wasalt data.",
    version="1.0.0",
    lifespan=lifespan,
)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class Source(BaseModel):
    title: str
    url: str
    source: str
    heading: str | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]


def build_context(chunks):
    blocks = []
    sources = []
    seen = set()
    for index, chunk in enumerate(chunks, start=1):
        heading = chunk.get("heading") or ""
        block = (
            f"[{index}] Source: {chunk['source']}\n"
            f"Title: {chunk['title']}\n"
            f"Heading: {heading or 'N/A'}\n"
            f"URL: {chunk['url']}\n"
            f"Content: {chunk['text']}"
        )
        blocks.append(block)
        key = (chunk["url"], chunk["title"])
        if key not in seen:
            seen.add(key)
            sources.append(Source(
                title=chunk["title"],
                url=chunk["url"],
                source=chunk["source"],
                heading=heading or None,
            ))
    return "\n\n".join(blocks), sources


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest):
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key or api_key.startswith("your_key"):
        raise HTTPException(status_code=503, detail="OpenRouter API key is not configured")

    chunks = await asyncio.to_thread(app.state.retriever.retrieve, payload.question, TOP_K)
    context, sources = build_context(chunks)

    if not context:
        return ChatResponse(
            answer="I do not have that information in the available data.",
            sources=[],
        )

    request_body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {payload.question}"},
        ],
        "temperature": 0.2,
        "max_tokens": 1400,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://localhost",
        "X-Title": "DarGlobal Wasalt chatbot",
        "Content-Type": "application/json",
    }

    try:
        response = await app.state.client.post(OPENROUTER_URL, json=request_body, headers=headers)
        response.raise_for_status()
        data = response.json()
        answer = data["choices"][0]["message"]["content"].strip()
        answer = re.sub(r"【[^】]*?(\d+)[^】]*?】", r"[\1]", answer)
        answer = re.sub(r"【\s*(\d+)", r"[\1]", answer)
        answer = re.sub(r"(?im)^\s*(answer|system)\s*:\s*", "", answer)
        answer = answer.strip()
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Model request failed") from exc

    return ChatResponse(answer=answer, sources=sources)


frontend_dist = os.path.join(os.path.dirname(BASE), "frontend", "dist")
if os.path.isdir(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
