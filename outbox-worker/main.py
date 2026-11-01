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

def publish_worker():
    while True:
        try:
            with engine.connect() as c:
                rows=c.execute(text('SELECT event_id,payload FROM orders.outbox WHERE NOT published ORDER BY event_id LIMIT 50')).mappings().all()
            if rows:
                conn=rabbit();ch=conn.channel();ch.queue_declare(queue='order_confirmed',durable=True)
                ch.confirm_delivery()
                for r in rows:
                    ch.basic_publish(exchange='',routing_key='order_confirmed',body=json.dumps(r['payload']).encode(),properties=pika.BasicProperties(delivery_mode=2,message_id=r['event_id']),mandatory=True)
                    sql('UPDATE orders.outbox SET published=true WHERE event_id=:id',id=r['event_id'])
                conn.close()
        except Exception as e:print('outbox retry:',repr(e),flush=True)
        time.sleep(2)

if __name__=="__main__":
    publish_worker()
