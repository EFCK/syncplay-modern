"""Qt-free room-state tracker.

Diffs successive snapshots of `SyncplayClient.userlist._rooms` and emits
typed events for the Room panel:

- `UserJoined` / `UserLeft` on membership changes
- `UserReadyChanged` on `user.isReady()` flips
- `UserFileChanged` on `user.file` name changes
- `RoomSnapshot` (always) carrying the whole-room current state

Lives next to `MessageRouter` and uses the same listener bus
(`subscribe` / `_emit`) so a single subscriber in MainWindow can route
both router and room events.

No Qt imports — classification logic is unit-testable without
QApplication.
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable, List, Optional

from syncplay.ui.modern.events import (
    RoomSnapshot,
    UserFileChanged,
    UserJoined,
    UserLeft,
    UserReadyChanged,
)


Listener = Callable[[object], None]


def _filename_of(user: Any) -> str:
    """Best-effort basename of the file the user is playing.

    Upstream's `user.file["name"]` is sometimes a basename and sometimes
    a full path/URL depending on how the file was opened. We strip any
    directory components so the UI shows just the final filename.
    """
    file_attr = getattr(user, "file", None) or {}
    if not isinstance(file_attr, dict):
        return ""
    raw = file_attr.get("name") or file_attr.get("path") or ""
    if not raw:
        return ""
    # Strip both POSIX and Windows separators — basename doesn't handle
    # the foreign separator on the wrong platform.
    raw = raw.replace("\\", "/")
    return os.path.basename(raw) or raw


def _ready_of(user: Any) -> bool:
    if not hasattr(user, "isReady"):
        return False
    try:
        return bool(user.isReady())
    except Exception:
        return False


class RoomState:
    def __init__(self) -> None:
        self._listeners: List[Listener] = []
        # Map of username -> {"ready": bool, "filename": str, "is_self": bool}
        self._last: dict = {}
        self._last_room: str = ""

    def subscribe(self, listener: Listener) -> None:
        self._listeners.append(listener)

    def last_self_ready(self) -> bool:
        """The local user's ready state in the most recent snapshot.

        Used by the toggle button to decide which state to send next
        without depending on upstream's `currentUser.isReady()` (which
        can transiently return None and confuse `not isReady()`).
        """
        for state in self._last.values():
            if state.get("is_self"):
                return bool(state.get("ready"))
        return False

    def _emit(self, event: object) -> None:
        for listener in self._listeners:
            listener(event)

    def update_from_rooms(self, currentUser: Any, rooms: dict) -> None:
        """Take a snapshot of `rooms`, diff it, emit events.

        `rooms` matches `SyncplayClient.userlist._rooms`: a dict mapping
        room name to an iterable of user objects with at least
        `username`, `isReady()`, and `file` (dict-or-None).
        """
        ts = time.time()
        current_username = getattr(currentUser, "username", None) if currentUser is not None else None
        new_state: dict = {}
        current_room = ""

        for room_name, members in rooms.items():
            for user in members:
                name = getattr(user, "username", None)
                if not name:
                    continue
                is_self = (user is currentUser)
                new_state[name] = {
                    "ready": _ready_of(user),
                    "filename": _filename_of(user),
                    "is_self": is_self,
                }
                if is_self:
                    current_room = room_name

        # Diff against the previous snapshot. Emit typed events for
        # each delta. Skip event emission on the very first snapshot
        # (`_last` is empty) so we don't fire a join storm at connect.
        is_first_snapshot = not self._last

        if not is_first_snapshot:
            for name, state in new_state.items():
                prev = self._last.get(name)
                if prev is None:
                    self._emit(UserJoined(user=name, room=current_room, timestamp=ts))
                    if state["filename"]:
                        self._emit(UserFileChanged(user=name, filename=state["filename"], timestamp=ts))
                    if state["ready"]:
                        self._emit(UserReadyChanged(user=name, ready=True, timestamp=ts))
                    continue
                if prev["ready"] != state["ready"]:
                    self._emit(UserReadyChanged(user=name, ready=state["ready"], timestamp=ts))
                if prev["filename"] != state["filename"]:
                    self._emit(UserFileChanged(user=name, filename=state["filename"], timestamp=ts))

            for name in self._last.keys() - new_state.keys():
                self._emit(UserLeft(user=name, room=self._last_room, timestamp=ts))

        # Build the panel-ready snapshot.
        users_for_panel = [
            {
                "name": name,
                "ready": state["ready"],
                "is_self": state["is_self"],
                "filename": state["filename"],
            }
            for name, state in sorted(new_state.items(), key=lambda kv: (not kv[1]["is_self"], kv[0].lower()))
        ]
        my_ready = False
        if current_username and current_username in new_state:
            my_ready = new_state[current_username]["ready"]

        self._emit(
            RoomSnapshot(
                users=users_for_panel,
                room=current_room,
                current_user=current_username,
                is_ready=my_ready,
            )
        )

        self._last = new_state
        self._last_room = current_room
