"""WebSocket router — real-time training log streaming via Redis Pub/Sub."""

import asyncio
import hmac
import json as _json
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
ADMIN_TOKEN = os.getenv("AI_ADMIN_TOKEN", "changeme").strip()

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/logs/{job_id}")
async def stream_logs(websocket: WebSocket, job_id: int):
    """Stream training log lines from Redis Pub/Sub to the WebSocket client."""
    token = websocket.query_params.get("token", "").strip()
    if not token or not hmac.compare_digest(token, ADMIN_TOKEN):
        await websocket.close(code=4401)
        return
    await websocket.accept()

    import redis as redis_lib

    channel = f"train:log:{job_id}"
    loop = asyncio.get_event_loop()

    def _subscribe_and_stream():
        r = redis_lib.Redis.from_url(REDIS_URL)
        pubsub = r.pubsub()
        pubsub.subscribe(channel)
        messages = []
        try:
            for msg in pubsub.listen():
                if msg["type"] != "message":
                    continue
                data = msg["data"]
                if isinstance(data, bytes):
                    data = data.decode("utf-8", errors="replace")
                messages.append(data)
                if data.strip() == "__DONE__":
                    break
        finally:
            pubsub.unsubscribe(channel)
            r.close()
        return messages

    try:
        messages = await loop.run_in_executor(None, _subscribe_and_stream)
        for line in messages:
            if line.strip() == "__DONE__":
                await websocket.send_text(_json.dumps({"type": "done"}))
                break
            await websocket.send_text(_json.dumps({"type": "log", "line": line}))
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
