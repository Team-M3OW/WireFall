def test_analyze_missing_model(client, sample_request):
    response = client.post("/analyze", json=sample_request)
    assert response.status_code in (200, 503)
    if response.status_code == 503:
        assert "unavailable" in response.json()["detail"].lower()
