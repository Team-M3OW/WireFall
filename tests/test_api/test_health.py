def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "redis_connected" in data
    assert "mongodb_connected" in data
    assert "anomaly_model_loaded" in data
