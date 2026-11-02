from fastapi import APIRouter,Depends
import asyncpg
from app.auth import current_user
from app.db import get_db
from app.feature_flags import feature_enabled
router=APIRouter(prefix="/api/v1/features",tags=["Features"])
KNOWN=["job_search","ai_assistant","resume_processing","gmail_integration","whatsapp_assistant","external_delivery"]
@router.get("")
async def list_features(user=Depends(current_user),db:asyncpg.Pool=Depends(get_db)):
    return {"features":{key:await feature_enabled(db,key,True) for key in KNOWN}}
