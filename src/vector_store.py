# src/vector_store.py
from typing import List

from langchain_community.vectorstores.pgvector import PGVector
from langchain_core.documents import Document

from .config import NEON_DB_URL, embeddings


COLLECTION_NAME = "book_chunks"


def init_pgvector_collection() -> None:
    """
    Touch the collection once so PGVector creates the extension / table if needed.
    The warning about deprecation is okay for now.
    """
    _ = PGVector(
        connection_string=NEON_DB_URL,
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
    )


def get_vector_store() -> PGVector:
    """
    Return a PGVector instance bound to our Neon database.
    """
    store = PGVector(
        connection_string=NEON_DB_URL,
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
    )
    return store


def add_chunks(chunks: List[Document]) -> None:
    """
    Add chunked Documents to PGVector in batches.
    """
    store = get_vector_store()
    
    # Batch size of 100 to avoid huge payloads/timeouts
    batch_size = 100
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        store.add_documents(batch)
        print(f"Added batch {i // batch_size + 1} ({len(batch)} chunks)")
