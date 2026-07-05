"""Live time injection plugin.

Injects a fresh [YYYY-MM-DD HH:MM TZ] timestamp into the user's message
every turn via the pre_llm_call hook. The model always sees the current
wall-clock time without breaking prefix caching — context is injected
into the user message only (the only uncached part of the prompt).

The injection is ephemeral: the original user message in conversation
history is never mutated, and nothing extra is persisted to the session
database. Transcripts stay clean automatically.

Solves https://github.com/NousResearch/hermes-agent/issues/10421 as a
zero-core-change plugin using the exact mechanism the issue requests
(pre_llm_call ephemeral context injection).
"""

import logging

logger = logging.getLogger("plugins.live-time-injection")


def register(ctx):
    def on_pre_llm_call(user_message: str, **kwargs):
        """Inject live timestamp as context for the current turn.

        pre_llm_call fires once per turn, before the tool-calling loop.
        Returning {"context": str} appends the text to the user message
        at API call time. The original message is never mutated.
        """
        try:
            from hermes_time import now as _hermes_now

            _now = _hermes_now()
            _tz_name = _now.strftime("%Z") or "UTC"
            _ts = f"[{_now.strftime('%Y-%m-%d %H:%M')} {_tz_name}]"
            return {"context": _ts}
        except Exception:
            logger.debug("live time injection failed", exc_info=True)
            return None

    ctx.register_hook("pre_llm_call", on_pre_llm_call)
