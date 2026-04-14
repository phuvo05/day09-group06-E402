"""
build_index.py — Index data/docs/*.txt into ChromaDB
Chạy: python build_index.py

Script này đọc 5 file trong data/docs/,
chia thành chunks (theo paragraph), embed bằng Sentence Transformers,
và lưu vào ChromaDB collection 'day09_docs'.

Sau khi index, retrieval worker sẽ dùng semantic search
thay vì lexical fallback yếu.
"""
import os
import re
import sys
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

# ─── Config ─────────────────────────────────────────────
COLLECTION_NAME = "day09_docs"
CHROMA_PATH = "./chroma_db"
DOCS_DIR = "./data/docs"
MODEL_NAME = "all-MiniLM-L6-v2"
CHUNK_OVERLAP = 0   # keep paragraphs separate for precision


def split_into_chunks(text: str, overlap: int = 0) -> list[str]:
    """
    Split text into semantic chunks by paragraph (\n\n).
    Keep each paragraph as a separate chunk for maximum precision.
    """
    raw_chunks = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    # For very long paragraphs (>500 chars), split by sentence
    chunks = []
    for chunk in raw_chunks:
        if len(chunk) > 500:
            # Split long paragraph into sentences
            sentences = re.split(r"(?<=[.!?])\s+", chunk)
            buffer = ""
            for sent in sentences:
                if len(buffer) + len(sent) <= 500:
                    buffer += (" " if buffer else "") + sent
                else:
                    if buffer:
                        chunks.append(buffer)
                    buffer = sent
            if buffer:
                chunks.append(buffer)
        else:
            chunks.append(chunk)
    return [c for c in chunks if c]


def main():
    # 1. Load model
    print(f"Loading embedding model: {MODEL_NAME}...")
    model = SentenceTransformer(MODEL_NAME)

    # 2. Setup ChromaDB
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    try:
        client.delete_collection(COLLECTION_NAME)
        print(f"  (Deleted existing collection '{COLLECTION_NAME}')")
    except Exception:
        pass

    collection = client.get_or_create_collection(
        COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )

    # 3. Collect all docs
    docs_dir = Path(DOCS_DIR)
    if not docs_dir.exists():
        print(f"ERROR: {DOCS_DIR} not found!")
        sys.exit(1)

    all_ids = []
    all_embeddings = []
    all_documents = []
    all_metadatas = []

    file_paths = sorted(docs_dir.glob("*.txt"))
    if not file_paths:
        print(f"ERROR: No .txt files found in {DOCS_DIR}")
        sys.exit(1)

    print(f"\nIndexing {len(file_paths)} files from {DOCS_DIR}:")
    for file_path in file_paths:
        fname = file_path.name
        raw_text = file_path.read_text(encoding="utf-8")
        chunks = split_into_chunks(raw_text)
        print(f"  {fname}: {len(chunks)} chunks")

        for i, chunk_text in enumerate(chunks):
            chunk_id = f"{fname}_{i}"
            embedding = model.encode([chunk_text])[0].tolist()

            all_ids.append(chunk_id)
            all_embeddings.append(embedding)
            all_documents.append(chunk_text)
            all_metadatas.append({
                "source": fname,
                "chunk_id": i,
                "total_chunks": len(chunks),
            })

    # 4. Batch add to ChromaDB
    BATCH_SIZE = 100
    total = len(all_ids)
    print(f"\nAdding {total} chunks to ChromaDB (batch_size={BATCH_SIZE})...")

    for start in range(0, total, BATCH_SIZE):
        end = min(start + BATCH_SIZE, total)
        collection.add(
            ids=all_ids[start:end],
            embeddings=all_embeddings[start:end],
            documents=all_documents[start:end],
            metadatas=all_metadatas[start:end],
        )
        print(f"  Added {end}/{total} chunks...")

    # 5. Verify
    count = collection.count()
    print(f"\n✅ ChromaDB indexed: {count} chunks in collection '{COLLECTION_NAME}'")

    # 6. Quick sanity check
    print("\nSanity check — semantic search:")
    test_queries = [
        "SLA P1 escalation",
        "hoàn tiền flash sale",
        "Level 3 access phê duyệt",
        "store credit bao nhiêu phần trăm",
        "mật khẩu thay đổi bao nhiêu ngày",
    ]
    for q in test_queries:
        emb = model.encode([q])[0].tolist()
        results = collection.query(
            query_embeddings=[emb],
            n_results=2,
            include=["documents", "distances", "metadatas"],
        )
        top_source = results["metadatas"][0][0]["source"] if results["metadatas"] else "?"
        top_dist = results["distances"][0][0] if results["distances"] else "?"
        top_text = results["documents"][0][0][:60] if results["documents"] else "?"
        print(f"  Q: {q[:40]}")
        print(f"    → [{top_source}] dist={top_dist:.3f}: {top_text}...")


if __name__ == "__main__":
    main()
