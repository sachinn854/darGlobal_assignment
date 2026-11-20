# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

React + Vite + Tailwind CSS. Python FastAPI backend. Docker runtime on Render.

## Users

Prospective investors and property buyers researching DarGlobal projects and
Wasalt property services. They arrive with specific questions and want a quick,
credible answer with a traceable source.

## Product Purpose

Provide a conversational assistant that answers questions strictly from public
DarGlobal and Wasalt data. Success means the visitor gets a direct answer and
can see which source page it came from.

## Positioning

Answers are grounded in a fixed, cleaned corpus of both companies' public pages
and reports, using hybrid semantic and keyword retrieval. The assistant does not
invent facts and states when information is unavailable.

## Operating Context

The assistant is embedded in a web page beside a conversation. Visitors type
English questions and read concise answers with source links. The page must also
work on mobile.

## Capabilities and Constraints

- Answers come only from retrieved context.
- Each answer is accompanied by source titles and links.
- English questions are the supported path.
- Backend exposes GET /health and POST /chat.
- No user accounts, no saved history, no payment flows.

## Brand Commitments

This is a technical assignment deliverable. It represents publicly available data
from DarGlobal and Wasalt and must not fabricate claims, prices, or testimonials.
Attribution to the source page is required.

## Evidence on Hand

Cleaned corpus at `backend/corpus_cleaned.json` (67 records, DarGlobal and Wasalt).
Verified retrieval at `backend/rag.py`. API contract at `backend/app.py`.
No customer testimonials, pricing tables, or proprietary imagery are available.

## Product Principles

1. Answer from evidence, never from imagination.
2. Show the source with every answer.
3. Keep the interface calm and readable; the answer is the product.
4. Make the first question obvious.
5. Stay fast on both desktop and mobile.
