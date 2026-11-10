import asyncio
import time
import httpx


class Codeforces:
    def __init__(self, interval=2.1, transport=None):
        self.lock = asyncio.Lock()
        self.last = 0
        self.interval = interval
        self.transport = transport

    async def call(self, method, **params):
        async with self.lock:
            for attempt in range(3):
                await asyncio.sleep(
                    max(0, self.interval - (time.monotonic() - self.last))
                )
                self.last = time.monotonic()
                try:
                    async with httpx.AsyncClient(
                        timeout=45, transport=self.transport
                    ) as client:
                        response = await client.get(
                            "https://codeforces.com/api/" + method, params=params
                        )
                        response.raise_for_status()
                        body = response.json()
                    if body.get("status") == "OK":
                        return body["result"]
                    message = body.get("comment", "Codeforces rejected the request")
                    if "limit" not in message.lower():
                        raise ValueError(message)
                except (httpx.HTTPError, ValueError) as exc:
                    if isinstance(exc, ValueError) and not isinstance(
                        exc, httpx.HTTPError
                    ):
                        raise
                    if attempt == 2:
                        raise
                await asyncio.sleep(2**attempt)
            raise ValueError("Codeforces rate limit exceeded. Try again later.")

    async def submissions(self, handle, previous, progress):
        rows = {s["id"]: s for s in previous}
        # Always revisit the newest page to refresh judging; stop at known stable IDs.
        stable = {
            s["id"]
            for s in previous
            if s.get("verdict") not in {None, "TESTING", "SUBMITTED"}
        }
        pending = {s["id"] for s in previous} - stable
        offset = 1
        while True:
            page = await self.call(
                "user.status", handle=handle, **{"from": offset, "count": 1000}
            )
            for s in page:
                rows[s["id"]] = s
                pending.discard(s["id"])
            progress(f"Imported {len(rows)} submissions")
            if len(page) < 1000 or (
                any(s["id"] in stable for s in page) and not pending
            ):
                break
            offset += len(page)
        return list(rows.values())
