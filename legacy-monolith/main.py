import os
from fastapi import HTTPException
from sqlalchemy import text
from common import app, engine, start
@app.get("/snapshot")
def snapshot():
    with engine.connect() as c:
        rows=c.execute(text("SELECT sku,quantity FROM legacy.stock ORDER BY sku")).mappings().all()
    return {"stock":[{"sku":r["sku"],"available":r["quantity"],"source":"legacy-monolith"} for r in rows]}

@app.get("/legacy/stock/{sku}")
def stock(sku:str):
    with engine.connect() as c:
        n=c.execute(text("SELECT quantity FROM legacy.stock WHERE sku=:sku"),{"sku":sku}).scalar_one_or_none()
    if n is None:raise HTTPException(404,"Unknown product")
    return {"sku":sku,"available":n,"source":"legacy-monolith"}
@app.post("/legacy/reserve/{sku}/{qty}")
def reserve(sku:str,qty:int):
    if os.getenv("LEGACY_WRITES_ENABLED","false").lower()!="true":raise HTTPException(403,"Strangler migration: legacy writes disabled")
    if qty<=0:raise HTTPException(422,"qty must be positive")
    with engine.begin() as c:
        n=c.execute(text("UPDATE legacy.stock SET quantity=quantity-:qty WHERE sku=:sku AND quantity>=:qty RETURNING quantity"),{"sku":sku,"qty":qty}).scalar_one_or_none()
    if n is None:raise HTTPException(409,"Insufficient stock")
    return {"available":n}
if __name__=="__main__":start()
