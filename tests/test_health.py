"""Basic health endpoint tests."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from main import app


def test_health_endpoint():
    client = app.test_client()
    response = client.get('/health')
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'ok'
    assert 'timestamp' in data


def test_index_endpoint():
    client = app.test_client()
    response = client.get('/')
    assert response.status_code == 200
    data = response.get_json()
    assert data['service'] == 'leka-product-catalogs'
    assert 'brands' in data
