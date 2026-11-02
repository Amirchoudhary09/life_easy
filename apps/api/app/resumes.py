from __future__ import annotations
import io,os,re
from uuid import uuid4
import asyncpg,boto3
from botocore.exceptions import BotoCoreError,ClientError
from docx import Document
from fastapi import APIRouter,Depends,File,HTTPException,UploadFile
from pypdf import PdfReader
from app.auth import current_user
from app.db import get_db
router=APIRouter(prefix="/api/v1/resumes",tags=["Resumes"])
MAX_BYTES=8*1024*1024
SKILLS={"python","java","c++","c","javascript","typescript","react","next.js","node.js","fastapi","django","flask","sql","postgresql","mysql","mongodb","redis","docker","kubernetes","aws","azure","gcp","git","linux","machine learning","deep learning","langchain","llm","rag","vector database","pytorch","tensorflow","html","css","kotlin","android","rest api","microservices","system design","data structures","algorithms"}

def storage():
    bucket=os.getenv("RESUME_BUCKET",""); access=os.getenv("S3_ACCESS_KEY_ID",""); secret=os.getenv("S3_SECRET_ACCESS_KEY","")
    if not all((bucket,access,secret)): raise HTTPException(status_code=503,detail="Private resume storage is not configured yet")
    return boto3.client("s3",endpoint_url=os.getenv("S3_ENDPOINT_URL") or None,region_name=os.getenv("S3_REGION","auto"),aws_access_key_id=access,aws_secret_access_key=secret),bucket

def extract(filename,raw):
    if filename.endswith(".pdf"): text="\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(raw)).pages)
    elif filename.endswith(".docx"):
        doc=Document(io.BytesIO(raw)); text="\n".join(p.text for p in doc.paragraphs)
        for table in doc.tables: text+="\n"+"\n".join(" | ".join(c.text for c in row.cells) for row in table.rows)
    else: raise HTTPException(status_code=415,detail="Upload a PDF or DOCX resume")
    text=re.sub(r"[ \t]+"," ",text); text=re.sub(r"\n{3,}","\n\n",text).strip()
    if len(text)<80: raise HTTPException(status_code=422,detail="Could not extract enough text. Upload a text-based PDF or DOCX.")
    return text[:100000]
def detect_skills(text):
    lower=text.lower()
    return sorted(s for s in SKILLS if re.search(r"(?<![a-z0-9+#.])"+re.escape(s)+r"(?![a-z0-9+#.])",lower))

@router.post("",status_code=201)
async def upload(file:UploadFile=File(...),user=Depends(current_user),db:asyncpg.Pool=Depends(get_db)):
    filename=(file.filename or "resume").replace("\\","/").split("/")[-1][:180].lower()
    if not filename.endswith((".pdf",".docx")): raise HTTPException(status_code=415,detail="Only PDF and DOCX resumes are accepted")
    raw=await file.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES: raise HTTPException(status_code=413,detail="Resume must be 8 MB or smaller")
    if filename.endswith(".pdf") and not raw.startswith(b"%PDF-"): raise HTTPException(status_code=415,detail="Invalid PDF file")
    if filename.endswith(".docx") and not raw.startswith(b"PK"): raise HTTPException(status_code=415,detail="Invalid DOCX file")
    text=extract(filename,raw); skills=detect_skills(text); client,bucket=storage()
    key=f"users/{user['id']}/resumes/{uuid4()}/{filename}"
    content_type="application/pdf" if filename.endswith(".pdf") else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    try: client.put_object(Bucket=bucket,Key=key,Body=raw,ContentType=content_type,ServerSideEncryption="AES256")
    except (BotoCoreError,ClientError): raise HTTPException(status_code=502,detail="Private resume storage upload failed")
    try:
        row=await db.fetchrow("INSERT INTO resume_documents(user_id,storage_key,filename,content_type,byte_size,extracted_text) VALUES($1,$2,$3,$4,$5,$6) RETURNING id,filename,content_type,byte_size,created_at",user["id"],key,filename,content_type,len(raw),text)
        await db.execute("""INSERT INTO profiles(user_id,skills) VALUES($1,$2::jsonb) ON CONFLICT(user_id) DO UPDATE SET skills=(SELECT COALESCE(jsonb_agg(DISTINCT value),'[]'::jsonb) FROM jsonb_array_elements_text(profiles.skills || EXCLUDED.skills) AS value),updated_at=now()""",user["id"],__import__("json").dumps(skills))
    except Exception:
        client.delete_object(Bucket=bucket,Key=key); raise
    return {"resume":dict(row),"extracted":{"characters":len(text),"skills":skills},"ats":{"status":"parsed","note":"Baseline extraction and skill detection; not a vendor ATS score."}}

@router.get("")
async def list_resumes(user=Depends(current_user),db:asyncpg.Pool=Depends(get_db)):
    rows=await db.fetch("SELECT id,filename,content_type,byte_size,created_at FROM resume_documents WHERE user_id=$1 ORDER BY created_at DESC LIMIT 20",user["id"])
    return {"resumes":[dict(r) for r in rows]}

@router.get("/{resume_id}/download")
async def download(resume_id:str,user=Depends(current_user),db:asyncpg.Pool=Depends(get_db)):
    row=await db.fetchrow("SELECT storage_key,filename FROM resume_documents WHERE id=$1::uuid AND user_id=$2",resume_id,user["id"])
    if row is None: raise HTTPException(status_code=404,detail="Resume not found")
    client,bucket=storage()
    try: url=client.generate_presigned_url("get_object",Params={"Bucket":bucket,"Key":row["storage_key"],"ResponseContentDisposition":f'attachment; filename="{row["filename"]}"'},ExpiresIn=300)
    except (BotoCoreError,ClientError): raise HTTPException(status_code=502,detail="Could not create private download link")
    return {"download_url":url,"expires_in":300}
