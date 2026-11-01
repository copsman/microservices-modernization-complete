# Microservices modernization — separate runnable services

**Eight independently built Python applications**: API gateway, order, inventory, payment, notification, outbox publisher, event consumer, and legacy monolith. PostgreSQL, RabbitMQ and Prometheus are additional infrastructure containers. This is a **development lab, not a production-ready payment platform**.

## Start

1. Install Docker Engine / Docker Desktop with Compose v2.
2. `cp .env.example .env` and set `POSTGRES_PASSWORD` to a strong password.
3. Configure Stripe credentials and SMTP credentials in `.env`. No fake approvals or fake emails are provided.
4. `docker compose up --build -d` then `docker compose ps`.
5. Open http://localhost:8000/ and teach from the Lesson tab. The beginner script is `docs/teaching-notes.md`. API docs remain at http://localhost:8000/docs, and `curl http://localhost:8000/health` checks the gateway.

**Checkout** (real Stripe PaymentIntent, but a PaymentIntent alone is NOT a charge):

```bash
curl -X POST http://localhost:8000/checkout -H 'Content-Type: application/json' -H 'Idempotency-Key: 6f8d' -d '{"order_id":"o-104","sku":"A1","qty":2,"email":"your-real-address@example.com"}'
```

The response returns an awaiting-payment state and client secret. **Use Stripe's official client SDK** to confirm the payment. Do not paste card numbers into this application. After the provider reports success, reconcile:

```bash
curl -X POST http://localhost:8000/orders/o-104/reconcile
curl http://localhost:8000/orders/o-104
curl http://localhost:8000/stock/A1
```

Stripe **test** mode makes genuine provider API calls but does not move real money. Live-mode charges require proper compliance and a real payment method. The lab does not pretend either mode completed payment.

## Source map

| Original exercise | Actual component |
|---|---|
| 1. Separate ownership | `order-service`, `inventory-service`, PostgreSQL tables |
| 2. Idempotency | `order-service` idempotency key and Stripe provider key |
| 3. 365ms budget | Actual request histograms at `/metrics`, Prometheus |
| 4. Saga and compensation | `order-service` reconcile + `inventory-service` release |
| 5. Transactional outbox | `order-service` transaction + `outbox-worker` |
| 6. Event handling | RabbitMQ + `event-consumer` + SMTP |
| 7. Strangler migration | `legacy-monolith` read route, disabled legacy writes, gateway routes |
| 8. ADR | `docs/ADR.md` |

## Explicit limitations and honesty about guarantees

- This package has been **syntax checked**, not run end-to-end with Docker, Stripe, and SMTP in this environment.
- Each service is in a separate directory and container build, but `common/` is shared infrastructure and the services currently use a **shared PostgreSQL login**. Schema ownership is a convention, not enforced least privilege.
- A live legacy system is not migrated in-place; the `legacy-monolith` is a real runnable example process with its own table. It does not share production data with the new inventory service. No dual-write migration is claimed.
- An awaiting-payment order requires the real Stripe client confirmation and explicit reconciliation. Automated crash recovery and webhook handling are not complete.
- An SMTP send may succeed just before the worker crashes, so duplicate emails remain possible. A message ID alone is not an exactly-once guarantee.
- Never expose development management interfaces publicly. Do not put live credentials in source control.
- All HTTP requests and database writes are real operations when the stack is running. Unconfigured external services fail rather than returning fake successes.
- The page at `/` is a classroom view. The gateway reads the other services to draw it and does not own their tables. Reset clears lab orders, reservations, payments, notifications, and the `order_confirmed` queue, then sets A1 stock back to 5.

## Useful commands

```bash
docker compose logs -f order inventory payment
docker compose ps
docker compose exec postgres psql -U lab -d lab -c 'select * from orders.orders;'
docker compose exec postgres psql -U lab -d lab -c 'select * from orders.outbox;'
docker compose down # keeps persisted data
docker compose down -v # deletes lab data; destructive
```

RabbitMQ management: http://localhost:15672 (guest/guest). Prometheus: http://localhost:9090.
