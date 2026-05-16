# Chat / Room-status split + ready-button + chat newline fix

**Date:** 2026-05-17
**Status:** approved, implementing

## Goal

Split the sidebar into two purpose-built tabs and fix the chat newline
bug along the way.

- **Chat tab** — chronological text-only log: chat messages, plus the
  pause/unpause/seek and join/leave sync events from upstream rendered
  as gray italic lines (one per line, newline-respecting).
- **Room tab** *(new)* — current-state view: every user in the room with
  their ready dot and currently-loaded file; an event log of
  join/leave/file-load/ready underneath; a single toggle button at the
  bottom that flips the local user's ready state.
- **Errors tab** — unchanged.

Default ready state at startup is **not ready**, regardless of the saved
INI value.

## Motivation

Today every upstream `showMessage(...)` line lands in the chat as a gray
italic notice — chat messages, sync events, ready toggles, file loads,
and per-room file-difference notices, all in one flat stream. On a busy
room the actual conversation gets buried.

Worse, the lines that *do* arrive from upstream often contain embedded
`\n` newline characters (formatted for terminal output); they're
HTML-escaped and dropped into a single `<p>` element, so HTML
whitespace-collapsing renders the whole message as one run-on line.

The room tab gives state changes their own home and lets the chat go
back to being a chat. The newline fix makes any remaining gray lines
actually readable.

## Non-goals

- No protocol changes — everything is built from existing UiManager
  hooks (`showMessage`, `userListChange`, `showUserList`).
- No new persistence — the Room tab is a pure derivative of
  `client.userlist._rooms`, refreshed on every `userListChange`.
- No mid-session "remember I want to be ready" preference — every
  launch starts as not-ready, full stop.

## Approach summary

Pick **Option A** from brainstorming: a Qt-free `RoomState` class
alongside `MessageRouter`. Snapshots `client.userlist._rooms`, diffs
against the previous snapshot, emits typed events (`UserJoined`,
`UserLeft`, `UserReadyChanged`, `UserFileChanged`) plus a fresh
`RoomSnapshot` for the panel to render whole.

The `showMessage` channel keeps emitting localized strings as generic
`SyncEvent`s for the chat — but with a small swallow-list filter that
drops the `"loaded file"` / `"is ready"` / `"is not ready"` / `"file
differences"` substrings so they don't appear in chat (their typed
equivalents already render in the Room tab).

## Components

| File | Status | Purpose |
| --- | --- | --- |
| `syncplay/ui/modern/events.py` | modify | Add `UserJoined`, `UserLeft`, `UserReadyChanged`, `UserFileChanged`, `RoomSnapshot` dataclasses. |
| `syncplay/ui/modern/roomState.py` | new | Qt-free. Owns `_last: dict[str, dict]`. One public method `update_from_rooms(currentUser, rooms_attr)` that diffs and emits via a shared listener bus. |
| `syncplay/ui/modern/roomPanel.py` | new | QWidget with three vertical regions: snapshot table, event log, ready toggle button. |
| `syncplay/ui/modern/chatPanel.py` | modify | `render_sync()` splits `event.detail` on `\n` and renders each line as its own `<p>`. |
| `syncplay/ui/modern/messageRouter.py` | modify | `showMessage()` skips emission for swallow-list matches (still runs the connection-state sniff first). |
| `syncplay/ui/modern/sidebarTabs.py` | modify | Constructor grows a third argument; tab order becomes Chat / Room / Errors. |
| `syncplay/ui/modern/mainWindow.py` | modify | Wire up `RoomState` + `RoomPanel`. `userListChange()` and `showUserList()` call `RoomState.update_from_rooms(...)`. `_on_router_event` routes new event types to `RoomPanel`. Ready-button signal calls `client.toggleReady(manuallyInitiated=True)`. |
| `syncplay/ui/ConfigurationGetter.py` | modify | After `_parseConfigFile`, force `self._config['readyAtStart'] = False`. INI not rewritten. |

## Data flow

```
SyncplayClient.userlist changes
        │
        ▼  (upstream callback, no args)
MainWindow.userListChange()
        │  pulls client.userlist._rooms + currentUser
        ▼
RoomState.update_from_rooms(currentUser, rooms)
        │
        ├─ diff against _last snapshot
        │   for each delta:
        │     emit UserJoined / UserLeft / UserReadyChanged / UserFileChanged
        ├─ emit RoomSnapshot(users=[…])
        │
        ▼
MainWindow._on_router_event(evt)       (RoomState shares the same listener bus)
        ├─ RoomSnapshot          → roomPanel.set_snapshot(evt)
        └─ Joined/Left/Ready/File → roomPanel.append_log_line(text, ts)
```

The `showMessage` path is unchanged for everything outside the
swallow-list. For example, an upstream "user X paused at 0:14:22"
message still renders as a gray italic line in chat.

## Ready button

- Single `QPushButton` at the bottom of `RoomPanel`.
- Label reflects the *current* ready state from the latest snapshot:
  `"I'm ready"` when not ready, `"I'm not ready"` when ready.
- Click handler emits a Qt signal `readyToggleRequested`.
- MainWindow connects it to `client.toggleReady(manuallyInitiated=True)`.
- After the toggle, upstream calls `userListChange()` → snapshot →
  `set_snapshot` → button label updates.

## Default not-ready

- `ConfigurationGetter._parseConfigFile()` ends with
  `self._config['readyAtStart'] = False`. This overrides whatever value
  is in the INI on disk.
- The INI keeps its old value; we just don't honor it. (If we ever want
  to make this configurable again, the simplest path is to remove the
  override line.)

## showMessage swallow-list

Module-level constant in `messageRouter.py`:

```python
_SWALLOWED_SUBSTRINGS = (
    "loaded file",        # "<user> loaded file: ..."
    "is ready",           # "<user> is ready"
    "is not ready",       # "<user> is not ready"
    "no longer ready",    # alternate phrasing variant
    "file differences",   # the per-room "<user> playing <X>, you have <Y>" notice
)
```

`showMessage()` runs `message.lower()` once, checks the substrings,
returns early if any matches. The connection-state sniff runs *above*
the swallow check (so we don't lose connect/disconnect signals if a
future translation accidentally overlaps).

Documented inline as locale-fragile. If a translation breaks the
suppression, the lines reappear in chat — degrades gracefully.

## Testing

Headless (no QApplication needed for `RoomState` / `MessageRouter`):

- `RoomState.update_from_rooms` with a sequence of fake rooms dicts:
  - empty → 1 user → emits `UserJoined`
  - same → no events
  - user ready toggled → emits `UserReadyChanged`
  - user file changed → emits `UserFileChanged`
  - user removed → emits `UserLeft`
  - `currentUser.isReady()` reflected in `RoomSnapshot`
- `MessageRouter.showMessage` with each swallow-list substring: no
  emission. With a non-matching string: one emission. With a
  connection-state string: connection-state emission still happens.

With QApplication (offscreen):

- `RoomPanel.set_snapshot()` renders the user table; `append_log_line`
  appends to the log; the toggle button's label flips on snapshot
  ready-state change; the `readyToggleRequested` signal fires on click.
- `ChatPanel.render_sync` with `"a\nb\nc"` produces three visible lines
  (assertable via the document's plain text).

End-to-end (manual): launch two instances against `syncplay.pl`, join
the same room, observe:
- Both start not-ready.
- Chat tab shows only chat / pause / seek / join / leave.
- Room tab shows the user list with ready dots and filenames.
- Clicking Ready flips both the button label and the dot in the user
  list.

## Risk / rollback

- All changes are UI-side; the protocol-compatibility boundary
  (`client.py`, `protocols.py`, `constants.py`) is untouched.
- The swallow-list is the only locale-fragile piece; the worst-case
  failure mode is "chat shows extra lines" — non-breaking.
- `readyAtStart=False` override is one line. Rollback = remove the line.
