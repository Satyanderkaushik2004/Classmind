"""
webrtc_signaling.py  —  ClassMind WebRTC Signaling Server
==========================================================
A fully self-contained FastAPI router that handles WebRTC signaling
for the Live Class video feature.

HOW TO MOUNT (add these 2 lines to main.py):
  from webrtc_signaling import vc_router
  app.include_router(vc_router)

Put both lines AFTER the `app = FastAPI(...)` line (around line 881).

WebSocket endpoint:
  ws://host/ws/vc/{session_code}?peer_id=...&role=...&name=...

This module is FULLY ISOLATED from existing ClassMind WebSocket routes.
It shares no state with the teacher/student WebSocket handlers.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Dict, Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from store import now, sessions

log = logging.getLogger("classmind.vc")

vc_router = APIRouter(tags=["Live Class / WebRTC"])

# ══════════════════════════════════════════════════════════════════
#  In-memory VC room registry
#  Structure: { session_code -> { peer_id -> PeerEntry } }
#  Lifecycle: room created on first join, auto-deleted when empty.
# ══════════════════════════════════════════════════════════════════

vc_rooms: Dict[str, Dict[str, dict]] = {}


def _get_room(session_code: str) -> Dict[str, dict]:
    if session_code not in vc_rooms:
        vc_rooms[session_code] = {}
    return vc_rooms[session_code]


def _cleanup_room(session_code: str) -> None:
    if session_code in vc_rooms and not vc_rooms[session_code]:
        del vc_rooms[session_code]
        log.info("[VC] Room %s destroyed (empty)", session_code)


async def _send(ws: WebSocket, msg: dict) -> bool:
    """Fire-and-forget send. Returns False on failure."""
    try:
        await ws.send_text(json.dumps(msg, default=str))
        return True
    except Exception as exc:
        log.debug("[VC] send failed: %s", exc)
        return False


async def _broadcast(session_code: str, msg: dict, exclude: Optional[str] = None) -> None:
    """Send msg to all peers in room except the excluded peer_id."""
    room = vc_rooms.get(session_code, {})
    for pid, peer in list(room.items()):
        if pid == exclude:
            continue
        await _send(peer["ws"], msg)


def _peer_summary(peer: dict) -> dict:
    """Public-safe summary of a peer (no WebSocket reference)."""
    return {
        "peer_id":   peer["peer_id"],
        "name":      peer["name"],
        "role":      peer["role"],
        "muted":     peer["muted"],
        "video_off": peer["video_off"],
        "joined_at": peer["joined_at"],
    }


# ══════════════════════════════════════════════════════════════════
#  Signaling WebSocket
# ══════════════════════════════════════════════════════════════════

@vc_router.websocket("/ws/vc/{session_code}")
async def vc_signaling(
    ws: WebSocket,
    session_code: str,
    peer_id: str  = Query(...,  description="Unique ephemeral ID for this peer"),
    role: str     = Query("student", description="teacher | student"),
    name: str     = Query("Anonymous", description="Display name"),
):
    """
    WebRTC signaling endpoint for the ClassMind Live Class feature.

    Message protocol (JSON over WebSocket):
    ─────────────────────────────────────────
    CLIENT → SERVER:
      { type: "offer",          target, sdp }
      { type: "answer",         target, sdp }
      { type: "ice_candidate",  target, candidate }
      { type: "mute_state",     muted: bool }
      { type: "video_state",    video_off: bool }
      { type: "teacher_mute_all" }            (teacher only)
      { type: "kick_peer",      target }       (teacher only)
      { type: "ping" }

    SERVER → CLIENT:
      { type: "room_joined",    peers: [...], peer_id }
      { type: "peer_joined",    peer_id, name, role }
      { type: "peer_left",      peer_id, name }
      { type: "offer",          from, from_name, sdp }
      { type: "answer",         from, from_name, sdp }
      { type: "ice_candidate",  from, candidate }
      { type: "peer_mute_state", peer_id, muted }
      { type: "peer_video_state", peer_id, video_off }
      { type: "force_mute" }
      { type: "kicked" }
      { type: "pong" }
      { type: "error",          message }
    """
    # ── Validate session exists ────────────────────────────────────
    s = sessions.get(session_code)
    if not s:
        await ws.accept()
        await _send(ws, {"type": "error", "message": f"Session '{session_code}' not found."})
        await ws.close()
        return

    await ws.accept()

    room = _get_room(session_code)

    # ── Reject duplicate peer_id (e.g., browser tab refresh race) ─
    if peer_id in room:
        old_ws = room[peer_id]["ws"]
        try:
            await old_ws.close()
        except Exception:
            pass

    # ── Register this peer ─────────────────────────────────────────
    room[peer_id] = {
        "ws":        ws,
        "peer_id":   peer_id,
        "role":      role,
        "name":      name,
        "muted":     False,
        "video_off": False,
        "joined_at": now(),
    }
    log.info("[VC] %s '%s' (id=%s) joined room %s  [%d peer(s)]",
             role, name, peer_id, session_code, len(room))

    # ── Send existing participants to the new joiner ───────────────
    existing_peers = [
        _peer_summary(p)
        for pid, p in room.items()
        if pid != peer_id
    ]
    await _send(ws, {
        "type":    "room_joined",
        "peer_id": peer_id,
        "peers":   existing_peers,
    })

    # ── Announce new joiner to everyone else ──────────────────────
    await _broadcast(session_code, {
        "type":    "peer_joined",
        "peer_id": peer_id,
        "name":    name,
        "role":    role,
    }, exclude=peer_id)

    # ── Message loop ──────────────────────────────────────────────
    try:
        while True:
            raw  = await ws.receive_text()
            data = json.loads(raw)
            t    = data.get("type", "")

            # ── Forwarded signaling (offer / answer / ICE) ──────
            if t in ("offer", "answer", "ice_candidate"):
                target = data.get("target")
                if target and target in room:
                    fwd = {
                        **data,
                        "from":      peer_id,
                        "from_name": name,
                    }
                    await _send(room[target]["ws"], fwd)
                else:
                    log.debug("[VC] %s target '%s' not in room (may have left)", t, target)

            # ── Mute state change ────────────────────────────────
            elif t == "mute_state":
                room[peer_id]["muted"] = bool(data.get("muted", False))
                await _broadcast(session_code, {
                    "type":    "peer_mute_state",
                    "peer_id": peer_id,
                    "muted":   room[peer_id]["muted"],
                }, exclude=peer_id)

            # ── Video state change ───────────────────────────────
            elif t == "video_state":
                room[peer_id]["video_off"] = bool(data.get("video_off", False))
                await _broadcast(session_code, {
                    "type":      "peer_video_state",
                    "peer_id":   peer_id,
                    "video_off": room[peer_id]["video_off"],
                }, exclude=peer_id)

            # ── Teacher: mute all students ───────────────────────
            elif t == "teacher_mute_all":
                if role == "teacher":
                    log.info("[VC] Teacher '%s' muted all in room %s", name, session_code)
                    await _broadcast(session_code, {
                        "type": "force_mute",
                        "by":   peer_id,
                    }, exclude=peer_id)

            # ── Teacher: remove a peer ───────────────────────────
            elif t == "kick_peer":
                if role == "teacher":
                    target = data.get("target")
                    if target and target in room:
                        log.info("[VC] Teacher kicked peer %s from room %s", target, session_code)
                        await _send(room[target]["ws"], {"type": "kicked"})
                        # Peer's own disconnect handler will clean up

            # ── Heartbeat ────────────────────────────────────────
            elif t == "ping":
                await _send(ws, {"type": "pong", "ts": now()})

    except WebSocketDisconnect:
        log.info("[VC] %s '%s' disconnected from room %s", role, name, session_code)
    except Exception as exc:
        log.warning("[VC] Unexpected error for peer %s: %s", peer_id, exc)
    finally:
        # ── Clean up this peer ────────────────────────────────────
        if room.get(peer_id, {}).get("ws") is ws:
            room.pop(peer_id, None)
        _cleanup_room(session_code)

        # ── Notify remaining peers ────────────────────────────────
        await _broadcast(session_code, {
            "type":    "peer_left",
            "peer_id": peer_id,
            "name":    name,
        })


# ══════════════════════════════════════════════════════════════════
#  REST helper – current participants in a room (for debugging)
# ══════════════════════════════════════════════════════════════════

@vc_router.get("/api/vc/{session_code}/participants")
async def vc_participants(session_code: str):
    """Return current VC participants for a session. Useful for debugging."""
    room = vc_rooms.get(session_code, {})
    return {
        "session_code": session_code,
        "count":        len(room),
        "participants": [_peer_summary(p) for p in room.values()],
    }
