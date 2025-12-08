# backend/ai_utils.py

import io
import os
import json
from typing import Dict, Any, List

from pypdf import PdfReader
import docx
from dotenv import load_dotenv

# LangChain + Gemini
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_ollama import OllamaEmbeddings


from langchain_openai import ChatOpenAI
from langchain_google_genai import (
    GoogleGenerativeAIEmbeddings,
    ChatGoogleGenerativeAI,
)

load_dotenv()

# -------------------- TEXT EXTRACTION -------------------- #

def extract_text(file_bytes: bytes, filename: str) -> str:
    """
    Extract text from different file types (pdf, txt, docx).
    """
    filename_lower = filename.lower()

    if filename_lower.endswith(".pdf"):
        return _extract_pdf_text(file_bytes)
    elif filename_lower.endswith(".txt"):
        return file_bytes.decode("utf-8", errors="ignore")
    elif filename_lower.endswith(".docx"):
        return _extract_docx_text(file_bytes)
    else:
        # Fallback: just try to decode
        return file_bytes.decode("utf-8", errors="ignore")


def _extract_pdf_text(file_bytes: bytes) -> str:
    pdf_stream = io.BytesIO(file_bytes)
    reader = PdfReader(pdf_stream)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text() or ""
        text += page_text + "\n"
    return text


def _extract_docx_text(file_bytes: bytes) -> str:
    doc_stream = io.BytesIO(file_bytes)
    doc = docx.Document(doc_stream)
    return "\n".join([p.text for p in doc.paragraphs])


# -------------------- RAG SETUP (LangChain + Gemini) -------------------- #

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY not set in environment")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set in environment")

llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.3,
    api_key=OPENAI_API_KEY
)


# LLM for generation
# llm = ChatGoogleGenerativeAI(
#     model="gemini-1.0-pro",
#     temperature=0.3,
#     google_api_key=GEMINI_API_KEY
# )

# ✅ Embeddings using API key (NOT Google Cloud ADC)
# embeddings = GoogleGenerativeAIEmbeddings(
#     model="models/embedding-001",
#     google_api_key=GEMINI_API_KEY
# )

embeddings=OllamaEmbeddings(
    model="mxbai-embed-large"
)


def rag_pipeline(document_text: str) -> Dict[str, Any]:
   
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=150,
    )
    chunks: List[str] = splitter.split_text(document_text)
    print(f"Total Chunks Created: {len(chunks)}")

    if not chunks:
        return {
            "summary": "No content available.",
            "insights": [],
            "topics": [],
            "sentiment": "neutral",
        }

    # 2) Build vector store (FAISS in-memory)
    vector_store = FAISS.from_texts(chunks, embedding=embeddings)

    # 3) Retrieve relevant chunks
    retriever = vector_store.as_retriever(search_kwargs={"k": 4})
    retrieved_docs = retriever.invoke(
        "Summarize and analyze this document"
    )
    retrieved_text = "\n\n".join(doc.page_content for doc in retrieved_docs)

    # 4) Ask Gemini using retrieved context only
    prompt = f"""
You are an AI assistant. Using ONLY the retrieved context below, return a valid JSON
with the following format:

{{
  "summary": "...",
  "insights": ["...", "..."],
  "topics": ["...", "..."],
  "sentiment": "positive" | "neutral" | "negative"
}}

Do NOT add explanations.
Do NOT wrap in markdown.
Do NOT add extra keys.

Retrieved context:
{retrieved_text}
    """

    response = llm.invoke(prompt)
    raw_text = response.content.strip()

    # 5) Parse JSON safely
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        # fallback when model doesn't strictly follow instructions
        data = {
            "summary": raw_text[:500],
            "insights": ["Model returned non-JSON output"],
            "topics": [],
            "sentiment": "neutral",
        }

    return {
        "summary": data.get("summary", ""),
        "insights": data.get("insights", []),
        "topics": data.get("topics", []),
        "sentiment": data.get("sentiment", "neutral"),
    }
