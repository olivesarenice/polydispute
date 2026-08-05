# Agent Memory System (Git-Backed)

This directory serves as a **Git-backed Agent Memory System** for `polydispute`. 

It enables any AI coding agent (Antigravity, Cursor, Claude, Copilot) or human developer working from another machine to instantly resume work with full context.

---

## Files

* **[`index.json`](./index.json):** The master machine-readable memory index. Lists active session pointers, topics, key decisions, and session file references.
* **`{conversation_id}.json`:** Full prompt-response turn history and executive summaries for individual sessions.

---

## Agent Bootstrapping (New Machine / Next Session)

When an agent initializes on another device:
1. Read **[`docs/conversations/index.json`](./index.json)** in a single tool call.
2. Read the active session file specified by `active_session_id` (`docs/conversations/c699e41c-0bee-440b-b34a-8f31a2d04196.json`).
