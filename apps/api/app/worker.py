from __future__ import annotations
import asyncio,os
import asyncpg
from app.action_worker import process_one,init_connection
from app.ingestion import ingest_configured_boards
async def run():
    dsn=os.getenv("DATABASE_URL","")
    if not dsn: raise RuntimeError("DATABASE_URL is required")
    pool=await asyncpg.create_pool(dsn,min_size=1,max_size=5,init=init_connection)
    interval=max(3600,int(os.getenv("JOB_INGESTION_INTERVAL_SECONDS","21600"))); next_ingest=0; next_recovery=0
    loop=asyncio.get_running_loop()
    try:
        while True:
            if loop.time()>=next_recovery:
                await pool.execute("UPDATE external_action_jobs SET status='uncertain',last_error='Worker stopped while sending; check provider Sent/Message history before retrying',updated_at=now() WHERE status='processing' AND updated_at<now()-interval '5 minutes'")
                next_recovery=loop.time()+60
            if loop.time()>=next_ingest:
                try: print({"job_ingestion":await ingest_configured_boards(pool)})
                except Exception as exc: print({"job_ingestion_error":str(exc)[:300]})
                next_ingest=loop.time()+interval
            if not await process_one(pool): await asyncio.sleep(3)
    finally: await pool.close()
if __name__=="__main__": asyncio.run(run())
