# ADR-001 — E-commerce checkout modernization

## Context
Checkout spans order state, inventory, payment, and notification. A retry or timeout must not result in duplicate charges. Services must own their writes and publish confirmed-order events reliably.

## Decision
Use HTTP orchestration, PostgreSQL transactions for local consistency, a unique idempotency key, a Stripe idempotency key, a transactional outbox, and durable RabbitMQ messages. Inventory updates are conditional database operations, preventing negative stock. Payment outcomes are reconciled against the provider before confirming or compensating an order.

## Rejected
A shared distributed transaction across payment provider and database, assuming timeouts imply payment failure, and publishing events directly without an outbox.

## Tradeoffs
The design is eventually consistent and requires recovery workers, webhook processing, observability, and authorization hardening before production use. RabbitMQ plus SMTP provides at-least-once delivery, not exactly-once external email delivery.
