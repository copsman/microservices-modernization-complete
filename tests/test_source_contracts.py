"""Static architecture checks; NOT substitutes for end-to-end integration tests."""
import ast
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def functions(folder):
    tree=ast.parse((ROOT/folder/'main.py').read_text())
    return {n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}

def test_distinct_applications():
    names=['api-gateway','order-service','inventory-service','payment-service','notification-service','outbox-worker','event-consumer','legacy-monolith']
    assert all((ROOT/n/'main.py').exists() for n in names)

def test_api_routes_registered():
    for folder in ['api-gateway','order-service','inventory-service','payment-service','notification-service']:
        assert any(n.decorator_list for n in functions(folder).values()),folder

def test_transactional_outbox_present():
    code=(ROOT/'order-service/main.py').read_text()
    assert 'orders.outbox' in code and 'with engine.begin() as c:' in code

def test_classroom_dashboard_present():
    html=(ROOT/'api-gateway'/'static'/'index.html').read_text()
    assert 'Checkout floor' in html and 'Lesson' in html and 'Step 1' in html
    gateway=(ROOT/'api-gateway'/'main.py').read_text()
    assert '/api/overview' in gateway and '/api/reset-lab' in gateway
    for folder in ['order-service','inventory-service','payment-service','notification-service','legacy-monolith']:
        assert '/snapshot' in (ROOT/folder/'main.py').read_text()

def test_real_provider_integration_present():
    assert 'stripe.PaymentIntent.create' in (ROOT/'payment-service/main.py').read_text()
    assert 'send_message(msg)' in (ROOT/'event-consumer/main.py').read_text()
