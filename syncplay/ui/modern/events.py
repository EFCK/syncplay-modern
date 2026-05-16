"""Typed UI events emitted by MessageRouter to panels.

Plain dataclasses (no Qt) so they can be constructed and matched against from
unit tests without spinning up QApplication.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SyncEventKind(str, Enum):
    PAUSE = "pause"
    UNPAUSE = "unpause"
    SEEK = "seek"
    READY = "ready"
    NOT_READY = "not_ready"
    JOIN = "join"
    LEAVE = "leave"
    FILE_CHANGE = "file_change"
    ROOM_CHANGE = "room_change"
    GENERIC = "generic"


class ErrorSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ConnectionStateKind(str, Enum):
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"


@dataclass
class ChatMessage:
    user: str
    text: str
    is_self: bool = False
    timestamp: float = 0.0


@dataclass
class SyncEvent:
    kind: SyncEventKind
    detail: str
    user: Optional[str] = None
    room: Optional[str] = None
    timestamp: float = 0.0


@dataclass
class ErrorEvent:
    severity: ErrorSeverity
    text: str
    category: str = "general"
    timestamp: float = 0.0


@dataclass
class ConnectionState:
    state: ConnectionStateKind
    detail: str = ""


@dataclass
class UserPresence:
    room: str
    users: list = field(default_factory=list)
    current_user: Optional[str] = None


@dataclass
class FileInfo:
    name: str
    duration: float
    path: str
