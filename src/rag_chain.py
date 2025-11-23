# src/rag_chain.py
from typing import List, Tuple, Set, Dict, Union, Any

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate

from .config import llm
from .vector_store import get_vector_store

# Simple in-memory history for the session
# List of {"role": "user" | "assistant", "content": "..."}
message_history: List[Dict[str, str]] = []

def get_history_summary(limit: int = 6) -> str:
    """
    Return the last few turns of conversation as a string.
    """
    if not message_history:
        return ""
    
    recent = message_history[-limit:]
    lines = []
    for msg in recent:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        lines.append(f"{role.upper()}: {content}")
        
    return "\n".join(lines)


def get_retriever_for_doc(doc_id: str):
    """
    Build a retriever that only searches chunks belonging to this doc_id.
    """
    store = get_vector_store()
    retriever = store.as_retriever(
        search_type="similarity",
        search_kwargs={"k": 8, "filter": {"doc_id": doc_id}},
    )
    return retriever


def format_docs(docs: List[Document]) -> str:
    parts = []
    for d in docs:
        page = d.metadata.get("page")
        source_type = d.metadata.get("type", "text")
        prefix = f"[page {page} ({source_type})] " if page is not None else ""
        parts.append(prefix + d.page_content.strip())
    return "\n\n".join(parts)


# src/rag_chain.py
from typing import List, Tuple, Set, Dict

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate

from .config import llm
from .vector_store import get_vector_store

# Simple in-memory history for the session
# List of {"role": "user" | "assistant", "content": "..."}
message_history: List[Dict[str, str]] = []

def get_history_summary(limit: int = 6) -> str:
    """
    Return the last few turns of conversation as a string.
    """
    if not message_history:
        return ""
    
    recent = message_history[-limit:]
    lines = []
    for msg in recent:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        lines.append(f"{role.upper()}: {content}")
        
    return "\n".join(lines)


def get_retriever_for_doc(doc_id: str):
    """
    Build a retriever that only searches chunks belonging to this doc_id.
    """
    store = get_vector_store()
    retriever = store.as_retriever(
        search_type="similarity",
        search_kwargs={"k": 8, "filter": {"doc_id": doc_id}},
    )
    return retriever


def format_docs(docs: List[Document]) -> str:
    parts = []
    for d in docs:
        page = d.metadata.get("page")
        source_type = d.metadata.get("type", "text")
        prefix = f"[page {page} ({source_type})] " if page is not None else ""
        parts.append(prefix + d.page_content.strip())
    return "\n\n".join(parts)


RAG_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "You are a helpful tutor chatbot for a school textbook.\n"
                "CRITICAL RULES:\n"
                "1. Use ONLY the supplied context from the book. DO NOT use any external knowledge.\n"
                "2. If the question is NOT related to the book content, you MUST say: 'This question is not related to the uploaded document. I can only answer questions about the content in this book.'\n"
                "3. If the answer is not in the context, say: 'I don't know based on the document.'\n"
                "4. NEVER make up information. NEVER hallucinate.\n"
                "5. If the context is empty or irrelevant to the question, say you cannot answer.\n\n"
                "Answer in {answer_lang}.\n"
                "If the user question is in Tamil, answer in natural, simple Tamil. "
                "Otherwise answer in English unless answer_lang says otherwise."
            ),
        ),
        (
            "user",
            (
                "User question:\n{question}\n\n"
                "Conversation history (may be empty):\n{history}\n\n"
                "Relevant book context:\n{context}\n\n"
                "Knowledge graph facts:\n{kg_context}\n\n"
                "IMPORTANT: First check if the question is related to the book content above. "
                "If not related, say so. If related but not enough info, say you don't know. "
                "Only answer if you have clear information from the context."
            ),
        ),
    ]
)


def generate_answer_with_validation(
    question: str,
    history: str,
    docs: List[Document],
    kg_context: Union[str, List[Dict[str, Any]]] = "",
    answer_lang: str = "English",
) -> Tuple[str, float, List[str]]:
    """
    Core RAG call with hallucination prevention.
    Returns (answer_text, confidence_score, list_of_image_paths).
    """
    context_str = format_docs(docs)

    # Format KG context if it's a list
    kg_context_str = ""
    if isinstance(kg_context, list):
        lines = []
        for triple in kg_context:
            s = triple.get('s', '')
            p = triple.get('p', '')
            o = triple.get('o', '')
            if s and p and o:
                lines.append(f"{s} | {p} | {o}")
        kg_context_str = "\n".join(lines)
    elif isinstance(kg_context, str):
        kg_context_str = kg_context
    else:
        kg_context_str = str(kg_context)

    # Check if we have any context at all
    if not context_str.strip() and not kg_context_str.strip():
        return (
            "I don't have enough information from the book to answer this. "
            "Please make sure you've uploaded and indexed a document first.",
            0.0,
            [],
        )
    
    # Check relevance: if retrieved docs are very short or seem unrelated
    # This is a simple heuristic - we check if context is too sparse
    # But if we have KG context, we might still be able to answer
    if len(context_str.strip()) < 50 and not kg_context_str.strip():
        return (
            "The question doesn't seem to match the content in this document. "
            "I can only answer questions about the uploaded book.",
            0.1,
            [],
        )

    msgs = RAG_PROMPT.format_messages(
        question=question,
        history=history or "(no previous conversation)",
        context=context_str,
        kg_context=kg_context_str or "(no KG facts)",
        answer_lang=answer_lang,
    )

    response = llm.invoke(msgs)
    answer = response.content.strip()
    
    # Check if the LLM itself said it doesn't know or question is unrelated
    lower_answer = answer.lower()
    if any(phrase in lower_answer for phrase in [
        "not related to", 
        "don't know based on", 
        "cannot answer",
        "not in the document",
        "no information about"
    ]):
        confidence = 0.2
    else:
        # Confidence based on number of retrieved docs and their length
        confidence = min(1.0, 0.4 + 0.1 * len(docs) + (len(context_str) / 5000))
    
    # Extract image paths from relevant docs
    image_paths: Set[str] = set()
    for d in docs:
        if d.metadata.get("type") == "image":
            path = d.metadata.get("image_path")
            if path:
                image_paths.add(path)
                
    return answer, confidence, list(image_paths)
