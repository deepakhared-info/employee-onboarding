def test_health_check(client, url):
    res = client.get(url("/healthz"))

    assert res.status_code == 200
    assert res.json() == {"status": "ok"}
