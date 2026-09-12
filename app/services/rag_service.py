"""
RAG service: chunking, embedding, storage, and scoped retrieval.

All vector operations are scoped by (organization_id, agent_id). One
organization's knowledge must never leak into another's retrieval - every
query here filters on both fields.

Uses MongoDB for chunk storage. If the connected cluster is MongoDB Atlas
with a Vector Search index configured on `knowledge_chunks.embedding`, swap
`_similarity_search` to use `$vectorSearch` aggregation instead of the
in-app cosine scan below - the rest of the pipeline is unchanged.
"""
from app.extensions import get_db
from app.models import build_knowledge_chunk, now
from app.services.embedding_service import embed, cosine_similarity

CHUNK_TARGET_TOKENS = 700
CHUNK_OVERLAP_TOKENS = 100


def chunk_text(text: str, target_words=CHUNK_TARGET_TOKENS, overlap_words=CHUNK_OVERLAP_TOKENS):
    words = text.split()
    if not words:
        return []
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + target_words, len(words))
        chunk = " ".join(words[start:end])
        if chunk.strip():
            chunks.append(chunk.strip())
        if end == len(words):
            break
        start = end - overlap_words
    return chunks


def index_document(organization_id, agent_id, source_id, text, base_metadata=None, db=None):
    """Chunk, embed, and store a document's text. Returns number of chunks created."""
    db = db or get_db()
    base_metadata = base_metadata or {}
    chunks = chunk_text(text)
    docs = []
    for i, chunk in enumerate(chunks):
        vector = embed(chunk)
        meta = dict(base_metadata)
        meta["chunk_index"] = i
        docs.append(build_knowledge_chunk(organization_id, agent_id, source_id, chunk, vector, meta))
    if docs:
        db.knowledge_chunks.insert_many(docs)
    return len(docs)


def delete_source_chunks(organization_id, agent_id, source_id, db=None):
    db = db or get_db()
    db.knowledge_chunks.delete_many({
        "organization_id": organization_id,
        "agent_id": agent_id,
        "source_id": source_id,
    })


def retrieve(organization_id, agent_id, query, top_k=5, min_score=0.05, db=None):
    """Scoped semantic search. Only ever searches this org+agent's chunks."""
    db = db or get_db()
    query_vec = embed(query)
    cursor = db.knowledge_chunks.find({
        "organization_id": organization_id,
        "agent_id": agent_id,
    })
    scored = []
    for doc in cursor:
        score = cosine_similarity(query_vec, doc["embedding"])
        if score >= min_score:
            scored.append((score, doc))
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_k]
    return [
        {
            "content": doc["content"],
            "score": round(score, 4),
            "metadata": doc.get("metadata", {}),
            "source_id": doc.get("source_id"),
        }
        for score, doc in top
    ]


def build_context_block(chunks):
    if not chunks:
        return ""
    lines = ["Relevant business knowledge (only use what's relevant, cite naturally, never invent beyond this):"]
    for c in chunks:
        lines.append(f"- {c['content']}")
    return "\n".join(lines)
