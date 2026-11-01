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

def send_email(event):
    if os.getenv('EMAIL_MODE','smtp')=='mock':
        # Local-only simulation: log the email instead of sending it.
        print(f"[MOCK EMAIL] To: {event['email']} | Subject: Order confirmed {event['order_id']} | Body: Your order {event['order_id']} is confirmed.",flush=True)
        return
    required=['SMTP_HOST','SMTP_USER','SMTP_PASSWORD','SMTP_FROM']
    missing=[k for k in required if not os.getenv(k)]
    if missing:raise RuntimeError('SMTP missing: '+','.join(missing))
    msg=EmailMessage();msg['Subject']='Order confirmed '+event['order_id']
    msg['From']=os.environ['SMTP_FROM'];msg['To']=event['email']
    msg['Message-ID']=f"<{event['event_id']}@lab.local>"
    msg.set_content('Your order '+event['order_id']+' is confirmed.')
    with smtplib.SMTP(os.environ['SMTP_HOST'],int(os.getenv('SMTP_PORT','587')),timeout=20) as s:
        s.starttls();s.login(os.environ['SMTP_USER'],os.environ['SMTP_PASSWORD']);s.send_message(msg)

def consume_worker():
    while True:
        try:
            conn=rabbit();ch=conn.channel();ch.queue_declare(queue='order_confirmed',durable=True);ch.basic_qos(prefetch_count=1)
            def handler(ch,method,props,body):
                event=json.loads(body);eid=event['event_id']
                with engine.connect() as c:
                    done=c.execute(text('SELECT 1 FROM notifications.delivered WHERE event_id=:id'),{'id':eid}).first()
                if done:ch.basic_ack(method.delivery_tag);return
                try:
                    send_email(event)
                    sql('INSERT INTO notifications.delivered(event_id) VALUES (:id) ON CONFLICT DO NOTHING',id=eid)
                    ch.basic_ack(method.delivery_tag)
                except Exception as e:
                    print('Email delivery failed, retry later:',repr(e),flush=True)
                    ch.basic_nack(method.delivery_tag,requeue=True)
                    time.sleep(5)
            ch.basic_consume(queue='order_confirmed',on_message_callback=handler)
            ch.start_consuming()
        except Exception as e:print('consumer reconnect:',repr(e),flush=True);time.sleep(5)

if __name__=="__main__":
    consume_worker()
