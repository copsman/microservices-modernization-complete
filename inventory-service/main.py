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

class Reservation(BaseModel):
    order_id:str
    sku:str
    qty:int=Field(gt=0)

@app.get('/stock/{sku}')
def get_stock(sku:str):
    with engine.connect() as c:
        n=c.execute(text('SELECT quantity FROM inventory.stock WHERE sku=:sku'),{'sku':sku}).scalar_one_or_none()
    if n is None:raise HTTPException(404,'Unknown SKU')
    return {'sku':sku,'available':n}

@app.post('/reserve')
def reserve(b:Reservation):
    with engine.begin() as c:
        existing=c.execute(text('SELECT sku,qty,state FROM inventory.reservations WHERE order_id=:oid FOR UPDATE'),{'oid':b.order_id}).mappings().first()
        if existing:
            if existing['sku']!=b.sku or existing['qty']!=b.qty:raise HTTPException(409,'Reservation key reused with different payload')
            if existing['state']=='reserved':return {'reserved':True,'replayed':True}
            raise HTTPException(409,'Reservation previously released')
        updated=c.execute(text('UPDATE inventory.stock SET quantity=quantity-:qty WHERE sku=:sku AND quantity>=:qty RETURNING quantity'),{'sku':b.sku,'qty':b.qty}).scalar_one_or_none()
        if updated is None:raise HTTPException(409,'Insufficient stock or unknown SKU')
        c.execute(text("INSERT INTO inventory.reservations VALUES (:oid,:sku,:qty,'reserved')"),{'oid':b.order_id,'sku':b.sku,'qty':b.qty})
    return {'reserved':True,'remaining':updated}

@app.post('/release/{order_id}')
def release(order_id:str):
    with engine.begin() as c:
        r=c.execute(text('SELECT sku,qty,state FROM inventory.reservations WHERE order_id=:oid FOR UPDATE'),{'oid':order_id}).mappings().first()
        if not r:return {'released':False,'reason':'no reservation'}
        if r['state']=='released':return {'released':True,'replayed':True}
        c.execute(text("UPDATE inventory.reservations SET state='released' WHERE order_id=:oid"),{'oid':order_id})
        c.execute(text('UPDATE inventory.stock SET quantity=quantity+:qty WHERE sku=:sku'),{'sku':r['sku'],'qty':r['qty']})
    return {'released':True}

@app.get('/snapshot')
def snapshot():
    with engine.connect() as c:
        stock=c.execute(text('SELECT sku,quantity FROM inventory.stock ORDER BY sku')).mappings().all()
        held=c.execute(text('SELECT order_id,sku,qty,state FROM inventory.reservations ORDER BY order_id')).mappings().all()
    return {'stock':[{'sku':r['sku'],'available':r['quantity']} for r in stock],'reservations':[dict(r) for r in held]}

@app.post('/reset-lab')
def reset_lab():
    with engine.begin() as c:
        c.execute(text('DELETE FROM inventory.reservations'))
        c.execute(text("INSERT INTO inventory.stock(sku,quantity) VALUES ('A1',5) ON CONFLICT(sku) DO UPDATE SET quantity=5"))
    return {'reset':True}

def seed():
    sql("INSERT INTO inventory.stock(sku,quantity) VALUES ('A1',5) ON CONFLICT(sku) DO NOTHING")

if __name__=="__main__":
    seed()
    start()
