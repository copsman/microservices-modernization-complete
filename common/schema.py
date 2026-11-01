from common import engine, text
def init_db():
    # Separate PostgreSQL schemas: each service only queries its own schema.
    with engine.begin() as c:
        for q in [
            'CREATE SCHEMA IF NOT EXISTS inventory',
            'CREATE SCHEMA IF NOT EXISTS orders',
            'CREATE SCHEMA IF NOT EXISTS payments',
            'CREATE SCHEMA IF NOT EXISTS notifications',
            "CREATE TABLE IF NOT EXISTS inventory.stock(sku TEXT PRIMARY KEY, quantity INT NOT NULL CHECK(quantity>=0))",
            "CREATE TABLE IF NOT EXISTS inventory.reservations(order_id TEXT PRIMARY KEY, sku TEXT NOT NULL, qty INT NOT NULL, state TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS orders.orders(id TEXT PRIMARY KEY, idem_key TEXT UNIQUE NOT NULL, sku TEXT NOT NULL, qty INT NOT NULL, email TEXT NOT NULL, status TEXT NOT NULL, error TEXT)",
            "CREATE TABLE IF NOT EXISTS orders.outbox(event_id TEXT PRIMARY KEY, payload JSONB NOT NULL, published BOOLEAN NOT NULL DEFAULT FALSE)",
            "CREATE TABLE IF NOT EXISTS payments.charges(order_id TEXT PRIMARY KEY, stripe_id TEXT UNIQUE NOT NULL, status TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS notifications.delivered(event_id TEXT PRIMARY KEY, delivered_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        ]: c.execute(text(q))

def init_legacy():
    with engine.begin() as c:
        c.execute(text("CREATE SCHEMA IF NOT EXISTS legacy"))
        c.execute(text("CREATE TABLE IF NOT EXISTS legacy.stock(sku TEXT PRIMARY KEY,quantity INT NOT NULL CHECK(quantity>=0))"))
        c.execute(text("INSERT INTO legacy.stock VALUES ('A1',5) ON CONFLICT DO NOTHING"))
if __name__=="__main__":
    init_db();init_legacy()
