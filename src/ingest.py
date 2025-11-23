# src/ingest.py
import io
import os
import base64
import fitz  # pymupdf
from typing import List, Optional

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage

from .vector_store import add_chunks
from .kg import upsert_kg_from_chunks
from .config import llm, llm_vision

STATIC_IMG_DIR = "static/images"
os.makedirs(STATIC_IMG_DIR, exist_ok=True)

def _encode_image_bytes(img_bytes: bytes) -> str:
    return base64.b64encode(img_bytes).decode("utf-8")

def _analyze_image_with_gpt(img_bytes: bytes, prompt_text: str) -> str:
    """
    Send image to GPT-4o-mini for description or OCR.
    """
    b64_img = _encode_image_bytes(img_bytes)
    
    message = HumanMessage(
        content=[
            {"type": "text", "text": prompt_text},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64_img}"},
            },
        ]
    )
    
    try:
        # Robust retry logic with backoff
        max_retries = 12
        for attempt in range(max_retries):
            try:
                # Use the vision-capable model
                response = llm_vision.invoke([message])
                return response.content.strip()
            except Exception as e:
                err_str = str(e).lower()
                # Check for rate limit (429 or 'rate_limit')
                if ("429" in err_str or "rate_limit" in err_str) and attempt < max_retries - 1:
                    wait_time = (2 ** attempt) + 2  # 3s, 4s, 6s, 10s...
                    print(f"Rate limit hit. Retrying in {wait_time}s...")
                    import time
                    time.sleep(wait_time)
                    continue
                else:
                    raise e
    except Exception as e:
        print(f"Error analyzing image: {e}")
        return ""

def _process_pdf_page(
    doc_pdf: fitz.Document, 
    page_num: int, 
    doc_id: str, 
    file_name: str,
    deep_ocr: bool = True
) -> List[Document]:
    """
    Process a single page:
    1. Extract text (fallback to VLM OCR if empty/sparse AND deep_ocr=True).
    2. Extract images -> Caption them -> Save to disk (only if deep_ocr=True).
    """
    page = doc_pdf.load_page(page_num)
    docs = []
    
    # 1. Text Extraction
    text = page.get_text()
    
    # Heuristic: If text is very short, it might be a scanned page or image-heavy.
    if len(text.strip()) < 50 and deep_ocr:
        print(f"Page {page_num + 1} seems scanned/empty. Using VLM OCR...")
        pix = page.get_pixmap()
        img_bytes = pix.tobytes("png")
        ocr_text = _analyze_image_with_gpt(
            img_bytes, 
            "Transcribe the text on this page exactly as it appears. If there is Tamil text, transcribe it accurately in Tamil."
        )
        if ocr_text:
            text = ocr_text

    if text.strip():
        docs.append(Document(
            page_content=text,
            metadata={
                "source": file_name,
                "page": page_num + 1,
                "doc_id": doc_id,
                "type": "text"
            }
        ))

    # 2. Image Extraction (Skip if deep_ocr is False)
    if deep_ocr:
        image_list = page.get_images(full=True)
        for img_index, img in enumerate(image_list):
            xref = img[0]
            base_image = doc_pdf.extract_image(xref)
            image_bytes = base_image["image"]
            ext = base_image["ext"]
            
            # Filter small icons/lines
            if len(image_bytes) < 10000:  # Skip images < 10KB (increased threshold)
                continue
                
            # Save image locally
            image_filename = f"{doc_id}_p{page_num+1}_i{img_index}.{ext}"
            image_path = os.path.join(STATIC_IMG_DIR, image_filename)
            
            with open(image_path, "wb") as f:
                f.write(image_bytes)
                
            # Generate description
            description = _analyze_image_with_gpt(
                image_bytes,
                "Describe this image in detail. If it's a chart or diagram, explain the data. If it contains text, transcribe it."
            )
            
            if description:
                docs.append(Document(
                    page_content=f"Image Description: {description}",
                    metadata={
                        "source": file_name,
                        "page": page_num + 1,
                        "doc_id": doc_id,
                        "image_path": image_path,
                        "type": "image"
                    }
                ))
            
    return docs

def ingest_pdf(file_bytes: bytes, file_name: str, doc_id: str, deep_ocr: bool = False, progress_callback=None) -> str:
    """
    Ingest PDF with optional enhanced OCR and Image handling.
    Uses batch processing to handle large files efficiently.
    
    Args:
        file_bytes: PDF file content
        file_name: Name of the file
        doc_id: Unique document ID
        deep_ocr: Whether to perform deep OCR and image analysis
        progress_callback: Optional callback function(current_page, total_pages)
    """
    doc_pdf = fitz.open(stream=file_bytes, filetype="pdf")
    
    total_pages = len(doc_pdf)
    print(f"Processing {file_name} ({total_pages} pages) [Deep OCR: {deep_ocr}]...")
    
    # Process in batches to avoid memory issues with large files
    BATCH_SIZE = 50
    
    import time
    
    for batch_start in range(0, total_pages, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, total_pages)
        batch_docs = []
        
        print(f"Processing pages {batch_start + 1} to {batch_end}...")
        
        for i in range(batch_start, batch_end):
            try:
                page_docs = _process_pdf_page(doc_pdf, i, doc_id, file_name, deep_ocr=deep_ocr)
                batch_docs.extend(page_docs)
                
                # Report progress
                if progress_callback:
                    progress_callback(i + 1, total_pages)
                
                # Only delay if we are doing deep OCR (which hits API)
                if deep_ocr:
                    time.sleep(3.0)
                else:
                    # No delay for pure text extraction
                    pass 
            except Exception as e:
                print(f"Skipping page {i+1} due to error: {e}")
                continue
        
        # Process this batch: chunk and upload
        if batch_docs:
            # Optimize chunk size for large documents
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=1500,  # Increased from 1000 for efficiency
                chunk_overlap=200,
                separators=["\n\n", "\n", ".", "!", "?"]
            )
            
            chunks = splitter.split_documents(batch_docs)
            
            # Save to vector DB (already batched internally)
            add_chunks(chunks)
            
            # Update KG for this batch
            upsert_kg_from_chunks(chunks, doc_id=doc_id)
            
            print(f"Uploaded batch {batch_start // BATCH_SIZE + 1} ({len(chunks)} chunks)")
            
            # Clear batch from memory
            del batch_docs
            del chunks
    
    doc_pdf.close()
    
    return doc_id

