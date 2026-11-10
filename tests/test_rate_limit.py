import asyncio
import time

import httpx

from app.codeforces import Codeforces


def test_concurrent_callers_share_request_pacing():
    times = []

    def handler(request):
        times.append(time.monotonic())
        return httpx.Response(200, json={"status": "OK", "result": []})

    async def run():
        cf = Codeforces(interval=0.03, transport=httpx.MockTransport(handler))
        await asyncio.gather(*(cf.call("user.info", handles=str(i)) for i in range(3)))

    asyncio.run(run())
    assert len(times) == 3
    assert all(b - a >= 0.025 for a, b in zip(times, times[1:]))
