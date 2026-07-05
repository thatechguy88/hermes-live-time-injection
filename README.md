# hermes-live-time-injection

A [Hermes Agent](https://github.com/NousResearch/hermes-agent) plugin that gives your agent a live sense of "now."

## What it does

Injects a fresh `[YYYY-MM-DD HH:MM TZ]` timestamp into every user message at API-call time via the `pre_llm_call` hook. The model always knows the current wall-clock time without calling a tool.

```
[2026-07-04 19:10 PDT]
```

This is appended to your message — ephemeral, never persisted to the session database, never baked into the cached system prompt. Transcripts stay clean. Prompt caching stays intact.

## Why

Hermes has session-level time (`Conversation started: ...`) but no turn-level live time. The agent doesn't know "today" or "right now" without explicitly calling a tool. This plugin fixes that with zero core modifications.

Solves [Issue #10421](https://github.com/NousResearch/hermes-agent/issues/10421) — turn-level live time context — using the exact mechanism the issue requests: `pre_llm_call` ephemeral context injection.

## Install

```bash
hermes plugins install thatechguy88/hermes-live-time-injection
```

Or manually: copy `plugin.yaml` and `__init__.py` into `~/.hermes/plugins/live-time-injection/`.

## Enable

```bash
hermes plugins enable live-time-injection
```

Per profile:

```bash
hermes plugins enable live-time-injection --profile naevis
```

Restart your gateway:

```bash
hermes gateway restart
```

## How it works

- Registers a `pre_llm_call` hook that fires once per turn
- Uses `hermes_time.now()` for timezone-aware current time
- Returns `{"context": "[2026-07-04 19:10 PDT]"}` — Hermes appends this to the user message at API call time
- Original message is never mutated
- System prompt is never touched (prompt cache prefix stays stable)
- Nothing extra is persisted to the session DB

## Requirements

- Hermes Agent v0.9.0+ (needs `pre_llm_call` hook support)

## License

MIT
