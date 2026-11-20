import os
import re
import json

BASE = os.path.dirname(os.path.abspath(__file__))


def _load_env():
    path = os.path.join(BASE, ".env")
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


_load_env()

from qdrant_client import QdrantClient
from fastembed import TextEmbedding
from sklearn.feature_extraction.text import TfidfVectorizer
from langchain_text_splitters import RecursiveCharacterTextSplitter

CORPUS_PATH = os.path.join(BASE, "corpus_cleaned.json")
MODEL_NAME = "BAAI/bge-small-en-v1.5"
COLLECTION = os.getenv("QDRANT_COLLECTION", "darglobal_wasalt_rag_v1")
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 150
SEPARATORS = ["\n\n", "\n", ". ", "! ", "? ", " ", ""]


def load_records():
    with open(CORPUS_PATH, encoding="utf-8") as f:
        return json.load(f)


HEADING_RE = re.compile(r"#{1,6}\s+")
HEADING_CAPTURE_RE = re.compile(r"#{1,6}\s+(?P<head>[^\n#]{2,120}?)(\?|\.|\n|\s{2,}|$)")
splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=SEPARATORS,
)


def normalize_text(text):
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]*\n", "\n\n", text)
    return text.strip()


def split_sections(text):
    matches = list(HEADING_RE.finditer(text))
    if not matches:
        return [(None, text)]
    sections = []
    if matches[0].start() > 0:
        preamble = text[:matches[0].start()].strip()
        if preamble:
            sections.append((None, preamble))
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section = text[match.start():end].strip()
        head_match = HEADING_CAPTURE_RE.match(section)
        if head_match:
            heading = head_match.group("head").strip()
            body = section[head_match.end():].strip()
        else:
            heading = ""
            body = section
        sections.append((heading or None, body))
    return sections


def make_chunks(records):
    chunks = []
    for record in records:
        text = normalize_text(record["text"])
        if len(text) <= CHUNK_SIZE:
            chunk = {k: v for k, v in record.items() if k != "text"}
            chunk["chunk_id"] = len(chunks)
            chunk["heading"] = None
            chunk["text"] = text
            chunks.append(chunk)
            continue
        sections = split_sections(text)
        merged = []
        pending = []
        for heading, body in sections:
            if len(body.strip()) < 20:
                label = heading or body.strip()
                if label and label not in pending:
                    pending.append(label)
                continue
            if pending:
                body = " ".join(pending) + "\n" + body
                heading = heading or pending[0]
                pending = []
            merged.append((heading, body))
        if pending:
            merged.append((pending[0], " ".join(pending)))

        for heading, body in merged:
            parts = splitter.split_text(body)
            for part in parts:
                part = part.strip()
                if len(part) < 20:
                    continue
                chunk = {k: v for k, v in record.items() if k != "text"}
                chunk["chunk_id"] = len(chunks)
                chunk["heading"] = heading
                chunk["text"] = part
                chunks.append(chunk)
    return chunks


RRF_K = 60

QUERY_ALIASES = {
    "gross development value": "GDV",
    "real estate general authority": "REGA",
    "return on equity": "ROE",
    "return on investment": "ROI",
    "financial figures": "revenue EBITDA GDV USD million",
    "financial performance": "revenue EBITDA GDV USD million",
}


def expand_query(query):
    expanded = query
    lower = query.lower()
    for phrase, alias in QUERY_ALIASES.items():
        if phrase in lower:
            expanded += " " + alias
    return expanded


class Retriever:
    def __init__(self):
        self.records = load_records()
        self.chunks = make_chunks(self.records)
        self.mode = "tfidf"
        self.qdrant = None
        self.model = None

        self.vectorizer = TfidfVectorizer(
            max_features=50000,
            stop_words="english",
            ngram_range=(1, 2),
            sublinear_tf=True,
        )
        self.matrix = self.vectorizer.fit_transform([c["text"] for c in self.chunks])

        try:
            self.qdrant = QdrantClient(
                url=os.getenv("QDRANT_URL"),
                api_key=os.getenv("QDRANT_API_KEY"),
                timeout=30,
            )
            names = [c.name for c in self.qdrant.get_collections().collections]
            if COLLECTION in names and self.qdrant.count(COLLECTION).count > 0:
                self.model = TextEmbedding(MODEL_NAME)
                self.mode = "hybrid"
        except Exception as exc:
            print(f"[rag] Qdrant unavailable, using keyword-only mode: {exc}", flush=True)

        print(f"[rag] mode={self.mode} chunks={len(self.chunks)}", flush=True)

    def _keyword_results(self, query, limit):
        vector = self.vectorizer.transform([query])
        scores = (self.matrix @ vector.T).toarray().ravel()
        top = scores.argsort()[-limit:][::-1]
        results = []
        for index in top:
            chunk = self.chunks[index]
            results.append({
                "chunk_id": chunk["chunk_id"],
                "text": chunk["text"],
                "source": chunk["source"],
                "url": chunk["url"],
                "title": chunk["title"],
                "heading": chunk.get("heading") or "",
                "score": float(scores[index]),
            })
        return results

    def _semantic_results(self, query, limit):
        vector = list(self.model.embed([query]))[0]
        hits = self.qdrant.query_points(
            collection_name=COLLECTION,
            query=vector.tolist(),
            limit=limit,
            with_payload=True,
        ).points
        results = []
        for hit in hits:
            payload = hit.payload or {}
            results.append({
                "chunk_id": payload.get("chunk_id"),
                "text": payload.get("text", ""),
                "source": payload.get("source", ""),
                "url": payload.get("url", ""),
                "title": payload.get("title", ""),
                "heading": payload.get("heading") or "",
                "score": float(hit.score),
            })
        return results

    def retrieve(self, query, top_k=4):
        if self.mode == "tfidf":
            return [
                {k: v for k, v in result.items() if k != "chunk_id"}
                for result in self._keyword_results(query, top_k)
            ]

        pool_size = max(top_k * 3, 12)
        search_query = expand_query(query)
        semantic = self._semantic_results(search_query, pool_size)
        keyword = self._keyword_results(search_query, pool_size)

        fused = {}
        for ranking, weight in ((semantic, 1.0), (keyword, 0.7)):
            for rank, result in enumerate(ranking, start=1):
                key = result["chunk_id"]
                if key not in fused:
                    fused[key] = {**result, "fusion_score": 0.0}
                fused[key]["fusion_score"] += weight / (RRF_K + rank)

        query_lower = query.lower()
        financial_intent = any(
            word in query_lower
            for word in (
                "financial", "invest", "revenue", "profit", "ebitda", "gdv",
                "return", "gross development value", "development value",
            )
        )
        for item in fused.values():
            boost = 0.0
            if financial_intent:
                text_lower = item["text"].lower()
                if any(marker in text_lower for marker in (
                    "usd", "us$", "revenue", "ebitda", "profit",
                    "gross development value", "gdv", "billion", "million",
                )):
                    boost += 0.008
            if "wasalt" in query_lower and item["source"] == "Wasalt":
                boost += 0.006
            if "darglobal" in query_lower and item["source"] == "DarGlobal":
                boost += 0.006
            label = (item["title"] + " " + item["heading"]).lower()
            for entity in ("aida", "trump", "missoni", "pagani", "lamborghini", "fendi"):
                if entity in query_lower and entity in label:
                    boost += 0.006
            item["fusion_score"] += boost

        candidates = list(fused.values())
        if "wasalt" in query_lower:
            candidates = [x for x in candidates if x["source"] == "Wasalt"] or candidates
        elif "darglobal" in query_lower:
            candidates = [x for x in candidates if x["source"] == "DarGlobal"] or candidates

        entities = [e for e in ("aida", "trump", "missoni", "pagani", "lamborghini", "fendi")
                    if e in query_lower]
        if entities:
            scoped = [
                x for x in candidates
                if any(e in (x["title"] + " " + x["heading"] + " " + x["text"][:1000]).lower()
                       for e in entities)
            ]
            candidates = scoped or candidates

        ranked = sorted(candidates, key=lambda item: item["fusion_score"], reverse=True)
        selected = []
        seen_urls = {}
        for item in ranked:
            if seen_urls.get(item["url"], 0) >= 3:
                continue
            seen_urls[item["url"]] = seen_urls.get(item["url"], 0) + 1
            selected.append({
                "text": item["text"],
                "source": item["source"],
                "url": item["url"],
                "title": item["title"],
                "heading": item["heading"],
                "score": item["fusion_score"],
            })
            if len(selected) >= top_k:
                break
        return selected
