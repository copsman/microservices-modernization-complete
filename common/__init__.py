import os, time
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import create_engine, text
import httpx, pika, uvicorn
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
ROLE=os.getenv("SERVICE_NAME", "service")
DB=os.getenv("DATABASE_URL")
AMQP=os.getenv("AMQP_URL", "amqp://guest:guest@rabbitmq:5672/%2F")
engine=create_engine(DB,pool_pre_ping=True) if DB else None
app=FastAPI(title=ROLE)
REQUESTS=Counter("lab_requests_total","Real HTTP requests",["role","path","status"])
LATENCY=Histogram("lab_http_seconds","Measured request latency",["role","path"])
@app.middleware("http")
async def monitor(request:Request,call_next):
    t=time.perf_counter(); response=await call_next(request)
    path=request.scope.get("route"); path=getattr(path,"path",request.url.path)
    REQUESTS.labels(ROLE,path,str(response.status_code)).inc()
    LATENCY.labels(ROLE,path).observe(time.perf_counter()-t)
    return response
@app.get("/health")
def health():return {"service":ROLE,"healthy":True}
@app.get("/metrics")
def metrics():return Response(generate_latest(),media_type=CONTENT_TYPE_LATEST)
def sql(q,**params):
    with engine.begin() as c:return c.execute(text(q),params)
def http(method,url,**kw):
    try:
        with httpx.Client(timeout=20) as client:
            r=client.request(method,url,**kw);r.raise_for_status();return r.json()
    except httpx.HTTPStatusError as e:
        detail=e.response.text[:250]
        try:
            body=e.response.json()
            if isinstance(body,dict) and "detail" in body:detail=body["detail"]
        except Exception:pass
        raise HTTPException(e.response.status_code,detail)
    except httpx.HTTPError as e:raise HTTPException(503,f"Downstream unavailable: {e}")
def rabbit():return pika.BlockingConnection(pika.URLParameters(AMQP))
def start():uvicorn.run(app,host="0.0.0.0",port=8000)
