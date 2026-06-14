import asyncio
import json
import os
import threading
from contextlib import suppress

try:
    import websockets
except ImportError:  # pragma: no cover - optional dependency in some environments
    websockets = None


SERVER_LOCK = threading.Lock()
SERVER_STARTED = False
SERVER_LOOP = None
SERVER_APP = None
CLIENTS = {}
CLIENTS_LOCK = threading.Lock()


def progress_socket_settings(app):
    reloader_parent = (
        os.getenv("WATER_USE_WERKZEUG_RELOADER") == "1"
        and os.getenv("WERKZEUG_RUN_MAIN") != "true"
    )
    return {
        "enabled": bool(websockets)
        and app.config.get("START_PROGRESS_SOCKET", True)
        and not app.config.get("TESTING")
        and not reloader_parent,
        "host": app.config.get("PROGRESS_SOCKET_HOST", "127.0.0.1"),
        "port": int(app.config.get("PROGRESS_SOCKET_PORT", 8765)),
    }


def _snapshot_connections(user_id=None):
    with CLIENTS_LOCK:
        if user_id is None:
            return {
                target_user_id: set(connections)
                for target_user_id, connections in CLIENTS.items()
                if connections
            }
        return set(CLIENTS.get(user_id, set()))


def _add_connection(user_id, connection):
    with CLIENTS_LOCK:
        CLIENTS.setdefault(user_id, set()).add(connection)


def _remove_connection(user_id, connection):
    with CLIENTS_LOCK:
        connections = CLIENTS.get(user_id)
        if not connections:
            return
        connections.discard(connection)
        if not connections:
            CLIENTS.pop(user_id, None)


async def _send_json(connection, payload):
    await connection.send(json.dumps(payload, ensure_ascii=False))


async def _authenticate(connection):
    raw_message = await asyncio.wait_for(connection.recv(), timeout=10)
    try:
        payload = json.loads(raw_message)
    except json.JSONDecodeError as exc:
        raise ValueError("认证消息不是合法 JSON") from exc

    token = str(payload.get("token", "")).strip()
    if payload.get("type") != "auth" or not token:
        raise ValueError("首条消息必须是包含 token 的 auth 消息")

    with SERVER_APP.app_context():
        from .auth import read_token
        from .services import get_user_by_id

        token_payload = read_token(token)
        user = get_user_by_id(token_payload["user_id"])

    if not user or int(user["status"]) != 1:
        raise ValueError("当前用户不可用，请重新登录")
    return user


async def _handle_connection(connection):
    user_id = None
    try:
        user = await _authenticate(connection)
        user_id = user["user_id"]
        _add_connection(user_id, connection)
        await _send_json(
            connection,
            {
                "type": "ready",
                "userId": user_id,
                "roleCode": user["role_code"],
            },
        )
        await connection.wait_closed()
    except Exception as exc:  # pragma: no cover - network errors are hard to reproduce deterministically
        with suppress(Exception):
            await _send_json(connection, {"type": "error", "message": str(exc)})
        with suppress(Exception):
            await connection.close()
    finally:
        if user_id is not None:
            _remove_connection(user_id, connection)


async def _broadcast(payload, user_id=None):
    if user_id is None:
        targets = []
        for connections in _snapshot_connections().values():
            targets.extend(connections)
    else:
        targets = list(_snapshot_connections(user_id))

    stale = []
    for connection in targets:
        try:
            await _send_json(connection, payload)
        except Exception:
            stale.append(connection)

    if user_id is None:
        with CLIENTS_LOCK:
            for target_user_id, connections in list(CLIENTS.items()):
                for connection in stale:
                    connections.discard(connection)
                if not connections:
                    CLIENTS.pop(target_user_id, None)
    else:
        for connection in stale:
            _remove_connection(user_id, connection)


def notify_user(user_id, payload):
    if not SERVER_LOOP:
        return False
    asyncio.run_coroutine_threadsafe(_broadcast(payload, user_id=user_id), SERVER_LOOP)
    return True


def _run_server(app):
    global SERVER_LOOP, SERVER_STARTED

    async def main():
        global SERVER_LOOP
        settings = progress_socket_settings(app)
        SERVER_LOOP = asyncio.get_running_loop()
        async with websockets.serve(
            _handle_connection,
            settings["host"],
            settings["port"],
            ping_interval=20,
            ping_timeout=20,
        ):
            await asyncio.Future()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    except Exception as exc:  # pragma: no cover - startup error path depends on host env
        SERVER_STARTED = False
        app.logger.warning("Progress WebSocket server failed to start: %s", exc)
    finally:
        with suppress(Exception):
            loop.stop()
        with suppress(Exception):
            loop.close()


def bootstrap_progress_socket(app):
    global SERVER_APP, SERVER_STARTED

    settings = progress_socket_settings(app)
    if not settings["enabled"]:
        return

    with SERVER_LOCK:
        if SERVER_STARTED:
            return
        SERVER_APP = app
        thread = threading.Thread(
            target=_run_server,
            args=(app,),
            name="progress-websocket-server",
            daemon=True,
        )
        thread.start()
        SERVER_STARTED = True
