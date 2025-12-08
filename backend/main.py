# # backend/main.py

# import os
# from uuid import uuid4
# from datetime import datetime

# import boto3
# from fastapi import FastAPI, File, UploadFile, HTTPException
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.responses import JSONResponse
# from pydantic import BaseModel
# from dotenv import load_dotenv

# from ai_utils import extract_text, rag_pipeline

# load_dotenv()

# AWS_REGION = os.getenv("AWS_REGION")
# FILES_TABLE_NAME = os.getenv("FILES_TABLE_NAME")
# AI_RESULTS_TABLE_NAME = os.getenv("AI_RESULTS_TABLE_NAME")
# S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

# if not all([AWS_REGION, FILES_TABLE_NAME, AI_RESULTS_TABLE_NAME, S3_BUCKET_NAME]):
#     raise RuntimeError("One or more AWS env vars are missing")

# # AWS clients
# dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
# files_table = dynamodb.Table(FILES_TABLE_NAME)
# ai_results_table = dynamodb.Table(AI_RESULTS_TABLE_NAME)
# s3 = boto3.client("s3", region_name=AWS_REGION)

# app = FastAPI(title="AI File Processor")

# # CORS for Streamlit
# origins = [
#     "http://localhost",
#     "http://localhost:8501",
#     "http://127.0.0.1:8501",
#     "*",   # relax for dev
# ]

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=origins,
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )


# class UploadResponse(BaseModel):
#     file_id: str
#     message: str


# class DownloadResponse(BaseModel):
#     file_id: str
#     download_url: str


# @app.get("/")
# def root():
#     return {"message": "AI File Processor Backend is running"}


# # ----------------- UPLOAD ----------------- #

# @app.post("/upload", response_model=UploadResponse)
# async def upload_file(file: UploadFile = File(...)):
#     """
#     1. Generate UUID
#     2. Upload file to S3
#     3. Save metadata to FilesTable
#     """
#     try:
#         file_id = str(uuid4())
#         s3_key = f"uploads/{file_id}_{file.filename}"

#         # Upload file stream directly to S3
#         s3.upload_fileobj(file.file, S3_BUCKET_NAME, s3_key)

#         # Public-style URL (even if bucket is private, we still store for reference)
#         s3_url = f"https://{S3_BUCKET_NAME}.s3.amazonaws.com/{s3_key}"

#         files_table.put_item(Item={
#             "file_id": file_id,
#             "filename": file.filename,
#             "s3_url": s3_url,
#             "s3_key": s3_key,
#             "upload_date": datetime.utcnow().isoformat(),
#             "status": "UPLOADED",
#         })

#         return UploadResponse(file_id=file_id, message="File uploaded successfully.")
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Upload failed: {e}")


# # ----------------- DOWNLOAD ----------------- #

# @app.get("/download/{file_id}", response_model=DownloadResponse)
# def download_file(file_id: str):
#     """
#     Return the stored S3 URL for the file.
#     """
#     resp = files_table.get_item(Key={"file_id": file_id})
#     item = resp.get("Item")

#     if not item:
#         raise HTTPException(status_code=404, detail="File not found")

#     return DownloadResponse(file_id=file_id, download_url=item["s3_url"])


# # ----------------- PROCESS (Text Extraction + RAG + Gemini) ----------------- #

# @app.post("/process/{file_id}")
# def process_file(file_id: str):
#     """
#     Pipeline:
#       1. Get file metadata from DynamoDB
#       2. Download file bytes from S3
#       3. Extract text (PDF/TXT/DOCX)
#       4. Run RAG pipeline (LangChain + FAISS + Gemini)
#       5. Store result in AIResultsTable
#       6. Return structured JSON
#     """

#     # 1. Metadata
#     resp = files_table.get_item(Key={"file_id": file_id})
#     file_item = resp.get("Item")

#     if not file_item:
#         raise HTTPException(status_code=404, detail="Invalid file_id")

#     s3_key = file_item["s3_key"]
#     filename = file_item["filename"]

#     # 2. Download from S3 via boto3
#     try:
#         obj = s3.get_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
#         file_bytes = obj["Body"].read()
#         print("✅ Downloaded bytes:", len(file_bytes))
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"S3 download failed: {e}")

#     # 3. Extract text
#     try:
#         text = extract_text(file_bytes, filename)
#         if not text.strip():
#             raise ValueError("No text extracted from file.")
#     except Exception as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Text extraction failed: {e}"
#         )

#     # 4. RAG + Gemini
#     try:
#         ai_result = rag_pipeline(text)
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"RAG pipeline failed: {e}")

#     # 5. Store result
#     try:
#         ai_results_table.put_item(Item={
#             "file_id": file_id,
#             "summary": ai_result["summary"],
#             "insights": ai_result["insights"],
#             "topics": ai_result["topics"],
#             "sentiment": ai_result["sentiment"],
#             "processed_at": datetime.utcnow().isoformat(),
#         })

#         files_table.update_item(
#             Key={"file_id": file_id},
#             UpdateExpression="SET #s = :s",
#             ExpressionAttributeNames={"#s": "status"},
#             ExpressionAttributeValues={":s": "PROCESSED"},
#         )
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Failed to store AI result: {e}")

#     # 6. Return JSON
#     return JSONResponse(content=ai_result)


# @app.get("/results/{file_id}")
# def get_results(file_id: str):
#     resp = ai_results_table.get_item(Key={"file_id": file_id})
#     item = resp.get("Item")

#     if not item:
#         raise HTTPException(status_code=404, detail="No AI result found for this file")

#     return item



# backend/main.py

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

# ------------------- AWS S3 ------------------- #

AWS_REGION = os.getenv("AWS_REGION")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

if not AWS_REGION or not S3_BUCKET_NAME:
    raise RuntimeError("AWS_REGION and S3_BUCKET_NAME must be set in .env")

s3 = boto3.client("s3", region_name=AWS_REGION)

# ------------------- MONGODB ------------------- #

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "ai_file_processor")

if not MONGO_URI:
    raise RuntimeError("MONGO_URI must be set in .env")

mongo_client = MongoClient(MONGO_URI)
db = mongo_client[MONGO_DB_NAME]

files_collection = db["files"]
results_collection = db["results"]

# ------------------- FASTAPI APP ------------------- #

app = FastAPI(title="AI File Processor with MongoDB")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------- SCHEMAS ------------------- #

class UploadResponse(BaseModel):
    file_id: str
    message: str


class DownloadResponse(BaseModel):
    file_id: str
    download_url: str


class FileRequest(BaseModel):
    file_id: str

# ------------------- ROOT ------------------- #

@app.get("/")
def root():
    return {"message": "AI File Processor (MongoDB + S3 + RAG) is running"}

# ------------------- UPLOAD ------------------- #

@app.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)):
    try:
        file_id = str(uuid4())
        s3_key = f"uploads/{file_id}_{file.filename}"

        # ✅ Upload file to S3
        s3.upload_fileobj(file.file, S3_BUCKET_NAME, s3_key)

        s3_url = f"https://{S3_BUCKET_NAME}.s3.amazonaws.com/{s3_key}"

        # ✅ Store metadata in MongoDB
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

# ------------------- DOWNLOAD ------------------- #

@app.get("/download/{file_id}", response_model=DownloadResponse)
def download_file(file_id: str):
    item = files_collection.find_one({"file_id": file_id})

    if not item:
        raise HTTPException(status_code=404, detail="File not found")

    return DownloadResponse(file_id=file_id, download_url=item["s3_url"])

# ------------------- PROCESS FILE (FULL PIPELINE) ------------------- #

@app.post("/process/{file_id}")
def process_file(file_id: str):

    # 1️⃣ Get metadata from MongoDB
    file_item = files_collection.find_one({"file_id": file_id})

    if not file_item:
        raise HTTPException(status_code=404, detail="Invalid file_id")

    s3_key = file_item["s3_key"]
    filename = file_item["filename"]

    # 2️⃣ Download file from S3
    try:
        obj = s3.get_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
        file_bytes = obj["Body"].read()
        print("✅ Downloaded bytes:", len(file_bytes))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"S3 download failed: {e}")

    # 3️⃣ Extract text
    text = extract_text(file_bytes, filename)
    if not text.strip():
        raise HTTPException(status_code=400, detail="No text extracted")

    # 4️⃣ Run RAG pipeline
    ai_result = rag_pipeline(text)

    # 5️⃣ Store AI results in MongoDB
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

    return JSONResponse(content=ai_result)

# ------------------- GET STORED RESULTS ------------------- #

@app.get("/results/{file_id}")
def get_results(file_id: str):
    item = results_collection.find_one(
        {"file_id": file_id},
        {"_id": 0}
    )

    if not item:
        raise HTTPException(status_code=404, detail="No AI result found")

    return item

# =================== NEW ENDPOINTS YOU ASKED FOR =================== #

# ------------------- EXTRACT TEXT + CHUNKS ------------------- #

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

    return {
        "file_id": req.file_id,
        "text_length": len(text),
        "total_chunks": len(chunks),
        "chunks": chunks,
    }

# ------------------- SUMMARY ONLY ------------------- #

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

    return {
        "file_id": req.file_id,
        "summary": result["summary"],
    }

# ------------------- ANALYZE ONLY ------------------- #

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

    return {
        "file_id": req.file_id,
        "insights": result["insights"],
        "topics": result["topics"],
        "sentiment": result["sentiment"],
    }

