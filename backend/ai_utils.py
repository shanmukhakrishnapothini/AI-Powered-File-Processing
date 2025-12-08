# backend/ai_utils.py

import io
import json
import os
from typing import Dict, Any

from pypdf import PdfReader
import docx

from dotenv import load_dotenv

load_dotenv()
import google.generativeai as genai



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



# Configure Gemini once
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    MODEL = genai.GenerativeModel("gemini-1.5-flash")
else:
    MODEL = None


def call_gemini_for_analysis(text: str) -> Dict[str, Any]:
    """
    Calls Gemini and returns a dict with:
    - summary (string)
    - insights (list)
    - topics (list)
    - sentiment (string)
    """

    if not MODEL:
        # Fallback so the app still runs without API key
        return {
            "summary": "Gemini API key not configured.",
            "insights": ["No insights generated."],
            "topics": ["N/A"],
            "sentiment": "neutral",
        }

    prompt = f"""
You are an AI assistant. Analyze the following document text and return ONLY a JSON object
with the following keys:

- "summary": short summary as string
- "insights": list of 3–7 key insights
- "topics": list of topics
- "sentiment": one of ["positive", "neutral", "negative"]

Respond with ONLY valid JSON. No explanations, no markdown.

Text:
{text[:15000]}
    """

    response = MODEL.generate_content(prompt)
    raw_text = response.text.strip()

    # Try to parse as JSON directly
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        # Very basic fallback: wrap in a simple structure
        data = {
            "summary": raw_text[:500],
            "insights": ["Model did not return valid JSON."],
            "topics": [],
            "sentiment": "neutral",
        }

    # Ensure all keys exist
    return {
        "summary": data.get("summary", ""),
        "insights": data.get("insights", []),
        "topics": data.get("topics", []),
        "sentiment": data.get("sentiment", "neutral"),
    }
