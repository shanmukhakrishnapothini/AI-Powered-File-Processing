import os
from uuid import uuid4
from datetime import datetime

import boto3
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from pymongo import MongoClient

from ai_utils import extract_text, rag_pipeline

load_dotenv()


AWS_REGION = os.getenv("AWS_REGION")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

if not AWS_REGION or not S3_BUCKET_NAME:
    raise RuntimeError("AWS_REGION and S3_BUCKET_NAME must be set in .env")

s3 = boto3.client("s3", region_name=AWS_REGION)


MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "ai_file_processor")

if not MONGO_URI:
    raise RuntimeError("MONGO_URI must be set in .env")

mongo_client = MongoClient(MONGO_URI)
db = mongo_client[MONGO_DB_NAME]

files_collection = db["files"]
results_collection = db["results"]


app = FastAPI(title="AI File Processor with MongoDB")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


class FileRequest(BaseModel):
    file_id: str


@app.get("/")
def root():
    return {"message": "AI File Processor (MongoDB + S3 + RAG) is running"}


@app.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)):
    try:
        file_id = str(uuid4())
        s3_key = f"uploads/{file_id}_{file.filename}"

        s3.upload_fileobj(file.file, S3_BUCKET_NAME, s3_key)

        s3_url = f"https://{S3_BUCKET_NAME}.s3.amazonaws.com/{s3_key}"

        files_collection.insert_one({
            "file_id": file_id,
            "filename": file.filename,
            "s3_key": s3_key,
            "s3_url": s3_url,
            "upload_date": datetime.utcnow(),
            "status": "UPLOADED",
        })

        return UploadResponse(file_id=file_id, message="File uploaded successfully")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")


@app.get("/download/{file_id}", response_model=DownloadResponse)
def download_file(file_id: str):

    item = files_collection.find_one({"file_id": file_id})

    if not item:
        raise HTTPException(status_code=404, detail="File not found")

    s3_key = item["s3_key"]

    try:
        presigned_url = s3.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": S3_BUCKET_NAME,
                "Key": s3_key
            },
            ExpiresIn=60
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Presigned URL failed: {e}")

    return DownloadResponse(file_id=file_id, download_url=presigned_url)


@app.post("/process/{file_id}")
def process_file(file_id: str):

    file_item = files_collection.find_one({"file_id": file_id})

    if not file_item:
        raise HTTPException(status_code=404, detail="Invalid file_id")

    s3_key = file_item["s3_key"]
    filename = file_item["filename"]

    try:
        obj = s3.get_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
        file_bytes = obj["Body"].read()
        print("✅ Downloaded bytes:", len(file_bytes))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"S3 download failed: {e}")

    text = extract_text(file_bytes, filename)
    if not text.strip():
        raise HTTPException(status_code=400, detail="No text extracted")

    ai_result = rag_pipeline(text)

    results_collection.insert_one({
        "file_id": file_id,
        "summary": ai_result["summary"],
        "insights": ai_result["insights"],
        "topics": ai_result["topics"],
        "sentiment": ai_result["sentiment"],
        "processed_at": datetime.utcnow(),
    })

    files_collection.update_one(
        {"file_id": file_id},
        {"$set": {"status": "PROCESSED"}}
    )
    print(ai_result)
    return JSONResponse(content=ai_result)


@app.get("/results/{file_id}")
def get_results(file_id: str):
    item = results_collection.find_one(
        {"file_id": file_id},
        {"_id": 0}
    )

    if not item:
        raise HTTPException(status_code=404, detail="No AI result found")

    return item


@app.post("/extract-text")
def extract_text_api(req: FileRequest):

    file_item = files_collection.find_one({"file_id": req.file_id})
    if not file_item:
        raise HTTPException(status_code=404, detail="Invalid file_id")

    s3_key = file_item["s3_key"]
    filename = file_item["filename"]

    obj = s3.get_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
    file_bytes = obj["Body"].read()

    text = extract_text(file_bytes, filename)

    from langchain_text_splitters import RecursiveCharacterTextSplitter
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=150)
    chunks = splitter.split_text(text)

    print(f"text_length: {len(text)},total_chunks: {len(chunks)}, chunks: {chunks}")

    return {
        "file_id": req.file_id,
        "text_length": len(text),
        "total_chunks": len(chunks),
        "chunks": chunks,
    }


@app.post("/summarize")
def summarize_api(req: FileRequest):

    file_item = files_collection.find_one({"file_id": req.file_id})
    if not file_item:
        raise HTTPException(status_code=404, detail="Invalid file_id")

    s3_key = file_item["s3_key"]
    filename = file_item["filename"]

    obj = s3.get_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
    file_bytes = obj["Body"].read()

    text = extract_text(file_bytes, filename)

    result = rag_pipeline(text)

    print(result["summary"])

    return {
        "file_id": req.file_id,
        "summary": result["summary"],
    }


@app.post("/analyze")
def analyze_api(req: FileRequest):

    file_item = files_collection.find_one({"file_id": req.file_id})
    if not file_item:
        raise HTTPException(status_code=404, detail="Invalid file_id")

    s3_key = file_item["s3_key"]
    filename = file_item["filename"]

    obj = s3.get_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
    file_bytes = obj["Body"].read()

    text = extract_text(file_bytes, filename)

    result = rag_pipeline(text)
    print(f"insights: {result["insights"]}, topics: {result["topics"]}, sentiment: {result["sentiment"]}")

    return {
        "file_id": req.file_id,
        "insights": result["insights"],
        "topics": result["topics"],
        "sentiment": result["sentiment"],
    }

