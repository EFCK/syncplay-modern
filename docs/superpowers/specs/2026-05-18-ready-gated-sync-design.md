# Ready-gated sync

**Date:** 2026-05-18
**Status:** draft, awaiting review

## Goal

Make `Ready` the explicit switch for joining the sync group, and fully
decouple playback control from readiness. A non-ready user watches the
video standalone — their seeks/pauses don't reach the group and the
group's seeks/pauses don't move their player. Pressing Ready snaps the
user to the group's current position and joins them to the sync. The
room is paused-locked until every member has readied up; once everyone
is ready, playback unlocks and someone presses Play to start.

This replaces the current Syncplay model, where pressing Play auto-flips
the local user to Ready and sync events flow regardless of ready state.

## Motivation

Three concrete problems with the upstream model:

1. **Loading a video implies commitment.** Hitting Play to check a
   subtitle track or scrub the opening credits silently marks you ready
   and pushes your position to the room. There's no "I'm just messing
   with my player, not joining yet" state.
2. **Sync is always on.** Even when you're explicitly not ready,
   upstream still applies the group's pause/seek to your player via
   `_changePlayerStateAccordingToGlobalState`. The Ready button only
   gates auto-unpause; everything else still syncs.
3. **The unpause-action setting is the only knob.** Today's
   `UNPAUSE_IFOTHERSREADY_MODE` partially covers (1) for unpausing but
   doesn't address (2) at all, and the failure mode is opaque — the
   user pauses, gets silently flipped to not-ready, and is confused.

The replacement model collapses this into one rule: **ready is in,
not-ready is out.**

## Non-goals

- **No new sync protocol.** Wire format is unchanged. This is purely a
  local gating change. Other clients in the room see a not-ready user
  exactly as upstream Syncplay does today (idle, not sending state).
- **No re-implementing seek/pause primitives.** We're not building a
  parallel pipeline; we're inserting `if self._syncEngaged()` checks at
  the existing send/receive boundaries.
- **No new UI surface.** The existing Ready toggle in the Room tab is
  the entire user interface for this. No mode picker, no "join sync"
  button.
- **No config flag for behavior.** Per brainstorming, the new model
  fully replaces the old one. The `unpauseAction` setting becomes
  vestigial and is removed from the settings panel (the underlying
  config key is left in `ConfigurationGetter` for upstream-compat).
- **`readyAtStart` is preserved** as-is; users who want to start the
  session already-in-sync can still tick that box.

## User-facing behavior

### Not-ready user (standalone)

- Drag/drop a video or `File → Open File…` loads it locally **and is
  announced to the room**. Peers see "alice loaded X.mkv" even while
  alice is still not-ready — file presence is informational, not a
  sync action, and hiding it makes the room feel broken when someone
  is browsing options. (Revised 2026-05-18: original draft suppressed
  the announcement; implementation found that this made loaded files
  invisible to the loader and to peers until ready, which read as a
  bug.)
- Play, pause, seek, speed change, audio/subtitle track switches all
  act on the local player only. Nothing reaches the wire.
- The user does not appear in the all-ready calculation as "ready";
  others see them as not-ready (same as upstream).
- The group's pause/play/seek does **not** move the local player. The
  user keeps watching whatever they were watching.
- The Room tab still updates with snapshots so the user can see who
  else is in the room, ready dots, file labels, the activity log.

### Pressing Ready (not-ready → ready)

- The local player snaps to `_globalPosition` (group's current
  position) and matches `_globalPaused`.
- The local file is announced to the room at this point (if it wasn't
  already), so others can see what we're loading.
- From this moment, outbound `sendState` and inbound state-application
  resume.

### Pressing Ready (ready → not-ready)

- The user drops out of the sync group. The local player keeps playing
  wherever it is — no snap back, no pause.
- Outbound `sendState` goes silent again; inbound state stops moving
  the player.

### Ready user

- Play / pause / seek propagates to the group as today.
- **Pressing Pause never silently un-readies you.** This is the key
  decoupling. To leave the sync group, the user presses the Ready
  button explicitly.
- Unpause is gated: if any room member is not ready, the local unpause
  call is rejected with a toast ("Waiting for everyone to ready up").
- Once every room member is ready, unpause works normally. There is no
  auto-play countdown — someone presses Play.

### Edge cases

- **Alone in room + ready:** trivially "all ready". Playback unlocks.
- **Last user becomes not-ready while playing:** the group pauses at
  current position (server-driven, since the room is no longer
  all-ready). Other ready members are paused by the standard sync.
- **File load while not-ready:** the file path/size **is** sent to
  the room immediately. Peers see who loaded what regardless of
  ready state. The room's "file difference" warning fires as usual
  if the new file doesn't match the room — that's the desired
  signal, not noise.
- **Disconnect while not-ready:** unchanged from today.
- **Room change:** moving to a new room resets ready to false
  (preserves upstream behavior). The new room's snapshot drives the
  next snap-on-ready.
- **Playlist advance:** if the room auto-advances to the next file and
  the user is not-ready, the local player keeps playing the current
  file. When the user readies up, they snap to the new file/position
  via the normal openFile flow.

## Architecture

### `_syncEngaged()` predicate

Add a single method on `SyncplayClient`:

```python
def _syncEngaged(self) -> bool:
    """True when the local user is participating in group sync.

    syncplay-modern: when False, outbound state is suppressed and
    inbound state is not applied to the player (we still mirror
    _globalPosition for snap-on-ready).
    """
    user = self.userlist.currentUser
    return bool(user is not None and user.isReady())
```

Call sites guard against `currentUser` being None during early
connection — `isReady()` can return None there, which we treat as
not-engaged.

### Four intercept points in `client.py`

All edits sit inside `# syncplay-modern: ready-gated sync` /
`# end syncplay-modern` comment blocks so upstream rebases can find
and reconcile them.

**1. Outbound state silence — `_determinePlayerStateChange`**
(client.py:~253). Wrap the `_protocol.sendState(...)` calls:

```python
if (pauseChange or seeked) and self._protocol and self._syncEngaged():
    ...
    self._protocol.sendState(...)
```

Also wrap the `_protocol.sendState(...)` call in `setPosition`
(client.py:~835).

**2. Inbound state silence — `_changePlayerStateAccordingToGlobalState`**
(client.py:414). Restructure as:

```python
def _changePlayerStateAccordingToGlobalState(self, position, paused, doSeek, setBy):
    # Always mirror group state — we use it for snap-on-ready.
    self._globalPaused = paused
    self._globalPosition = position
    self._lastGlobalUpdate = time.time()

    if not self._syncEngaged():
        return False  # silent: don't touch the player

    # ... existing body unchanged
```

**3. Decouple play/pause from ready — `_determinePlayerStateChange`**
(client.py:~241–249). Remove the `_toggleReady` call entirely. The
helper itself stays (it's still useful for the explicit-toggle
codepath) but is no longer invoked from the pause-change handler.

The "you paused, so I'll mark you not-ready" auto-flip is what we are
specifically removing.

**4. Snap-on-ready — `setReady` handler** (client.py:1086). On the
not-ready → ready transition for the current user, apply current
global state to the player:

```python
def setReady(self, username, isReady, manuallyInitiated=True, setBy=None):
    oldReadyState = self.userlist.isReady(username)
    ...
    self.userlist.setReady(username, isReady)

    # syncplay-modern: snap to group when joining sync
    if username == self.userlist.currentUser.username \
       and oldReadyState != True and isReady == True:
        if self._lastGlobalUpdate is not None:
            self._player.setPosition(self._globalPosition)
            self._player.setPaused(self._globalPaused)
        # announce the current file to the room if we held it back
        self._announceCurrentFileIfNeeded()
    # end syncplay-modern

    if oldReadyState != isReady:
        ...
```

### Strict all-ready unpause gate — `instaplayConditionsMet`

Today this method honors the `unpauseAction` setting. We collapse all
branches to one rule:

```python
def instaplayConditionsMet(self):
    if self.isPlayingMusic():
        return True
    if not self.userlist.currentUser.canControl():
        return False
    # syncplay-modern: strict — every room member must be ready.
    return (
        self.userlist.currentUser.isReady()
        and self.userlist.areAllUsersInRoomReady()
    )
```

This is the single biggest behavioral change for ready users: hitting
Play while someone in the room is not-ready does nothing (we surface
a toast — see UI section).

### File announcements always flow

`sendFile` is **not** gated by `_syncEngaged()`. The upstream flow is
preserved: `openFile` → libvlc parse → `_executeFileUpdate` →
`self.sendFile()` → `_protocol.sendFileSetting(...)`. Peers see what
each user is loading regardless of ready state.

The original draft of this spec held the announcement back until
the not-ready → ready transition. In practice this surfaced as a bug:
the loader couldn't see their own file in the room panel (the server
echo never came), peers couldn't see who had loaded what, and the
"file diff" warning that exists precisely to flag a mismatched file
load never fired. Reverted 2026-05-18.

### UI changes

**Settings panel** (`syncplay/ui/modern/settingsPanel.py`):
- Remove the `_UNPAUSE_OPTIONS` combo and its row. Replace the row
  with a short label explaining the new rule: "Playback starts when
  every user in the room is ready."
- Leave `readyAtStart` checkbox in place.

**Room tab** (`syncplay/ui/modern/roomPanel.py`):
- No structural changes. The Ready toggle button keeps its current
  wiring (`readyToggleRequested` → `mainWindow._on_ready_toggle`).
- Update the button label semantics: when not-ready, the label hints
  at the consequence ("Ready (join sync)"); when ready, ("Not Ready
  (watch alone)"). Keep this lightweight — one extra label string,
  no new widgets.

**Toast on blocked unpause** (`syncplay/ui/modern/mainWindow.py`):
- Wire a new client-side signal `unpauseBlockedBecauseNotAllReady` and
  show a toast: "Waiting for {count} user(s) to ready up". The toast
  module already supports this style of message.

## Data flow

```
[not-ready user]
   Local input ──> EmbeddedVlcPlayer (direct)
                   _protocol.sendState  ← SUPPRESSED
   Server state ──> _changePlayerStateAccordingToGlobalState
                    ├─ updates _globalPosition / _globalPaused
                    └─ returns False (no player touch)

[becoming ready]
   Ready button ──> _protocol.setReady(True)
   Server confirms ──> setReady(username=me, isReady=True)
                       ├─ player.setPosition(_globalPosition)
                       ├─ player.setPaused(_globalPaused)
                       └─ announce held file (if any)

[ready user, all ready]
   Local input ──> EmbeddedVlcPlayer
                   _protocol.sendState  ← FLOWS
   Server state ──> _changePlayerStateAccordingToGlobalState (normal)

[ready user, NOT all ready]
   Play attempt ──> instaplayConditionsMet() == False
                    └─ toast "Waiting for N user(s) to ready up"
                    Player stays paused.
```

## Testing

The Qt-free unit tests in `tests/` already exercise `MessageRouter`.
Add a new test module `tests/test_sync_gating.py` covering:

- `_syncEngaged()` returns False when `currentUser.isReady()` is None
  or False.
- A stubbed protocol records calls; `_determinePlayerStateChange`
  with a paused-change while not-ready makes zero `sendState` calls.
- `_changePlayerStateAccordingToGlobalState` with not-ready leaves
  player paused/position untouched but updates `_globalPosition`.
- `setReady(me, True)` after a global state has arrived calls
  `player.setPosition(_globalPosition)` and `player.setPaused(...)`.
- `instaplayConditionsMet` returns False whenever any room member is
  not-ready, even if the local user is ready and controlling.

These all run headless without `QApplication`.

Manual verification (documented in the implementation plan's
verification block):

1. Two-client local test against a local syncplay server.
   - Client A loads a file, plays it, doesn't ready up. Client B
     joins, readies up, plays. Confirm A's video doesn't twitch when
     B plays/pauses/seeks.
   - A readies up. Confirm A snaps to B's position and pause state.
   - B unreadies. Confirm playback locks; A's Play attempts surface
     the "waiting" toast.
2. Onboarding default still works (`readyAtStart=False`): new user
   joins, video is locally loaded, no ready flip on pause.

## Implementation order

1. Add `_syncEngaged()` + the four intercept points in `client.py`
   (no UI changes yet). Verify with the new pytest module.
2. Strict `instaplayConditionsMet` + the unpause-blocked toast wiring.
3. File-announcement deferral.
4. Settings panel cleanup.
5. Room tab label tweak.
6. Two-client manual run-through.

## Upstream-rebase notes

All `client.py` edits are inside `# syncplay-modern: ready-gated sync`
markers. The `_syncEngaged` predicate is the only new method; the rest
are guarded modifications to existing methods.

If upstream rewrites `instaplayConditionsMet` (it is the most likely
flashpoint), the rebase strategy is: take upstream's body verbatim,
then replace it with our strict version. Our version intentionally
drops the `unpauseAction` branching; that is a feature regression on
the upstream config surface, which is acceptable per the rollout
decision.
