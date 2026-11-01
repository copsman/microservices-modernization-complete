import os, json, time, uuid, smtplib, re
from email.message import EmailMessage
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
import httpx, pika, stripe, uvicorn
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from common import engine, sql, http, app, start, rabbit

class Checkout(BaseModel):
    sku:str='A1'
    qty:int=Field(default=2,gt=0)
    email:str
    order_id:str|None=None

@app.post('/checkout')
def gateway_checkout(body:Checkout,idempotency_key:str=Header(...)):
    return http('POST','http://order:8000/checkout',json=body.model_dump(),headers={'Idempotency-Key':idempotency_key})

@app.post('/orders/{order_id}/reconcile')
def gateway_reconcile(order_id:str):return http('POST',f'http://order:8000/orders/{order_id}/reconcile')

@app.get('/orders/{order_id}')
def gateway_order(order_id:str):return http('GET',f'http://order:8000/orders/{order_id}')

@app.get('/stock/{sku}')
def gateway_stock(sku:str):return http('GET',f'http://inventory:8000/stock/{sku}')

@app.get("/legacy/stock/{sku}")
def legacy_stock(sku:str):return http("GET",f"http://legacy-monolith:8000/legacy/stock/{sku}")

READS={
    "order":"http://order:8000/snapshot",
    "inventory":"http://inventory:8000/snapshot",
    "payment":"http://payment:8000/snapshot",
    "notification":"http://notification:8000/snapshot",
    "legacy":"http://legacy-monolith:8000/snapshot",
}
METRICS={
    "gateway":None,
    "order":"http://order:8000/metrics",
    "inventory":"http://inventory:8000/metrics",
    "payment":"http://payment:8000/metrics",
    "notification":"http://notification:8000/metrics",
    "legacy":"http://legacy-monolith:8000/metrics",
}
RESETS={
    "order":"http://order:8000/reset-lab",
    "inventory":"http://inventory:8000/reset-lab",
    "payment":"http://payment:8000/reset-lab",
    "notification":"http://notification:8000/reset-lab",
}
IGNORE_PATHS={"/health","/metrics","/snapshot","/reset-lab","/","/api/overview","/api/reset-lab","/docs","/redoc","/openapi.json","/docs/oauth2-redirect"}

def fetch_json(method,url):
    try:
        with httpx.Client(timeout=2.0) as client:
            response=client.request(method,url)
            body=response.json() if response.content else None
            return response.status_code,body
    except Exception as exc:
        return 0,{"detail":str(exc)}

def fetch_text(url):
    try:
        with httpx.Client(timeout=2.0) as client:
            response=client.get(url)
            return response.status_code,response.text
    except Exception as exc:
        return 0,str(exc)

def summarize_metrics(body):
    requests=0.0; seconds=0.0; observations=0.0
    for line in body.splitlines():
        if not line or line.startswith("#"):continue
        path=re.search(r'path="([^"]*)"',line)
        if path and path.group(1) in IGNORE_PATHS:continue
        try:value=float(line.rsplit(" ",1)[-1])
        except ValueError:continue
        if line.startswith("lab_requests_total"):requests+=value
        elif line.startswith("lab_http_seconds_sum"):seconds+=value
        elif line.startswith("lab_http_seconds_count"):observations+=value
    average=(seconds/observations*1000) if observations else None
    return {"requests":int(requests),"avg_ms":round(average,1) if average is not None else None,"scraped":True}

def rabbit_quick():
    params=pika.URLParameters(os.getenv("AMQP_URL","amqp://guest:guest@rabbitmq:5672/%2F"))
    params.socket_timeout=2; params.blocked_connection_timeout=2; params.connection_attempts=1; params.retry_delay=0
    return pika.BlockingConnection(params)

def queue_stats():
    try:conn=rabbit_quick()
    except Exception as exc:return {"connected":False,"exists":False,"messages":0,"consumers":0,"detail":str(exc)}
    try:
        channel=conn.channel()
        declared=channel.queue_declare(queue="order_confirmed",passive=True)
        return {"connected":True,"exists":True,"messages":declared.method.message_count,"consumers":declared.method.consumer_count}
    except Exception:
        return {"connected":True,"exists":False,"messages":0,"consumers":0}
    finally:
        try:conn.close()
        except Exception:pass

def purge_queue():
    try:conn=rabbit_quick()
    except Exception as exc:return {"purged":False,"detail":str(exc)}
    try:
        channel=conn.channel(); channel.queue_purge(queue="order_confirmed")
        return {"purged":True}
    except Exception:
        return {"purged":False,"detail":"queue not declared"}
    finally:
        try:conn.close()
        except Exception:pass

def providers():
    smtp=all(os.getenv(name) for name in ("SMTP_HOST","SMTP_USER","SMTP_PASSWORD","SMTP_FROM"))
    return {"stripe":bool(os.getenv("STRIPE_SECRET_KEY")) or os.getenv("PAYMENT_MODE")=="mock","smtp":bool(smtp) or os.getenv("EMAIL_MODE")=="mock"}

@app.get("/")
def dashboard():
    page=Path(__file__).resolve().parent/"static"/"index.html"
    if not page.is_file():raise HTTPException(500,"Classroom dashboard file is missing from the gateway image")
    return FileResponse(page,media_type="text/html",headers={"Cache-Control":"no-store"})

@app.get("/api/overview")
def overview():
    # Classroom read model. Order, inventory, payment, and notification still own their writes.
    work={}
    with ThreadPoolExecutor(max_workers=12) as pool:
        for name,url in READS.items():work[("read",name)]=pool.submit(fetch_json,"GET",url)
        for name,url in METRICS.items():
            if url:work[("metrics",name)]=pool.submit(fetch_text,url)
        work[("queue","rabbit")]=pool.submit(queue_stats)
        done={key:future.result() for key,future in work.items()}
    services=[]; snapshots={}
    for name in READS:
        code,body=done[("read",name)]
        healthy=code==200 and isinstance(body,dict)
        services.append({"name":name,"healthy":healthy,"status":code})
        snapshots[name]=body if healthy else {}
    queue=done[("queue","rabbit")]
    services.append({"name":"rabbitmq","healthy":bool(queue.get("connected")),"status":200 if queue.get("connected") else 0})
    telemetry=[{"service":"gateway",**summarize_metrics(generate_latest().decode())}]
    for name,url in METRICS.items():
        if not url:continue
        code,body=done[("metrics",name)]
        telemetry.append({"service":name,**summarize_metrics(body)} if code==200 else {"service":name,"requests":None,"avg_ms":None,"scraped":False})
    inventory=snapshots.get("inventory") or {}
    order=snapshots.get("order") or {}
    return {
        "providers":providers(),
        "services":services,
        "stock":inventory.get("stock",[]),
        "reservations":inventory.get("reservations",[]),
        "orders":order.get("orders",[]),
        "outbox":order.get("outbox",[]),
        "charges":(snapshots.get("payment") or {}).get("charges",[]),
        "deliveries":(snapshots.get("notification") or {}).get("deliveries",[]),
        "legacy":(snapshots.get("legacy") or {}).get("stock",[]),
        "queue":queue,
        "telemetry":telemetry,
    }

@app.post("/api/reset-lab")
def reset_lab():
    results={}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures={name:pool.submit(fetch_json,"POST",url) for name,url in RESETS.items()}
        for name,future in futures.items():
            code,body=future.result(); results[name]={"status":code,"body":body}
    purge_queue(); time.sleep(1); results["queue"]=purge_queue()
    results["ok"]=all(item["status"]==200 for item in results.values() if isinstance(item,dict) and "status" in item)
    return results

if __name__=="__main__":
    start()

