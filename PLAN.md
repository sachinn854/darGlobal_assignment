# Assignment Plan - DarGlobal + Wasalt RAG Chatbot

## 1. Objective
Scrape public data from DarGlobal and Wasalt, build an AI chatbot on that data,
containerize it with Docker, deploy it, and provide a working URL for testing.

Requirements:
1. Scrape publicly available data from **DarGlobal** and **Wasalt**.
2. Build an AI chatbot using the collected data.
3. Use a free model available through **OpenRouter**.
4. Containerize the application with **Docker**.
5. Deliver a deployed solution, not just source code.
6. Provide a **working URL** for direct testing.

## 2. Step-by-step breakdown

### Step 1 - Scraper pipeline
- Discover public URLs from both sitemaps.
- Follow `robots.txt` and `llms.txt` rules (rate limits, disallowed paths).
- Fetch each allowed page and extract visible text only.
- Store structured records with title, URL, and source name.
- Output: `backend/corpus.json`.

### Step 2 - Data cleaning
- Remove markdown artifacts, tracking parameters, cookie banners, navigation,
  footer links, UI labels, and duplicate blocks.
- Preserve headings and paragraph structure.
- Re-scrape Wasalt with semantic extraction to recover heading structure.
- Output: `backend/corpus_cleaned.json`. Raw file is preserved for audit.

### Step 3 - Chunking and retrieval
- Split long documents with `RecursiveCharacterTextSplitter` (1200 chars, 150 overlap).
- Short records (<= 1200 chars) remain a single chunk automatically.
- Embed chunks with `BAAI/bge-small-en-v1.5` via `fastembed` (no PyTorch).
- Store vectors in a dedicated Qdrant collection.
- Retrieve with hybrid search: semantic vectors plus TF-IDF keywords, fused with
  reciprocal rank fusion and boosted by source or project names in the question.

### Step 4 - Backend and RAG (`/chat`)
- FastAPI server with a startup-loaded retriever.
- Flow: `question -> retrieve -> prompt with context -> OpenRouter -> answer + sources`.
- Endpoint: `POST /chat` returning `{ "answer": "...", "sources": [...] }`.
- `GET /health` for readiness checks.
- Answer strictly from retrieved context; state when information is unavailable.

### Step 5 - Frontend
- React + Vite + Tailwind chat interface.
- Chat bubbles, input box, send button, and source links.
- English sample questions (the embedding model is English-oriented).

### Step 6 - Docker
- Multi-stage `Dockerfile`: Node build stage, Python runtime stage.
- `.dockerignore` and `requirements.txt`.

### Step 7 - Deploy
- Render web service with Docker runtime.
- Environment variables for OpenRouter and Qdrant credentials.
- Test the live URL and share it.

## 3. Tech stack

| Purpose | Tool | Reason |
|---|---|---|
| HTTP requests and HTML parsing | `requests`, `BeautifulSoup4` | Simple and sufficient for public pages |
| Semantic HTML to Markdown | `markdownify` | Preserves headings and structure |
| Sitemap parsing | `xml`, `gzip` (standard library) | Handles plain and compressed sitemaps |
| Text cleaning | Python regex | No extra dependency |
| Chunking | `langchain-text-splitters` | Recursive, separator-aware splitting |
| Vector embeddings | `fastembed` + `BAAI/bge-small-en-v1.5` | Torch-free, ONNX, 384 dimensions |
| Vector store | Qdrant Cloud | Dedicated collection, fast semantic search |
| Keyword retrieval | `scikit-learn` TF-IDF | Combined with semantic search via reciprocal rank fusion |
| Result fusion | Reciprocal rank fusion | Merges semantic and keyword rankings with source-aware boosting |
| Backend | Python + FastAPI + uvicorn | Lightweight async API |
| LLM generation | OpenRouter free model | Assignment requirement |
| Configuration | `.env` + environment variables | No secrets in code |
| Frontend | React + Vite + Tailwind CSS | Chosen stack |
| Containerization | Docker (multi-stage) | Assignment requirement |
| Deployment | Render (Docker runtime) | Free tier with Docker support |
| Version control | Git | Source history and deployment source |

## 4. File and folder structure

```
C:\darGlobal\
├── PLAN.md                  # Overview and tech stack
├── PHASES.md                # Phase-by-phase execution plan
├── SAMPLE_VERIFY.txt        # Before/after cleaning sample
├── Dockerfile               # Multi-stage build
├── .dockerignore
├── .gitignore
├── render.yaml              # Render blueprint
├── backend/
│   ├── scraper.py           # Sitemap discovery and fetching
│   ├── clean_corpus.py      # Cleaning and semantic extraction
│   ├── corpus.json          # Raw output (preserved)
│   ├── corpus_cleaned.json  # Cleaned output
│   ├── rag.py               # Chunking and retrieval
│   ├── embed_and_upsert.py  # One-time vector setup
│   ├── app.py               # FastAPI application
│   ├── requirements.txt
│   ├── .env.example
│   └── .env                 # Local secrets (gitignored)
└── frontend/
    ├── index.html
    ├── package.json
    ├── vite.config.js
    ├── tailwind.config.js
    ├── postcss.config.js
    └── src/
        ├── main.jsx
        ├── App.jsx
        └── index.css
```

## 5. Data sources

### DarGlobal - `https://darglobal.co.uk`
- Sitemap: `https://darglobal.co.uk/sitemap.xml` (482 URLs).
- `robots.txt` allows `/blog/`, `/press/`, `/projects/`.
- Pages: about, investor, FAQ, why-invest, partners, press, blog, projects.
- Excluded: `darglobal.com` (an unrelated company).

### Wasalt - `https://wasalt.sa`
- `robots.txt` allows most paths and disallows `/search`.
- `llms.txt` permits LLM use with attribution: "Source: Wasalt.sa".
- Pages: home, corporate, masterplan, business, property listings.
- Excluded: `/search`, user profiles, bulk contact data.

## 6. OpenRouter model
- Free model via `https://openrouter.ai/api/v1/chat/completions`.
- API key stored in `OPENROUTER_API_KEY` (environment variable only).
- Prompt restricts answers to retrieved context.

## 7. Environment notes
- Local machine: Python 3.13, Node 20, npm 10, Git available.
- Docker is not installed locally; the image is built on Render.
- Deployment requires a Render account and a GitHub repository.

## 8. Execution order
1. Setup and structure.
2. Scraper and raw corpus.
3. Cleaning and cleaned corpus.
4. Chunking, embeddings, and Qdrant storage.
5. FastAPI backend.
6. React frontend.
7. Dockerfile and Render blueprint.
8. Deployment and live URL.
