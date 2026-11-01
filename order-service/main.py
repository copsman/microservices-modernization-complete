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

class Checkout(BaseModel):
    sku:str='A1'
    qty:int=Field(default=2,gt=0)
    email:str
    order_id:str|None=None

def confirm_order(oid,email):
    event={"event_id":str(uuid.uuid4()),"type":"OrderConfirmed","order_id":oid,"email":email}
    with engine.begin() as c:
        updated=c.execute(text("UPDATE orders.orders SET status='CONFIRMED',error=NULL WHERE id=:id AND status <> 'CONFIRMED' RETURNING id"),{"id":oid}).scalar_one_or_none()
        if updated:c.execute(text("INSERT INTO orders.outbox(event_id,payload) VALUES (:id,CAST(:payload AS jsonb))"),{"id":event["event_id"],"payload":json.dumps(event)})

@app.post('/checkout')
def checkout(b:Checkout,idempotency_key:str=Header(...)):
    oid=b.order_id or str(uuid.uuid4())
    with engine.begin() as c:
        existing=c.execute(text('SELECT * FROM orders.orders WHERE idem_key=:key FOR UPDATE'),{'key':idempotency_key}).mappings().first()
        if existing:
            if (existing['sku'],existing['qty'],existing['email'])!=(b.sku,b.qty,b.email):raise HTTPException(409,'Idempotency key payload mismatch')
            return {'order_id':existing['id'],'status':existing['status'],'replayed':True,'error':existing['error']}
        try:
            c.execute(text("INSERT INTO orders.orders(id,idem_key,sku,qty,email,status) VALUES (:id,:key,:sku,:qty,:email,'PENDING')"),{'id':oid,'key':idempotency_key,'sku':b.sku,'qty':b.qty,'email':b.email})
        except IntegrityError:raise HTTPException(409,'Order ID conflict')
    # Synchronous orchestration for lab clarity. Recovery requires a reconciliation worker.
    try:
        http('POST','http://inventory:8000/reserve',json={'order_id':oid,'sku':b.sku,'qty':b.qty})
    except HTTPException as e:
        sql("UPDATE orders.orders SET status='REJECTED',error=:err WHERE id=:id",err=str(e.detail),id=oid)
        return {'order_id':oid,'status':'REJECTED','reason':str(e.detail)}
    try:
        pay=http('POST','http://payment:8000/charge',json={'order_id':oid,'amount_cents':b.qty*1000})
    except HTTPException as e:
        # Do NOT release on ambiguous provider outcome; retain reservation pending reconciliation.
        sql("UPDATE orders.orders SET status='PAYMENT_UNKNOWN',error=:err WHERE id=:id",err=str(e.detail),id=oid)
        return {'order_id':oid,'status':'PAYMENT_UNKNOWN','reason':str(e.detail)}
    status=pay['status']
    if status=='succeeded':
        confirm_order(oid,b.email)
        return {'order_id':oid,'status':'CONFIRMED'}
    sql("UPDATE orders.orders SET status='AWAITING_PAYMENT',error=NULL WHERE id=:id",id=oid)
    return {'order_id':oid,'status':'AWAITING_PAYMENT','payment_intent':pay['provider_id'],'client_secret':pay.get('client_secret'),'note':'Confirm PaymentIntent using Stripe client SDK, then POST /orders/{id}/reconcile'}

@app.post('/orders/{oid}/reconcile')
def reconcile(oid:str):
    with engine.connect() as c:
        order=c.execute(text('SELECT * FROM orders.orders WHERE id=:id'),{'id':oid}).mappings().first()
    if not order:raise HTTPException(404,'Order not found')
    if order['status'] in ('CONFIRMED','CANCELLED','REJECTED'):return {'status':order['status']}
    try:payment=http('GET',f'http://payment:8000/status/{oid}')
    except HTTPException as e:raise HTTPException(503,'Payment outcome cannot be verified; reservation retained')
    if payment['status']=='succeeded':
        confirm_order(oid,order['email'])
        return {'status':'CONFIRMED'}
    if payment['status'] in ('canceled','requires_payment_method'):
        http('POST',f'http://inventory:8000/release/{oid}')
        sql("UPDATE orders.orders SET status='CANCELLED' WHERE id=:id",id=oid)
        return {'status':'CANCELLED'}
    return {'status':'AWAITING_PAYMENT','stripe_status':payment['status']}

@app.get('/snapshot')
def snapshot():
    with engine.connect() as c:
        orders=c.execute(text('SELECT id,idem_key,sku,qty,email,status,error FROM orders.orders ORDER BY id')).mappings().all()
        outbox=c.execute(text('SELECT event_id,payload,published FROM orders.outbox ORDER BY event_id')).mappings().all()
    events=[]
    for r in outbox:
        payload=r['payload']
        if isinstance(payload,str):payload=json.loads(payload)
        events.append({'event_id':r['event_id'],'payload':payload,'published':bool(r['published'])})
    return {'orders':[dict(r) for r in orders],'outbox':events}

@app.post('/reset-lab')
def reset_lab():
    with engine.begin() as c:
        c.execute(text('DELETE FROM orders.outbox'))
        c.execute(text('DELETE FROM orders.orders'))
    return {'reset':True}

@app.get('/orders/{oid}')
def get_order(oid:str):
    with engine.connect() as c:
        r=c.execute(text('SELECT id,sku,qty,email,status,error FROM orders.orders WHERE id=:id'),{'id':oid}).mappings().first()
    if not r:raise HTTPException(404,'Unknown order')
    return dict(r)

if __name__=="__main__":
    start()
