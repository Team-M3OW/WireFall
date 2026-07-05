def test_rules_endpoint(client):
    response = client.get("/rules")
    assert response.status_code in (200, 503)


def test_add_invalid_rule(client):
    response = client.post("/rules", json={"rule": "[invalid"})
    assert response.status_code in (400, 503)
