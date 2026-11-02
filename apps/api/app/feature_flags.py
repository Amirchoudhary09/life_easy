from fastapi import HTTPException
async def feature_enabled(db,key:str,default:bool=True)->bool:
    value=await db.fetchval("SELECT enabled FROM feature_flags WHERE flag_key=$1",key)
    return default if value is None else bool(value)
async def require_feature(db,key:str):
    if not await feature_enabled(db,key,True):
        raise HTTPException(status_code=503,detail=f"The {key.replace('_',' ')} feature is temporarily disabled")
