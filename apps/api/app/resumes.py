from __future__ import annotations
import io,json,os,re,zipfile
from uuid import uuid4
import asyncpg,boto3
from botocore.exceptions import BotoCoreError,ClientError
from docx import Document
from fastapi import APIRouter,Depends,File,HTTPException,UploadFile
from pypdf import PdfReader
from pydantic import BaseModel,Field
from app.auth import current_user
from app.db import get_db
router=APIRouter(prefix="/api/v1/resumes",tags=["Resumes"])
MAX_BYTES=8*1024*1024
SKILLS={"python","java","c++","c","javascript","typescript","react","next.js","node.js","fastapi","django","flask","sql","postgresql","mysql","mongodb","redis","docker","kubernetes","aws","azure","gcp","git","linux","machine learning","deep learning","langchain","llm","rag","vector database","pytorch","tensorflow","html","css","kotlin","android","rest api","microservices","system design","data structures","algorithms"}
class AnalyzeBody(BaseModel):
    job_description:str=Field(default="",max_length=30000)
def storage():
    bucket=os.getenv("RESUME_BUCKET",""); access=os.getenv("S3_ACCESS_KEY_ID",""); secret=os.getenv("S3_SECRET_ACCESS_KEY","")
    if not all((bucket,access,secret)): raise HTTPException(status_code=503,detail="Private resume storage is not configured yet")
    return boto3.client("s3",endpoint_url=os.getenv("S3_ENDPOINT_URL") or None,region_name=os.getenv("S3_REGION","auto"),aws_access_key_id=access,aws_secret_access_key=secret),bucket
def extract(filename,raw):
    try:
        if filename.lower().endswith(".pdf"):
            reader=PdfReader(io.BytesIO(raw))
            if len(reader.pages)>60:
                raise HTTPException(status_code=413,detail="Resume PDF must contain 60 pages or fewer")
            text="\\n".join(page.extract_text() or "" for page in reader.pages)
        elif filename.lower().endswith(".docx"):
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                expanded=sum(item.file_size for item in archive.infolist())
                if expanded>30*1024*1024:
                    raise HTTPException(status_code=413,detail="DOCX expands beyond the allowed size")
            document=Document(io.BytesIO(raw))
            text="\\n".join(paragraph.text for paragraph in document.paragraphs)
            for table in document.tables:
                text+="\\n"+"\\n".join(" | ".join(cell.text for cell in row.cells) for row in table.rows)
        else:
            raise HTTPException(status_code=415,detail="Upload a PDF or DOCX resume")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422,detail="Resume file could not be parsed") from exc
    text=re.sub(r"[ \\t]+"," ",text)
    text=re.sub(r"\\n{3,}","\\n\\n",text).strip()
    if len(text)<80:
        raise HTTPException(status_code=422,detail="Could not extract enough text. Upload a text-based PDF or DOCX.")
    return text[:100000]
def detect_skills(text):
    lower=text.lower()
    return sorted(s for s in SKILLS if re.search(r"(?<![a-z0-9+#.])"+re.escape(s)+r"(?![a-z0-9+#.])",lower))
@router.post("",status_code=201)
async def upload(file:UploadFile=File(...),user=Depends(current_user),db:asyncpg.Pool=Depends(get_db)):
    filename=(file.filename or "resume").replace("\\","/").split("/")[-1][:180]
    if not filename.lower().endswith((".pdf",".docx")): raise HTTPException(status_code=415,detail="Only PDF and DOCX resumes are accepted")
    raw=await file.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES: raise HTTPException(status_code=413,detail="Resume must be 8 MB or smaller")
    if filename.lower().endswith(".pdf") and not raw.startswith(b"%PDF-"): raise HTTPException(status_code=415,detail="Invalid PDF file")
    if filename.lower().endswith(".docx") and not raw.startswith(b"PK"): raise HTTPException(status_code=415,detail="Invalid DOCX file")
    text=extract(filename.lower(),raw); skills=detect_skills(text); client,bucket=storage(); key=f"users/{user['id']}/resumes/{uuid4()}/{filename}"
    content_type="application/pdf" if filename.lower().endswith(".pdf") else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    try: client.put_object(Bucket=bucket,Key=key,Body=raw,ContentType=content_type)
    except (BotoCoreError,ClientError): raise HTTPException(status_code=502,detail="Private resume storage upload failed")
    try:
        row=await db.fetchrow("INSERT INTO resume_documents(user_id,storage_key,filename,content_type,byte_size,extracted_text) VALUES($1,$2,$3,$4,$5,$6) RETURNING id,filename,content_type,byte_size,created_at",user["id"],key,filename,content_type,len(raw),text)
        await db.execute("""INSERT INTO profiles(user_id,skills) VALUES($1,$2) ON CONFLICT(user_id) DO UPDATE SET skills=(SELECT COALESCE(jsonb_agg(DISTINCT value),'[]'::jsonb) FROM jsonb_array_elements_text(profiles.skills || EXCLUDED.skills) AS value),updated_at=now()""",user["id"],skills)
    except Exception:
        client.delete_object(Bucket=bucket,Key=key); raise
    return {"resume":dict(row),"extracted":{"characters":len(text),"skills":skills},"ats":{"status":"parsed","note":"Baseline extraction and skill detection; not a vendor ATS score."}}
@router.get("")
async def list_resumes(user=Depends(current_user),db:asyncpg.Pool=Depends(get_db)):
    rows=await db.fetch("SELECT id,filename,content_type,byte_size,created_at FROM resume_documents WHERE user_id=$1 ORDER BY created_at DESC LIMIT 20",user["id"])
    return {"resumes":[dict(r) for r in rows]}
@router.post("/{resume_id}/analyze")
async def analyze(resume_id:str,body:AnalyzeBody,user=Depends(current_user),db:asyncpg.Pool=Depends(get_db)):
    row=await db.fetchrow("SELECT extracted_text,filename FROM resume_documents WHERE id=$1::uuid AND user_id=$2",resume_id,user["id"])
    if row is None: raise HTTPException(status_code=404,detail="Resume not found")
    text=row["extracted_text"]; lower=text.lower(); resume_skills=set(detect_skills(text))
    target_skills=set(detect_skills(body.job_description)) if body.job_description else set()
    matched=sorted(resume_skills & target_skills); missing=sorted(target_skills-resume_skills)
    sections={"experience":any(x in lower for x in ("experience","employment","work history")),"education":"education" in lower,"skills":"skills" in lower,"projects":"projects" in lower}
    section_score=round(sum(sections.values())/len(sections)*25)
    keyword_score=round(len(matched)/max(1,len(target_skills))*45) if target_skills else 0
    quantified=bool(re.search(r"\b\d+(?:%|\+|x| years?| users?| projects?)\b",lower))
    action_verbs=sum(1 for x in ("built","developed","designed","implemented","optimized","led","automated","delivered") if x in lower)
    impact_score=min(15,(5 if quantified else 0)+min(10,action_verbs*2))
    length_score=15 if 350<=len(text.split())<=1000 else 10 if 200<=len(text.split())<=1300 else 5
    raw_score=section_score+keyword_score+impact_score+length_score
    score=min(100,round(raw_score if target_skills else raw_score/55*100))
    return {"resume":row["filename"],"heuristic_score":score,"score_type":"heuristic_not_vendor_ats","score_context":"target-job comparison" if target_skills else "general resume quality; normalized because no job description was supplied","breakdown":{"sections":section_score,"target_keywords":keyword_score,"impact_and_metrics":impact_score,"length":length_score},"sections_found":sections,"detected_skills":sorted(resume_skills),"matched_target_skills":matched,"missing_target_skills":missing,"recommendations":[*(["Add an Experience section with role, company and dates."] if not sections["experience"] else []),*(["Add an Education section."] if not sections["education"] else []),*(["Add a clearly labeled Skills section."] if not sections["skills"] else []),*(["Add measurable outcomes (%, scale, latency, users, revenue or time saved)."] if not quantified else []),*(["Add relevant target-job keywords naturally where your experience supports them."] if missing else [])]}
@router.get("/{resume_id}/download")
async def download(resume_id:str,user=Depends(current_user),db:asyncpg.Pool=Depends(get_db)):
    row=await db.fetchrow("SELECT storage_key,filename FROM resume_documents WHERE id=$1::uuid AND user_id=$2",resume_id,user["id"])
    if row is None: raise HTTPException(status_code=404,detail="Resume not found")
    client,bucket=storage()
    try: url=client.generate_presigned_url("get_object",Params={"Bucket":bucket,"Key":row["storage_key"],"ResponseContentDisposition":f'attachment; filename="{row["filename"]}"'},ExpiresIn=300)
    except (BotoCoreError,ClientError): raise HTTPException(status_code=502,detail="Could not create private download link")
    return {"download_url":url,"expires_in":300}
