"""Shared test helpers.

`collect_events` subscribes a list to any object exposing a
`subscribe(listener)` method and returns the list. Both MessageRouter
and RoomState use the same listener-bus pattern, so this works for
either.
"""

from __future__ import annotations

from typing import Any, List


def collect_events(emitter: Any) -> List[Any]:
    events: List[Any] = []
    emitter.subscribe(events.append)
    return events
