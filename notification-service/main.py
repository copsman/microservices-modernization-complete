import os, json, time, uuid, smtplib
from email.message import EmailMessage
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
import httpx, pika, stripe, uvicorn
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from common import engine, sql, http, app, start, rabbit

@app.get('/snapshot')
def snapshot():
    with engine.connect() as c:
        rows=c.execute(text('SELECT event_id,delivered_at FROM notifications.delivered ORDER BY delivered_at')).mappings().all()
    return {'deliveries':[{'event_id':r['event_id'],'delivered_at':r['delivered_at'].isoformat()} for r in rows]}

@app.post('/reset-lab')
def reset_lab():
    sql('DELETE FROM notifications.delivered')
    return {'reset':True}

@app.get('/delivered/{event_id}')
def delivered(event_id:str):
    with engine.connect() as c:
        found=c.execute(text('SELECT 1 FROM notifications.delivered WHERE event_id=:id'),{'id':event_id}).first()
    return {'delivered':bool(found)}

if __name__=="__main__":
    start()
