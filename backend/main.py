# backend/main.py

import os
from uuid import uuid4
from datetime import datetime

import boto3
import requests
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from dotenv import load_dotenv

load_dotenv()

from ai_utils import extract_text, call_gemini_for_analysis



AWS_REGION = os.getenv("AWS_REGION")
FILES_TABLE_NAME = os.getenv("FILES_TABLE_NAME")
AI_RESULTS_TABLE_NAME = os.getenv("AI_RESULTS_TABLE_NAME")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

# AWS clients
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
files_table = dynamodb.Table(FILES_TABLE_NAME)
ai_results_table = dynamodb.Table(AI_RESULTS_TABLE_NAME)

s3 = boto3.client("s3", region_name=AWS_REGION)

app = FastAPI(title="AI File Processor")

# Allow Streamlit (running on localhost:8501) to call this API
origins = [
    "http://localhost",
    "http://localhost:8501",
    "http://127.0.0.1:8501",
    "*",   # relax for dev; tighten later in prod
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class UploadResponse(BaseModel):
    file_id: str
    message: str


class DownloadResponse(BaseModel):
    file_id: str
    download_url: str


@app.get("/")
def root():
    return {"message": "AI File Processor Backend is running"}


# ----------------- UPLOAD ----------------- #

@app.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)):
    try:
        file_id = str(uuid4())
        s3_key = f"uploads/{file_id}_{file.filename}"

        # Upload to S3
        s3.upload_fileobj(file.file, S3_BUCKET_NAME, s3_key)

        # Public URL (assuming bucket or object made public read)
        s3_url = f"https://{S3_BUCKET_NAME}.s3.amazonaws.com/{s3_key}"

        # Save metadata in FilesTable
        files_table.put_item(Item={
            "file_id": file_id,
            "filename": file.filename,
            "s3_url": s3_url,
            "s3_key": s3_key,
            "upload_date": datetime.utcnow().isoformat(),
            "status": "UPLOADED",
        })

        return UploadResponse(file_id=file_id, message="File uploaded successfully.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")


# ----------------- DOWNLOAD ----------------- #

@app.get("/download/{file_id}", response_model=DownloadResponse)
def download_file(file_id: str):
    resp = files_table.get_item(Key={"file_id": file_id})
    item = resp.get("Item")

    if not item:
        raise HTTPException(status_code=404, detail="File not found")

    return DownloadResponse(file_id=file_id, download_url=item["s3_url"])


# ----------------- PROCESS (TEXT + GEMINI) ----------------- #

# @app.post("/process/{file_id}")
# def process_file(file_id: str):
#     # 1. Get file metadata
#     resp = files_table.get_item(Key={"file_id": file_id})
#     file_item = resp.get("Item")

#     if not file_item:
#         raise HTTPException(status_code=404, detail="Invalid file_id")

#     s3_url = file_item["s3_url"]
#     filename = file_item["filename"]

#     # 2. Download file content from S3 (public URL)
#     try:
#         file_bytes = requests.get(s3_url).content
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error downloading file: {e}")

#     # 3. Extract text
#     try:
#         text = extract_text(file_bytes, filename)
#         if not text.strip():
#             raise ValueError("No text extracted from file.")
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Text extraction failed: {e}")

#     # 4. Call Gemini for analysis
#     try:
#         ai_result = call_gemini_for_analysis(text)
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Gemini analysis failed: {e}")

#     # 5. Store in AIResultsTable
#     try:
#         ai_results_table.put_item(Item={
#             "file_id": file_id,
#             "summary": ai_result["summary"],
#             "insights": ai_result["insights"],
#             "topics": ai_result["topics"],
#             "sentiment": ai_result["sentiment"],
#             "processed_at": datetime.utcnow().isoformat(),
#         })

#         # Also update status in FilesTable
#         files_table.update_item(
#             Key={"file_id": file_id},
#             UpdateExpression="SET #s = :s",
#             ExpressionAttributeNames={"#s": "status"},
#             ExpressionAttributeValues={":s": "PROCESSED"},
#         )
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Failed to store AI result: {e}")

#     # 6. Return structured JSON to frontend
#     return JSONResponse(content=ai_result)


@app.post("/process/{file_id}")
def process_file(file_id: str):

    # 1. Get file metadata
    resp = files_table.get_item(Key={"file_id": file_id})
    file_item = resp.get("Item")

    if not file_item:
        raise HTTPException(status_code=404, detail="Invalid file_id")

    s3_url = file_item["s3_url"]
    filename = file_item["filename"]

    # ✅✅✅ 2. SAFELY EXTRACT s3_key FROM URL
    try:
        # Example URL:
        # https://bucket-name.s3.amazonaws.com/uploads/abc123-file.pdf
        s3_key = s3_url.split(".amazonaws.com/")[1]
    except Exception:
        raise HTTPException(status_code=500, detail="Invalid S3 URL format")

    # ✅✅✅ 3. DOWNLOAD USING BOTO3 (NOT requests)
    try:
        obj = s3.get_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
        file_bytes = obj["Body"].read()
        print("✅ Downloaded bytes:", len(file_bytes))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"S3 download failed: {e}")

    # ✅✅✅ 4. EXTRACT TEXT SAFELY
    try:
        text = extract_text(file_bytes, filename)
        if not text.strip():
            raise ValueError("No text extracted from file.")
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Text extraction failed: File corrupted or unreadable → {e}"
        )

    # ✅ 5. CALL GEMINI
    try:
        ai_result = call_gemini_for_analysis(text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gemini analysis failed: {e}")

    # ✅ 6. STORE RESULT IN AIResultsTable
    try:
        ai_results_table.put_item(Item={
            "file_id": file_id,
            "summary": ai_result["summary"],
            "insights": ai_result["insights"],
            "topics": ai_result["topics"],
            "sentiment": ai_result["sentiment"],
            "processed_at": datetime.utcnow().isoformat(),
        })

        files_table.update_item(
            Key={"file_id": file_id},
            UpdateExpression="SET #s = :s",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": "PROCESSED"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store AI result: {e}")

    # ✅ 7. RETURN JSON TO FRONTEND
    return JSONResponse(content=ai_result)
