from __future__ import annotations


async def test_readyz_checks_database_and_redis(client):
    res = await client.get("/readyz")

    assert res.status_code == 200
    body = res.json()
    assert body == {"ok": True, "checks": {"database": True, "redis": True}}
