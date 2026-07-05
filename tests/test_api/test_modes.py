def test_set_valid_mode(client):
    response = client.post("/set-mode/fast")
    assert response.status_code in (200, 503)


def test_set_invalid_mode(client):
    response = client.post("/set-mode/invalid")
    assert response.status_code == 400
