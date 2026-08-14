#!/usr/bin/env python3
"""A toy chatbot that reproduces the file-based memory mechanism end to end.

This is the smallest complete loop the survey describes: chat sessions with a
model, model-discretionary curation into a `MEMORY.md` index plus topic files
at session end, and recall in later sessions via index preload + grep + read.
Everything memory-mechanical goes through `ccmem.CCMemory`, so what you watch
here is exactly what the unit tests pin.

Usage, against any OpenAI-compatible chat endpoint (Ollama, LM Studio, llama
server, or a hosted key):

    export CCMEM_BASE_URL=http://localhost:11434/v1   # default shown
    export CCMEM_MODEL=gemma4:26b-a4b-it-qat
    export CCMEM_API_KEY=...                          # only if the server wants one
    export CCMEM_NO_THINK=1                           # reasoning models: skip thinking
    export CCMEM_MAX_TOKENS=4096                      # per-reply budget
    python3 chatbot.py ~/ccmem-demo

Talk normally. `/end` closes the session and runs the curation round (watch
it write the memory directory); running the script again on the same
directory starts a *new* session whose only link to the last one is what
curation saved. `/memory` shows the loaded index view, `/quit` exits without
curating. Stdlib only.
"""

import json
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ccmem  # noqa: E402

BASE_URL = os.environ.get("CCMEM_BASE_URL", "http://localhost:11434/v1")
MODEL = os.environ.get("CCMEM_MODEL", "gemma4:26b-a4b-it-qat")
API_KEY = os.environ.get("CCMEM_API_KEY", "")
MAX_TOKENS = int(os.environ.get("CCMEM_MAX_TOKENS", "4096"))
# CCMEM_NO_THINK=1 asks the server to skip reasoning-model thinking via
# chat_template_kwargs (honoured by mlx_lm and vLLM for Qwen-style models;
# unset it for servers that reject unknown request fields).
NO_THINK = os.environ.get("CCMEM_NO_THINK", "") not in ("", "0")

# ---------------------------------------------------------------------------
# The two prompts. Both are written from the survey (README.md §1 "Writing"):
# the documented discretion phrasing, the four-type taxonomy, and the index
# contract. The original instruction block is unpublished (§7 open gap), so
# these are the reconstruction the study ran with, trimmed to the toy.
# ---------------------------------------------------------------------------

CURATION_SYSTEM = """You have a persistent, file-based memory system: a directory containing MEMORY.md (the index) plus separate topic files. You build up this memory over time across many conversations with the same user. Nothing is saved automatically — you decide what is worth remembering.

Save only what would be useful in a future conversation: durable facts about the user (their life, work, plans, possessions, preferences, habits), corrections and feedback they gave you, project state, and reference material. Do not save pleasantries, one-off task mechanics, or anything with no cross-session value.

Memory types (choose one per topic file): user (facts about the user), feedback (corrections/preferences about how to behave), project (ongoing work state), reference (external facts worth keeping).

The index contract: MEMORY.md is a concise index — one line per entry, each line naming the fact or pointing at the topic file that holds the details. Only the first 200 lines / 25KB of MEMORY.md is loaded at the start of a future session; topic files are NEVER auto-loaded and are only found via the index or grep. Details go in topic files; the index stays short. If a new statement contradicts something already saved, update the existing entry in place rather than adding a duplicate.

You will be shown the current MEMORY.md view and one conversation session. Reply with a fenced JSON block containing the list of memory operations, and nothing else after it:

```json
[{"op": "create", "path": "topic-file.md", "content": "...", "index_line": "- one-line index entry (topic-file.md)", "type": "user", "name": "short name", "description": "one sentence"},
 {"op": "append", "path": "MEMORY.md", "content": "- new one-line fact"},
 {"op": "replace_line", "path": "MEMORY.md", "match": "- old fact line", "content": "- corrected fact line"}]
```

If nothing in the session is worth saving, reply with an empty list. At most 6 operations."""

CHAT_SYSTEM = """You are a helpful assistant with a persistent, file-based memory built up across past sessions with this user.

Below is your memory index (MEMORY.md). Topic files are NOT loaded — to consult one, or to search for something not visible in the index, reply with ONLY a fenced JSON block of tool calls:

```json
[{"tool": "grep", "pattern": "..."}, {"tool": "read", "path": "some-topic.md"}]
```

You will get the results back and can then answer (or search again, up to 3 rounds). If the index already tells you enough, just answer directly. Never invent memories: if it is not in the memory and not in this conversation, say you do not know.

--- MEMORY.md ---
{index}
--- end of MEMORY.md ---"""

FENCE_RE = re.compile(r"```(?:json)?\s*(\[.*?\])\s*```", re.DOTALL)


def chat(messages, chat_fn=None):
    """One completion. `chat_fn` injectable for tests."""
    if chat_fn:
        return chat_fn(messages)
    req = urllib.request.Request(
        BASE_URL.rstrip("/") + "/chat/completions",
        data=json.dumps({"model": MODEL, "messages": messages,
                         "temperature": 0, "max_tokens": MAX_TOKENS,
                         **({"chat_template_kwargs": {"enable_thinking": False}}
                            if NO_THINK else {})}).encode(),
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {API_KEY}"} if API_KEY else {})})
    with urllib.request.urlopen(req, timeout=600) as r:
        msg = json.load(r)["choices"][0]["message"]
        # Reasoning models can burn the whole budget thinking and return no
        # content; surface that instead of crashing on a missing key.
        return msg.get("content") or "<error: model returned no content>"


def parse_fenced_list(text):
    for m in FENCE_RE.finditer(text):
        try:
            v = json.loads(m.group(1))
            if isinstance(v, list):
                return v
        except json.JSONDecodeError:
            continue
    return None


# ---------------------------------------------------------------------------
# Answering with memory: index preload + up to 3 tool rounds.
# ---------------------------------------------------------------------------

def answer(mem, history, user_msg, chat_fn=None, log=print):
    msgs = [{"role": "system",
             "content": CHAT_SYSTEM.replace("{index}", mem.load_index())}]
    msgs += history + [{"role": "user", "content": user_msg}]
    for _ in range(3):
        reply = chat(msgs, chat_fn)
        calls = parse_fenced_list(reply)
        if calls is None or not any(isinstance(c, dict) and c.get("tool")
                                    for c in calls):
            return reply
        results = []
        for c in calls[:4]:
            if not isinstance(c, dict):
                continue
            if c.get("tool") == "grep":
                out = mem.grep(str(c.get("pattern", "")))
                log(f"  [grep {c.get('pattern')!r}]")
            elif c.get("tool") == "read":
                try:
                    out = mem.read_file(str(c.get("path", "")))
                except ValueError as e:
                    out = f"<error: {e}>"
                log(f"  [read {c.get('path')!r}]")
            else:
                continue
            results.append({"tool": c.get("tool"), "result": out})
        msgs += [{"role": "assistant", "content": reply},
                 {"role": "user",
                  "content": "Tool results:\n```json\n"
                             + json.dumps(results, indent=1)
                             + "\n```\nNow answer the user."}]
    return chat(msgs, chat_fn)


# ---------------------------------------------------------------------------
# Curation at session end: one round, plus one rewrite round if the
# post-write check comes back over-limit (mirroring the harness nag).
# ---------------------------------------------------------------------------

def apply_ops(mem, ops, session_id, log=print):
    check = None

    def _index_lines():
        return (open(mem.index_path).read().splitlines()
                if os.path.exists(mem.index_path) else [])

    for op in (ops or [])[:6]:
        if not isinstance(op, dict):
            continue
        kind = str(op.get("op", "")).strip().lower()
        path = str(op.get("path", "")).strip()
        content = str(op.get("content", ""))
        if not path or not kind:
            continue
        is_index = path.strip("/").lower() == "memory.md"
        try:
            if kind == "replace_line" and is_index:
                c = mem.replace_index_line(op.get("match", ""), content)
            elif kind == "append" and is_index:
                # The curation contract forbids duplicate index entries, and
                # models routinely emit both an index_line and an append for
                # the same fact.
                if content.rstrip("\n") in _index_lines():
                    log("  [skip duplicate index line]")
                    continue
                c = mem.append_index(content)
            elif kind in ("create", "update") and not is_index:
                c = (mem.create_topic_file if kind == "create"
                     else mem.update_topic_file)(
                    path, content,
                    **({"name": str(op.get("name", "")),
                        "description": str(op.get("description", "")),
                        "mtype": str(op.get("type", "reference")).lower(),
                        "origin_session_id": session_id}
                       if kind == "create" else {}))
                if kind == "create" and op.get("index_line"):
                    il = str(op["index_line"])
                    if il.rstrip("\n") not in _index_lines():
                        c = mem.append_index(il) or c
            else:
                log(f"  [rejected: {kind} on {path}]")
                continue
            log(f"  [{kind} {path}]")
            if c:
                check = c
        except ValueError as e:
            log(f"  [rejected: {e}]")
    return check


def curate(mem, transcript, session_id, chat_fn=None, log=print):
    msgs = [{"role": "system", "content": CURATION_SYSTEM},
            {"role": "user",
             "content": "Current MEMORY.md view:\n" + mem.load_index()
                        + "\n\nSession transcript:\n" + transcript
                        + "\n\nEmit the memory operations JSON now."}]
    ops = parse_fenced_list(chat(msgs, chat_fn))
    check = apply_ops(mem, ops, session_id, log)
    if check and check.startswith("Error:"):        # over-limit: one rewrite round
        log("  [over limit — rewrite round]")
        msgs += [{"role": "user",
                  "content": check + "\n\nCurrent MEMORY.md:\n"
                             + open(mem.index_path).read()
                             + "\nEmit ONE update op for MEMORY.md with the "
                               "full rewritten index."}]
        ops = parse_fenced_list(chat(msgs, chat_fn))
        for op in (ops or [])[:1]:
            if isinstance(op, dict):
                mem.rewrite_index(str(op.get("content", "")))


# ---------------------------------------------------------------------------
# The REPL.
# ---------------------------------------------------------------------------

def main():
    root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "./ccmem-demo")
    mem = ccmem.CCMemory(root)
    session_id = f"session-{len(mem.list_files())}-{os.getpid()}"
    print(f"memory dir: {mem.mem_dir}\nmodel: {MODEL} via {BASE_URL}")
    print("chat away. NOTHING IS SAVED MID-SESSION: /end runs the one "
          "curation round, writes memory, and exits; rerun on the same "
          "directory to see recall. /memory shows the index, /quit exits "
          "without saving\n")
    print("--- loaded memory index ---\n" + mem.load_index()
          + "\n---------------------------\n")
    history = []
    while True:
        try:
            user = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not user:
            continue
        if user == "/quit":
            return
        if user == "/memory":
            print(mem.load_index())
            if history:
                print("(nothing is written until /end runs the curation "
                      "round - so far this conversation exists only in "
                      "context)")
            continue
        if user == "/end":
            transcript = "\n".join(f"[{m['role']}] {m['content']}"
                                   for m in history) or "(empty session)"
            print("curating... (one more model call)", flush=True)
            curate(mem, transcript, session_id)
            print("saved. files now: " + ", ".join(mem.list_files() or ["none"]))
            return
        t0 = time.time()
        print("(waiting on the model; CCMEM_NO_THINK=1 makes "
              "reasoning models much faster. Ctrl-C aborts)", flush=True)
        reply = answer(mem, history, user)
        print(f"bot> ({time.time() - t0:.0f}s) " + reply.strip() + "\n")
        history += [{"role": "user", "content": user},
                    {"role": "assistant", "content": reply}]


if __name__ == "__main__":
    main()
