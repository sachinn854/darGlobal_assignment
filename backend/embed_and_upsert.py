import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from rag import COLLECTION, MODEL_NAME, load_records, make_chunks, _load_env

_load_env()

from fastembed import TextEmbedding
from qdrant_client import QdrantClient, models

URL = os.getenv("QDRANT_URL")
KEY = os.getenv("QDRANT_API_KEY")
VECTOR_SIZE = 384


def main():
    records = load_records()
    chunks = make_chunks(records)
    print(f"records={len(records)} chunks={len(chunks)} model={MODEL_NAME}", flush=True)

    client = QdrantClient(url=URL, api_key=KEY, timeout=60)
    existing = [c.name for c in client.get_collections().collections]
    print(f"existing collections: {existing}", flush=True)

    if COLLECTION in existing:
        client.delete_collection(COLLECTION)
        print(f"deleted old '{COLLECTION}' for clean rebuild", flush=True)
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=models.VectorParams(
            size=VECTOR_SIZE,
            distance=models.Distance.COSINE,
        ),
    )
    print(f"created collection '{COLLECTION}' (size={VECTOR_SIZE}, cosine)", flush=True)

    model = TextEmbedding(MODEL_NAME)
    texts = [c["text"] for c in chunks]
    vectors = list(model.embed(texts))
    print(f"embeddings done: {len(vectors)} vectors of dim {len(vectors[0])}", flush=True)

    points = [
        models.PointStruct(
            id=chunk["chunk_id"],
            vector=vector.tolist(),
            payload=chunk,
        )
        for chunk, vector in zip(chunks, vectors)
    ]

    for start in range(0, len(points), 100):
        client.upsert(collection_name=COLLECTION, points=points[start:start + 100], wait=True)
        print(f"  upserted {min(start + 100, len(points))}/{len(points)}", flush=True)

    count = client.count(COLLECTION).count
    print(f"DONE: '{COLLECTION}' now has {count} points. Other collections untouched.", flush=True)


if __name__ == "__main__":
    main()
