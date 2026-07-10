"""Live time injection plugin.

Injects a fresh [YYYY-MM-DD HH:MM TZ] timestamp into the user's message
every turn. The model always sees the current wall-clock time.

*CACHE FIX*: The injection is now PERSISTED to the session database. 
Previously, this plugin used ephemeral injection (API-call-time only). 
However, ephemeral injection completely breaks prefix caching on exact-match 
APIs (like Zhipu/GLM and Anthropic) because the user message reverts to its 
original state on the next turn, causing the prefix to diverge and miss the 
cache for all subsequent turns (resulting in 90%+ cache misses).
By persisting the timestamp into the database, the conversation history 
remains strictly append-only, preserving 100% prefix cache hits.
"""

import logging
import sqlite3
import os

logger = logging.getLogger("plugins.live-time-injection")


def register(ctx):
    def on_pre_llm_call(user_message: str, **kwargs):
        """Inject live timestamp and persist it to the database to preserve caching."""
        try:
            from hermes_time import now as _hermes_now
            import sys

            _now = _hermes_now()
            _tz_name = _now.strftime("%Z") or "UTC"
            _ts = f"[{_now.strftime('%Y-%m-%d %H:%M')} {_tz_name}]"

            # 1. We must find the agent to access the session messages
            agent = sys._getframe(1).f_locals.get('agent')
            if not agent:
                agent = sys._getframe(2).f_locals.get('agent')
            
            if agent and hasattr(agent, 'session') and hasattr(agent.session, 'messages'):
                # Find the latest user message in the DB memory
                for msg in reversed(agent.session.messages):
                    if msg.get("role") == "user":
                        # If we haven't already injected the timestamp
                        if _ts not in msg.get("content", ""):
                            # 2. Mutate the in-memory object
                            msg["content"] = f"{_ts}\n\n{msg['content']}"
                            
                            # 3. Persist to SQLite so it survives the next turn
                            db_path = os.path.expanduser("~/.hermes/state.db")
                            if os.path.exists(db_path):
                                try:
                                    with sqlite3.connect(db_path) as conn:
                                        conn.execute(
                                            "UPDATE messages SET content = ? WHERE id = ?", 
                                            (msg["content"], msg["id"])
                                        )
                                        # Also update the FTS tables (Hermes triggers should handle this, 
                                        # but just in case we let the triggers do their job via the UPDATE)
                                except Exception as e:
                                    logger.warning(f"live-time-injection failed to update DB: {e}")
                        break
            
            # 4. Return None because we permanently mutated the history. 
            # If we returned {"context": _ts}, Hermes would double-inject it ephemerally.
            return None
        except Exception:
            logger.debug("live time injection failed", exc_info=True)
            return None

    ctx.register_hook("pre_llm_call", on_pre_llm_call)
