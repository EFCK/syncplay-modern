"""Chat panel: user-message bubbles + inline gray system lines.

Phase 2 placeholder. Subscribes to MessageRouter and renders ChatMessage and
SyncEvent events. When an ErrorEvent arrives, inserts a single brief gray
italic notice (`-> ... see Errors tab`) but does not render the error itself.
"""
