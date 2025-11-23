# src/kg.py
from __future__ import annotations

from typing import List, Dict, Any, Optional

from neo4j import GraphDatabase
from langchain_openai import ChatOpenAI
from .config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, llm, OPENAI_API_KEY, LLM_MODEL_NAME

_driver = None
llm_deterministic = ChatOpenAI(
    model=LLM_MODEL_NAME,
    temperature=0.0,
    api_key=OPENAI_API_KEY,
)

def get_driver():
    global _driver
    if _driver is None:
        try:
            _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            # Test connection
            with _driver.session() as session:
                session.run("RETURN 1")
            print("Connected to Neo4j successfully")
        except Exception as e:
            print(f"Warning: Could not connect to Neo4j: {e}")
            print("Knowledge Graph features will be disabled. Please start Neo4j to enable them.")
            _driver = None
    return _driver


# ---------- Triple extraction using LLM ----------

TRIPLE_EXTRACTION_SYSTEM = (
    "You are an information extraction assistant. "
    "Given a passage of text, extract important factual triples "
    "in the form (subject, predicate, object).\\n"
    "Rules:\\n"
    "1. Extract ALL key facts, definitions, and relationships.\\n"
    "2. Use simple, atomic subjects and objects (e.g. 'The process of photosynthesis' -> 'photosynthesis').\\n"
    "3. Return them as lines in the format: subject | predicate | object\\n"
    "4. If you find nothing, return an empty string."
)


def extract_triples_from_text(text: str) -> List[Dict[str, str]]:
    """
    Use the LLM to extract subject–predicate–object triples from text.
    """
    if not text.strip():
        return []

    prompt = (
        "Extract factual triples from the following text.\\n\\n"
        f"TEXT:\\n{text}\\n\\n"
        "TRIPLES (one per line, 'subject | predicate | object'):"
    )

    msg = [
        ("system", TRIPLE_EXTRACTION_SYSTEM),
        ("user", prompt),
    ]
    
    # Robust retry logic with backoff
    max_retries = 12
    for attempt in range(max_retries):
        try:
            response = llm.invoke(msg)
            content = response.content.strip()

            triples: List[Dict[str, str]] = []
            for line in content.splitlines():
                line = line.strip()
                if not line or "|" not in line:
                    continue
                parts = [p.strip() for p in line.split("|")]
                if len(parts) != 3:
                    continue
                s, p, o = parts
                # Validate that we have non-empty values
                if s and p and o:
                    triples.append({"s": s, "p": p, "o": o})
            return triples
            
        except Exception as e:
            err_str = str(e).lower()
            # Check for rate limit (429 or 'rate_limit')
            if ("429" in err_str or "rate_limit" in err_str) and attempt < max_retries - 1:
                wait_time = (2 ** attempt) + 2  # 3s, 4s, 6s, 10s...
                print(f"KG Rate limit hit. Retrying in {wait_time}s...")
                import time
                time.sleep(wait_time)
                continue
            else:
                print(f"Error extracting triples (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    # Last attempt failed
                    print(f"Failed to extract triples after {max_retries} attempts")
                return []
    return []


# ---------- Upsert into Neo4j ----------

def upsert_kg_from_chunks(chunks, doc_id: str) -> None:
    """
    Given LangChain Document chunks, extract triples and upsert them into Neo4j.
    """
    driver = get_driver()
    
    # Check if Neo4j is available
    if driver is None:
        print("⚠️ Neo4j is not available - skipping knowledge graph extraction")
        return

    all_triples: List[Dict[str, str]] = []

    # Optimization: Process every 2nd chunk (50% coverage) to balance speed and completeness
    # Previously was 20% coverage [::5] which missed too many details.
    chunks_to_process = chunks[::2]
    
    print(f"Building KG from {len(chunks_to_process)} chunks (sampled from {len(chunks)})...")
    
    for ch in chunks_to_process:
        text = ch.page_content
        # skip very short chunks
        if len(text) < 100:
            continue
        triples = extract_triples_from_text(text)
        all_triples.extend(triples)
        
        # Small delay to be nice to the API
        import time
        time.sleep(1.0)

    if not all_triples:
        print("No triples extracted from chunks.")
        return

    # Upload triples in batches to avoid Neo4j transaction timeouts
    BATCH_SIZE = 500
    cypher = """
    UNWIND $triples AS t
    MERGE (s:Entity {name: t.s})
    MERGE (o:Entity {name: t.o})
    MERGE (s)-[r:RELATES_TO {predicate: t.p, doc_id: $doc_id}]->(o)
    """

    with driver.session() as session:
        for i in range(0, len(all_triples), BATCH_SIZE):
            batch = all_triples[i:i + BATCH_SIZE]
            session.run(cypher, triples=batch, doc_id=doc_id)
            print(f"Uploaded KG batch {i // BATCH_SIZE + 1} ({len(batch)} triples)")


# ---------- Entity Extraction for Query Filtering ----------

ENTITY_EXTRACTION_SYSTEM = (
    "You are an expert at identifying key entities and concepts from a user query for a Knowledge Graph lookup. "
    "Your goal is to extract keywords that are likely to exist as Nodes in the graph. "
    "Rules:\n"
    "1. Extract important nouns, proper nouns, or technical terms.\n"
    "2. EXPAND terms with synonyms, root forms, and variations (e.g. 'flight' -> 'flight | flying | fly | aviation').\n"
    "3. For TITLES or PHRASES, also provide the core words (e.g. 'His First Flight' -> 'His First Flight | First Flight | Flight').\n"
    "4. If the query is in English, YOU MUST provide Tamil translations for key terms (e.g. 'sun' -> 'sun | சூரியன்').\n"
    "5. Keep compound nouns together but ALSO provide the head noun (e.g. 'solar energy' -> 'solar energy | energy').\n"
    "6. Ignore generic words like 'process', 'type', 'way', 'details' unless part of a specific term.\n"
    "7. Return them as a pipe-separated list.\n"
    "8. If the query is conversational or has no specific entities, return an empty string."
)

def extract_entities_from_query(query: str) -> List[str]:
    """
    Extract key entities from the user query to filter KG results.
    Uses deterministic LLM (temp=0) for stability.
    """
    if not query.strip():
        return []
        
    msg = [
        ("system", ENTITY_EXTRACTION_SYSTEM),
        ("user", f"Extract entities from this query: {query}"),
    ]
    
    try:
        # Use deterministic LLM
        response = llm_deterministic.invoke(msg)
        content = response.content.strip()
        
        if not content:
            return []
            
        # Split by pipe and clean
        entities = [e.strip() for e in content.split("|") if e.strip()]
        return entities
        
    except Exception as e:
        print(f"Error extracting entities from query: {e}")
        return []


def filter_relevant_triples(query: str, triples: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Use LLM to filter out triples that are not semantically relevant to the query.
    This prevents 'keyword matching' hallucinations.
    """
    if not triples:
        return []
    
    # Format triples for LLM
    triples_text = ""
    for i, t in enumerate(triples):
        triples_text += f"{i}: {t['s']} | {t['p']} | {t['o']}\n"
        
    system_prompt = (
        "You are a helpful relevance filter. "
        "Given a user query and a numbered list of facts (triples), "
        "return ONLY the numbers of the triples that are potentially useful to answer the query or provide context. "
        "Be generous: if a triple is related to the main concepts, include it. "
        "Return numbers separated by commas (e.g. '0, 2, 5'). "
        "If none are relevant, return 'NONE'."
    )
    
    msg = [
        ("system", system_prompt),
        ("user", f"Query: {query}\n\nTriples:\n{triples_text}"),
    ]
    
    try:
        response = llm_deterministic.invoke(msg)
        content = response.content.strip()
        
        if "NONE" in content:
            return []
            
        # Parse numbers
        indices = []
        for part in content.split(","):
            part = part.strip()
            if part.isdigit():
                indices.append(int(part))
                
        filtered = [triples[i] for i in indices if i < len(triples)]
        return filtered
        
    except Exception as e:
        print(f"Error filtering triples: {e}")
        return triples  # Fallback: return all if filter fails


def query_kg_for_query(query: str, doc_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Query the knowledge graph - returns ONLY triples relevant to the query entities.
    """
    driver = get_driver()
    
    # Check if Neo4j is available
    if driver is None:
        print("Neo4j is not available - returning empty results")
        return []
        
    # 1. Extract entities from the query
    entities = extract_entities_from_query(query)
    print(f"Extracted entities for KG query: {entities}")
    
    if not entities:
        print("No entities found in query - skipping KG lookup")
        return []
    
    # 2. Query for triples involving these entities (fuzzy match)
    # We use case-insensitive substring matching for broader recall
    if doc_id:
        cypher = """
        MATCH (s:Entity)-[r:RELATES_TO]->(o:Entity)
        WHERE r.doc_id = $doc_id
        AND (
            any(e IN $entities WHERE toLower(s.name) CONTAINS toLower(e)) OR 
            any(e IN $entities WHERE toLower(o.name) CONTAINS toLower(e))
        )
        RETURN s.name AS s, r.predicate AS p, o.name AS o
        LIMIT 50
        """
        params = {"doc_id": doc_id, "entities": entities}
    else:
        cypher = """
        MATCH (s:Entity)-[r:RELATES_TO]->(o:Entity)
        WHERE (
            any(e IN $entities WHERE toLower(s.name) CONTAINS toLower(e)) OR 
            any(e IN $entities WHERE toLower(o.name) CONTAINS toLower(e))
        )
        RETURN s.name AS s, r.predicate AS p, o.name AS o
        LIMIT 50
        """
        params = {"entities": entities}
    
    with driver.session() as session:
        result = session.run(cypher, **params)
        rows = [r.data() for r in result]
    
    if not rows:
        print(f"No matching triples found for entities: {entities}")
        return []
    
    print(f"Found {len(rows)} candidate triples. Filtering for relevance...")
    
    # 3. Filter for semantic relevance
    relevant_rows = filter_relevant_triples(query, rows)
    
    if not relevant_rows:
        print("Relevance filter removed all triples. Falling back to top 10 candidates.")
        return rows[:10]
    
    print(f"Found {len(relevant_rows)} relevant triples after filtering (from {len(rows)})")
    return relevant_rows

def get_random_triples(doc_id: Optional[str]) -> List[Dict[str, Any]]:
    """
    Get random triples for a document. Only used for initial exploration.
    """
    driver = get_driver()
    if driver is None:
        return []

    if doc_id:
        cypher = """
        MATCH (s:Entity)-[r:RELATES_TO]->(o:Entity)
        WHERE r.doc_id = $doc_id
        RETURN s.name AS s, r.predicate AS p, o.name AS o
        LIMIT 10
        """
        params = {"doc_id": doc_id}
    else:
        cypher = """
        MATCH (s:Entity)-[r:RELATES_TO]->(o:Entity)
        RETURN s.name AS s, r.predicate AS p, o.name AS o
        LIMIT 10
        """
        params = {}
        
    with driver.session() as session:
        result = session.run(cypher, **params)
        return [r.data() for r in result]
