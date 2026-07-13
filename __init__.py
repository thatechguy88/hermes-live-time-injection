"""Live time injection plugin.

Injects a fresh [YYYY-MM-DD HH:MM TZ] timestamp into the user's message
every turn. The model always sees the current wall-clock time.

*CACHE FIX*: The injection is PERSISTED to the session database.
Ephemeral injection (API-call-time only) breaks prefix caching on exact-match
APIs (Zhipu/GLM, Anthropic) because the user message reverts to its original
state on the next turn, causing the prefix to diverge and miss the cache.
By persisting the timestamp into the database, conversation history remains
strictly append-only, preserving 100% prefix cache hits.

*IMPLEMENTATION*: Uses the session_id and conversation_history kwargs passed
by the pre_llm_call hook system — no sys._getframe() stack walking.
The current turn's user message is in conversation_history (appended before
the hook fires) but has no 'id' or 'timestamp' keys, so we update by
finding the latest user message row for this session in the DB.
"""

import logging
import sqlite3
import os
import re

logger = logging.getLogger("plugins.live-time-injection")

# Match our own injection pattern so we don't double-inject.
_TS_PATTERN = re.compile(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2} [A-Z]+\]\s")


def register(ctx):
    def on_pre_llm_call(user_message: str, session_id: str = "", conversation_history=None, **kwargs):
        """Inject live timestamp and persist it to the database to preserve caching."""
        try:
            from hermes_time import now as _hermes_now

            _now = _hermes_now()
            _tz_name = _now.strftime("%Z") or "UTC"
            _ts = f"[{_now.strftime('%Y-%m-%d %H:%M')} {_tz_name}]"

            # Skip if the current user message already has a timestamp
            # (e.g. replayed from DB on a subsequent turn).
            if _TS_PATTERN.match(user_message.strip()):
                return None

            # Find the latest user message in conversation_history.
            # The current turn's user message is appended to 'messages'
            # before the hook fires, so it's in conversation_history.
            target_msg = None
            if conversation_history:
                for msg in reversed(conversation_history):
                    if msg.get("role") == "user":
                        content = msg.get("content", "")
                        if content and not _TS_PATTERN.match(content.strip()):
                            target_msg = msg
                        break

            if not target_msg:
                return None

            # Mutate the in-memory message so the LLM sees the timestamp this turn.
            target_msg["content"] = f"{_ts}\n\n{target_msg['content']}"

            # Persist to SQLite so it survives the next turn (cache-safe).
            # The current turn's message dict has no 'id' or 'timestamp' keys,
            # so we update the LATEST user message row for this session.
            db_path = os.path.expanduser("~/.hermes/state.db")
            if os.path.exists(db_path):
                try:
                    with sqlite3.connect(db_path) as conn:
                        conn.execute(
                            "UPDATE messages SET content = ? "
                            "WHERE id = (SELECT id FROM messages "
                            "WHERE session_id = ? AND role = 'user' "
                            "ORDER BY id DESC LIMIT 1)",
                            (target_msg["content"], session_id),
                        )
                        # FTS tables are auto-updated by triggers on UPDATE.
                except Exception as e:
                    logger.warning("live-time-injection failed to update DB: %s", e)

            # Return None — we mutated history directly.
            # Returning {"context": _ts} would cause double ephemeral injection.
            return None
        except Exception:
            logger.debug("live time injection failed", exc_info=True)
            return None

    ctx.register_hook("pre_llm_call", on_pre_llm_call)
