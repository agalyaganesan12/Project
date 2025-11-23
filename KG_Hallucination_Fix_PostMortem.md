# Knowledge Graph Hallucination Fix - Post Mortem & Error Log

This document summarizes the logical and technical errors encountered while addressing the issue of Knowledge Graph (KG) hallucinations and the subsequent fixes implemented.

## 0. Fundamental Design Difficulties (From the Beginning)

### 0.1. Naive KG Retrieval Strategy
*   **The Initial Flaw:** The original design assumed that if a user selects a document, *all* Knowledge Graph facts extracted from that document are relevant context for *any* query.
*   **Why it failed:** For specific questions (e.g., "What is the theme?"), feeding the LLM hundreds of unrelated facts (e.g., specific dates, minor characters) confused the model, leading to hallucinations where it tried to force-fit unrelated facts into the answer.
*   **The Lesson:** RAG systems must filter *both* unstructured text (vector search) *and* structured data (KG) based on query relevance.

### 0.2. The Precision vs. Recall Trade-off
*   **The Challenge:** Finding the "sweet spot" for filtering was the hardest part of this implementation.
    *   **Too Strict:** When we filtered strictly by entities, we missed relevant info (e.g., "His First Flight" didn't match "First Flight").
    *   **Too Loose:** When we didn't filter enough, the system returned irrelevant info for queries like "Capital of France", causing hallucinations.
*   **The Solution:** A multi-layered approach:
    1.  **Robust Entity Extraction:** Using an LLM to expand terms (synonyms, translations).
    2.  **Fuzzy Matching:** Using `CONTAINS` in Cypher.
    3.  **Semantic Verification:** Using a second LLM step to verify relevance, but with a "generous" prompt and a safety fallback.

## 1. Logical Errors

### 1.1. Unfiltered KG Queries (Root Cause of Hallucination)
*   **Issue:** The initial implementation of `query_kg_for_query` returned **all** triples associated with a document, regardless of the user's specific question.
*   **Impact:** When a user asked an irrelevant question (e.g., "Capital of France"), the LLM received a context full of unrelated facts from the book, leading it to hallucinate an answer or get confused.
*   **Fix:** Implemented **Entity-Based Filtering**. We now extract key entities from the user's query and only return triples that contain those entities (or fuzzy matches).

### 1.2. Strict Entity Matching (Recall Issue)
*   **Issue:** The initial entity extraction was too literal.
    *   Query: "His First Flight" -> Entity: "His First Flight". Graph Node: "First Flight". Result: No match.
    *   Query: "flight" -> Entity: "flight". Graph Node: "Flying". Result: No match.
*   **Impact:** Relevant queries returned no results, causing the KG to be useless for valid questions.
*   **Fix:** Updated the `ENTITY_EXTRACTION_SYSTEM` prompt to:
    *   **Strip articles/pronouns** from titles.
    *   **Expand synonyms** and variations (e.g., "flight" -> "flight | flying | aviation").
    *   **Provide multilingual translations** (e.g., English -> Tamil) for better matching in non-English texts.

### 1.3. Over-Aggressive Relevance Filtering
*   **Issue:** We introduced a secondary "Relevance Filter" (LLM step) to verify if retrieved triples were actually relevant. The initial prompt was "Strict", causing it to discard useful context that wasn't explicitly mentioned in the query.
*   **Impact:** Users saw "No relevant info found" even when the KG had data.
*   **Fix:**
    *   Relaxed the prompt to be **"Helpful" and "Generous"**.
    *   Added a **Fallback Mechanism**: If the filter removes all triples, the system now returns the top 10 candidate triples instead of nothing, ensuring we don't return an empty result due to over-filtering.

### 1.4. Incomplete Data Ingestion (Sampling)
*   **Issue:** The `upsert_kg_from_chunks` function was processing only **20%** of the document chunks (`chunks[::5]`) to save time.
*   **Impact:** Many key details were simply not in the graph. Queries for specific details (e.g., "flight") failed because those specific paragraphs were skipped during ingestion.
*   **Fix:** Increased sampling to **50%** (`chunks[::2]`) and updated the extraction prompt to capture **"ALL key facts"** instead of a "small number".

## 2. Technical Errors

### 2.1. Unicode Encoding Errors (Windows)
*   **Issue:** The debug script used emojis (✅, ⚠️) and printed Tamil characters to the console. On Windows `cmd.exe` (cp1252 encoding), this caused `UnicodeEncodeError` and crashed the script.
*   **Fix:**
    *   Removed emojis from log messages in `src/kg.py`.
    *   Added `sys.stdout.reconfigure(encoding='utf-8')` in the debug script.

### 2.2. Missing Import (`NameError`)
*   **Issue:** During a refactor to add `langchain_openai`, the import `from neo4j import GraphDatabase` was accidentally removed.
*   **Impact:** The application crashed with `NameError: name 'GraphDatabase' is not defined` when trying to connect to Neo4j.
*   **Fix:** Restored the missing import.

### 2.3. File Truncation (Tooling Error)
*   **Issue:** The `replace_file_content` tool failed to correctly match the context for a large edit block, resulting in a truncated and syntactically invalid `src/kg.py` file.
*   **Impact:** The code was broken with missing functions.
*   **Fix:** Completely rewrote the file using `write_to_file` to ensure integrity.

### 2.4. Non-Deterministic LLM Output
*   **Issue:** The entity extraction was using the default LLM temperature (0.2). This caused inconsistent results where a query might work once and fail the next time ("hallucinating while rerunning").
*   **Fix:** Instantiated a dedicated `llm_deterministic` with **temperature=0.0** for all logic-critical steps (extraction, filtering).

## Summary of Robustness Improvements
The final solution is robust because:
1.  **Ingestion** covers more data (50% vs 20%).
2.  **Querying** uses semantic expansion (synonyms, translations) to find nodes.
3.  **Filtering** prevents hallucinations but has a safety net (fallback) to ensure recall.
4.  **Stability** is enforced via deterministic LLM calls.
