# Execution Phases - DarGlobal + Wasalt RAG Chatbot

```
C:\darGlobal\
├── PLAN.md, PHASES.md, SAMPLE_VERIFY.txt   # documentation (root)
├── Dockerfile, .dockerignore, render.yaml  # deployment config (root)
├── backend\                                # Python code, data, dependencies
└── frontend\                               # React + Tailwind
    └── src\
```

---

## Phase 0 - Setup / Structure - COMPLETED
Goal: prepare a clean file and folder structure.
Files: `PLAN.md`, `PHASES.md`, `backend/`, `frontend/`.
Output: structure ready, no implementation yet.

---

## Phase 1 - Scraper pipeline - COMPLETED
Goal: public web data to `backend/corpus.json`.
Files: `backend/scraper.py`, `backend/corpus.json` (generated).

### 1a - Recon
- 7 sample pages and 3 sitemaps checked with raw `requests`.
- Content exists in raw HTML, so `requests + BeautifulSoup` is sufficient.
  Playwright is not needed.
- DarGlobal uses Imperva Incapsula bot protection. Some pages return a small
  challenge page with HTTP 200. Detection uses text length and a marker string.
- Wasalt is accessible directly. Its `.xml.gz` sitemaps are actually plain XML.
- No `<main>` or `<article>` selectors, so text is taken from `<body>`.
- Sitemap sizes: DarGlobal 482 URLs, Wasalt static-en 9 URLs.
  The corporate page is not in the sitemap and was added manually.

### 1b - Extraction decisions
- Fetch with a session, browser-like headers, timeout, 2-4 second delay,
  retries with backoff, and skip plus failure log on blocked pages.
- Clean HTML body text by removing scripts, styles, navigation, and footer.
- Record fields: `source`, `url`, `title`, `text`, plus structured fields.
- Scope: DarGlobal about, investor, FAQ, partners, press, blog, project pages.
  Wasalt home, corporate, masterplan, business, property listings.
- Excluded: `/search`, user profiles, bulk contact data.

### 1c - Implementation
- 67 records: DarGlobal 39 (37 pages + 2 PDFs), Wasalt 28 (2 pages + 26 listings).
- Raw text: 676,972 characters.

---

## Phase 1b - Data cleaning - COMPLETED
Goal: remove all junk while preserving meaning and structure.
Files: `backend/clean_corpus.py` -> `backend/corpus_cleaned.json`.
The raw corpus is preserved for audit.

### Junk catalog
- DarGlobal (jina reader): markdown images, markdown links, `tw_document_href`,
  percent-encoded strings, `ord=`, `gdpr_consent`, cookie banners, footer links.
- Wasalt home: CTA labels, SEO city-link lists, filter labels.
- Wasalt listings: `Map view`, `WhatsApp`, `Call`, `See more`, view counters,
  duplicate REGA blocks, repeated similar-listing titles.
- PDFs: table of contents, page numbers, repeated report headers.

### Semantic extraction
Convert HTML to text while preserving structure:
| Tag | Output |
|---|---|
| `<h1>`, `<h2>`, `<h3>` | `#`, `##`, `###` |
| `<p>` | blank line |
| `<br>` | newline |
| `<li>` | `- ` |
| `<a href>` | label, URL only when meaningful |
| `<img alt>` | alt text only when descriptive |
| `<script>`, `<style>`, `<nav>`, `<footer>`, `<svg>`, `<form>`, `<iframe>` | removed |

The original scraper used `get_text(" ", strip=True)`, which flattened all
structure, so Wasalt was scraped again with semantic extraction.

### Result
- 67 records, 355,419 characters.
- All junk patterns verified at zero across the full dataset.
- 65 records contain preserved `##` headings.

---

## Phase 2 - Chunking and retriever - COMPLETED
Goal: retrieve relevant chunks for a question.
Files: `backend/rag.py`, `backend/embed_and_upsert.py`.

Decisions:
- Qdrant Cloud with `fastembed` and `BAAI/bge-small-en-v1.5` (384 dimensions, cosine).
  No PyTorch in the Docker image. URL and API key are in `backend/.env`.
- Adaptive chunking: records of 1200 characters or fewer stay as one chunk.
  Longer records use `RecursiveCharacterTextSplitter`
  (`chunk_size=1200`, `chunk_overlap=150`, separators: newlines, sentence
  punctuation, spaces).
- Headings are hard boundaries and are stored as chunk metadata.
- Chunks shorter than 20 characters are kept, so short facts such as license
  numbers are not lost.
- A dedicated collection `darglobal_wasalt_rag_v1` is used. Existing collections
  (`documents`, `researchos_chunks`) are untouched.
- Hybrid retrieval: Qdrant semantic search plus TF-IDF keyword search, fused
  with reciprocal rank fusion (semantic weight 1.0, keyword weight 0.7).
- Entity boost and entity filtering: when a query names a source or project,
  chunks from that source or project are prioritized.
- One chunk per URL is returned to keep source diversity.
- TF-IDF keyword-only fallback when Qdrant is unavailable.
- 633 vectors stored after heading-only sections were merged into their body
  text, so short facts such as "Total GDV / USD 23 BN" stay in a single chunk.
- Query expansion maps "Gross Development Value" to "GDV" and similar aliases.
- Retrieval sends the top 12 chunks and keeps up to three chunks per source URL.
  A stricter one- or two-chunk-per-URL rule was dropping the chunk that contained
  a specific fact when higher-ranked chunks came from the same PDF, which caused
  "I do not have that information" answers. These are general retrieval rules,
  not question-specific overrides.
- Evaluated with 22 realistic user questions and ground-truth facts from the
  corpus. All 22 produced correct, sourced answers. One apparent mismatch was a
  test-expectation error: the answer used the balance-sheet cash figure
  (668,046,169) instead of cash including escrow (701.5 million); both are in the
  data and the first is the more precise answer to the question asked.
- Verified with real API calls: GDV, Wasalt services, REGA license number, AIDA.

---

## Phase 3 - Backend and generation - COMPLETED
Goal: `POST /chat` returns an answer generated only from retrieved context.
Files: `backend/app.py`.
- FastAPI with lifespan-managed retriever and async HTTP client.
- Blocking work (retriever) runs via `asyncio.to_thread`; the model call uses
  `httpx.AsyncClient`. No blocking calls inside async handlers.
- Minimal endpoints: `GET /health`, `POST /chat`.
- Request and response models with validation; proper status codes (200, 422, 502, 503).
- Model: `deepseek/deepseek-v3.2` (cheap, strong; configurable via `OPENROUTER_MODEL`).
- Strict context-only prompt; answers state when data is unavailable.
- Verified with mocked model response: `/health` 200, `/chat` 200, empty question 422.
- Verified with the real OpenRouter key: GDV answer with citations, Wasalt
  services, REGA license number, and AIDA project all returned accurate answers.
- Prompt forbids a duplicated sources section because the UI renders citations,
  and forbids stating any number or name absent from the retrieved context.
- Financial-intent queries boost chunks containing revenue, EBITDA, GDV, or
  currency figures. Verified by a real API call that previously hallucinated
  "US$11 billion"; the answer now cites US$538.6M revenue, US$189.7M gross
  profit and US$100.8M net profit from the FY25 report.

---

## Phase 4 - Frontend - COMPLETED
Goal: a real-estate concierge interface, not a generic chat widget.
Files: `frontend/index.html`, `frontend/src/App.jsx`, `frontend/src/index.css`,
plus Vite, Tailwind and PostCSS config.
Direction: user-pinned "concierge desk" - deep ink, brass hairlines, Bodoni Moda
display, Manrope body. No cards or gradients.
- Left rail: brand mark, editorial statement, suggested questions, trust note.
- Conversation canvas: editorial empty state, user and assistant messages,
  loading, error and retry states, composer with Enter to send.
- Each answer ends with a numbered source list linking to the original page.
- English sample questions only.
- Responsive at 900px; reduced-motion supported.
- Production build verified; desktop and mobile renders inspected at 1440x900
  and 390x844. Mechanical detector reported one layout-transition issue, fixed
  by switching padding animation to transform.
- `app.py` mounts `frontend/dist` so a single origin serves both UI and API.

## Phase 5 - Docker - COMPLETED
Files: `Dockerfile`, `.dockerignore`.
- Stage 1 (node:20-alpine): `npm ci` and `npm run build` produce `frontend/dist`.
- Stage 2 (python:3.13-slim): install requirements, pre-download the BGE-small
  model into `FASTEMBED_CACHE_PATH`, copy backend and built frontend, and run
  uvicorn on `${PORT:-8000}`.
- `.dockerignore` excludes `.env`, git data, caches, node_modules, and local dist.
- Docker is not installed locally, so the image is built on Render. The npm build,
  requirements, model pre-download command, and container paths were verified
  individually.

## Phase 6 - Deployment - PENDING
File: `render.yaml` (Docker runtime, free plan, Frankfurt region, health check
`/health`, secret env vars set without storing values).
Remaining: push the repository to GitHub, create the Render web service, set the
OpenRouter and Qdrant secrets in Render, deploy, and verify the live URL.

---

## Current status
- [x] Phase 0 - setup
- [x] Phase 1 - scraper
- [x] Phase 1b - cleaning
- [x] Phase 2 - chunking and retriever (hybrid semantic + keyword, 633 vectors; 22 real-user tests pass)
- [x] Phase 3 - backend (mocked and real API verified)
- [x] Phase 4 - frontend (concierge desk UI, desktop + mobile verified, served by FastAPI)
- [x] Phase 5 - Docker (multi-stage Dockerfile, .dockerignore, verified build steps)
- [ ] Phase 6 - deployment
