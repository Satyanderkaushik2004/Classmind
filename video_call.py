"""
video_call.py  —  VYOM WebRTC Signaling Server
Pure WebSocket relay — no external services, no TURN, no database.

Endpoint:  ws://host/ws/vc/{session_code}/{user_id}

Message protocol (JSON):
  join            { type, user_id, role }                    → announce presence
  offer           { type, target, data }                     → SDP offer
  answer          { type, target, data }                     → SDP answer
  ice-candidate   { type, target, data }                     → ICE candidate
  participant_joined / participant_left  (server → clients)
  vc_started      (server → all class students via ws_student)
  vc_ended        (server → all class students via ws_student)
"""

from __future__ import annotations

import json
import logging
from typing import Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

log = logging.getLogger("vyom.vc")

# ── In-memory room registry ──────────────────────────────────────
# rooms[session_code][user_id] = WebSocket
rooms: Dict[str, Dict[str, WebSocket]] = {}

router = APIRouter()


# ── helpers ──────────────────────────────────────────────────────

async def _send(ws: WebSocket, data: dict) -> bool:
    try:
        await ws.send_text(json.dumps(data))
        return True
    except Exception as exc:
        log.debug("vc _send failed: %s", exc)
        return False


async def _broadcast_room(session_code: str, data: dict, exclude: str | None = None) -> None:
    room = rooms.get(session_code, {})
    for uid, ws in list(room.items()):
        if uid == exclude:
            continue
        await _send(ws, data)


def _cleanup_room(session_code: str, user_id: str) -> None:
    room = rooms.get(session_code)
    if not room:
        return
    room.pop(user_id, None)
    if not room:
        rooms.pop(session_code, None)
        log.info("VC room %s destroyed (last participant left)", session_code)


# ── WebSocket endpoint ───────────────────────────────────────────

@router.websocket("/ws/vc/{session_code}/{user_id}")
async def vc_signaling(websocket: WebSocket, session_code: str, user_id: str):
    await websocket.accept()

    # Register connection
    if session_code not in rooms:
        rooms[session_code] = {}
    rooms[session_code][user_id] = websocket

    log.info("VC join: session=%s user=%s (room size=%d)", session_code, user_id, len(rooms[session_code]))

    # Notify others in the room that this participant joined
    await _broadcast_room(session_code, {
        "type": "participant_joined",
        "user_id": user_id,
    }, exclude=user_id)

    # Send current participant list to the newcomer
    existing = [uid for uid in rooms[session_code] if uid != user_id]
    await _send(websocket, {
        "type": "room_state",
        "participants": existing,
    })

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "")
            target   = msg.get("target")

            # ── Relay targeted messages (offer / answer / ice-candidate / screen share requests) ──
            if msg_type in ("offer", "answer", "ice-candidate", "screen_share_request", "screen_share_accept", "screen_share_reject") and target:
                room = rooms.get(session_code, {})
                target_ws = room.get(target)
                if target_ws:
                    # Stamp the sender so the receiver knows who this is from
                    await _send(target_ws, {**msg, "from": user_id})
                else:
                    log.debug("VC relay: target %s not in room %s", target, session_code)

            # ── Broadcast (e.g. join announcement or screen share status) ──
            elif msg_type == "join":
                await _broadcast_room(session_code, {
                    "type": "participant_joined",
                    "user_id": user_id,
                    "role": msg.get("role", "student"),
                }, exclude=user_id)

            elif msg_type in ("screen_share_started", "screen_share_stopped"):
                await _broadcast_room(session_code, {
                    "type": msg_type,
                    "user_id": user_id,
                    **msg
                }, exclude=user_id)

            # ── Ignore unknown message types (forward-compat) ──
            else:
                log.debug("VC unknown msg type '%s' from %s", msg_type, user_id)

    except WebSocketDisconnect:
        log.info("VC disconnect: session=%s user=%s", session_code, user_id)
    except Exception as exc:
        log.warning("VC error: session=%s user=%s error=%s", session_code, user_id, exc)
    finally:
        _cleanup_room(session_code, user_id)
        # Notify remaining peers
        await _broadcast_room(session_code, {
            "type": "participant_left",
            "user_id": user_id,
        })
        log.info("VC left: session=%s user=%s (room size=%d)",
                 session_code, user_id, len(rooms.get(session_code, {})))


# ── REST helper: get participants in a room ─────────────────────

@router.get("/api/vc/{session_code}/participants")
async def get_vc_participants(session_code: str):
    """Returns list of user IDs currently in the signaling room."""
    room = rooms.get(session_code, {})
    return {"session_code": session_code, "participants": list(room.keys())}
