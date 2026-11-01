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

class Charge(BaseModel):
    order_id:str
    amount_cents:int=Field(gt=0)
    currency:str='usd'

@app.post('/charge')
def charge(b:Charge):
    key=os.getenv('STRIPE_SECRET_KEY','')
    if not key:raise HTTPException(503,'STRIPE_SECRET_KEY not configured; no payment attempted')
    with engine.connect() as c:
        prev=c.execute(text('SELECT stripe_id,status FROM payments.charges WHERE order_id=:id'),{'id':b.order_id}).mappings().first()
    if prev:return {'provider_id':prev['stripe_id'],'status':prev['status'],'replayed':True}
    stripe.api_key=key
    try:
        # Real Stripe API request. PaymentIntent requires customer confirmation for many payment methods.
        intent=stripe.PaymentIntent.create(amount=b.amount_cents,currency=b.currency,automatic_payment_methods={'enabled':True},metadata={'order_id':b.order_id},idempotency_key='lab-charge-'+b.order_id)
    except stripe.error.StripeError as e:
        raise HTTPException(502,f'Stripe API error: {str(e)}')
    with engine.begin() as c:
        c.execute(text('INSERT INTO payments.charges(order_id,stripe_id,status) VALUES (:id,:sid,:status) ON CONFLICT(order_id) DO NOTHING'),{'id':b.order_id,'sid':intent.id,'status':intent.status})
    return {'provider_id':intent.id,'status':intent.status,'client_secret':intent.client_secret}

@app.get('/snapshot')
def snapshot():
    with engine.connect() as c:
        rows=c.execute(text('SELECT order_id,stripe_id,status FROM payments.charges ORDER BY order_id')).mappings().all()
    return {'charges':[dict(r) for r in rows]}

@app.post('/reset-lab')
def reset_lab():
    sql('DELETE FROM payments.charges')
    return {'reset':True}

@app.get('/status/{order_id}')
def payment_status(order_id:str):
    key=os.getenv('STRIPE_SECRET_KEY','')
    if not key:raise HTTPException(503,'Stripe not configured')
    with engine.connect() as c:
        sid=c.execute(text('SELECT stripe_id FROM payments.charges WHERE order_id=:id'),{'id':order_id}).scalar_one_or_none()
    if not sid:raise HTTPException(404,'No payment intent')
    stripe.api_key=key
    try:intent=stripe.PaymentIntent.retrieve(sid)
    except stripe.error.StripeError as e:raise HTTPException(502,str(e))
    return {'status':intent.status,'provider_id':sid}

if __name__=="__main__":
    start()
