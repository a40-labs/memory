# File-based agent memory: a reconstruction

`ccmem.py` is a dependency-free reconstruction of the file-based memory mechanism that shipping coding
agents use: a `MEMORY.md` index the model curates, topic files it writes and reads on demand, and no
retrieval beyond keeping the index in context and grepping the rest.

The best-documented instance of that mechanism is Claude Code's auto-memory, so this document is a
survey of it, and `ccmem.py` implements what the survey establishes. The original is closed-source and
cannot be lifted, so fidelity rests on traceability instead: **every claim below is labelled**
**[official]** = documented by Anthropic, **[corroborated]** = multiple independent community sources,
**[single-source]** = one analysis, **[rumor]** = leak-derived or unverified. A reader can therefore see
exactly how well-evidenced each behaviour is, rather than taking "faithful" on trust.

Compiled 2026-07-21 from official docs, release notes, GitHub issues, and community forensics. Anything
here may have changed since: the mechanism is under active development, and §3 is about the direction it
is moving.

## Using it

```python
from ccmem import CCMemory

mem = CCMemory("/some/dir")                     # creates <dir>/memory/
mem.append_index("- [Auth](auth.md) - tokens refresh every 15 min")
mem.create_topic_file("auth.md", "auth", "How auth works", "project", "Tokens refresh every 15 minutes.")

mem.load_index()        # the first 200 lines / 25KB, frontmatter stripped, overflow warning appended
mem.grep("refresh")     # literal or regex, bounded output, the only retrieval there is
mem.read_file("auth.md")  # injects a staleness notice if the file is aged
mem.post_write_check()  # the near-limit nag / over-limit error the harness issues after a write
```

Standard library only, no install step. The limits are module constants (`INDEX_MAX_LINES`,
`INDEX_MAX_BYTES`, `STALENESS_DAYS`) so they can be swept rather than hard-coded into an experiment.

---

## 0. Three systems, one comparison target

Anthropic ships three distinct memory mechanisms, and they are frequently conflated. This document describes the second one, which is what `ccmem.py` implements.

| System | What it is | Status |
| --- | --- | --- |
| CLAUDE.md instruction files | Hand-maintained instruction memory, loaded in full every session, hierarchical (managed policy → user → project → local), `@import` syntax to depth 4 | GA, longstanding [official] |
| **Claude Code auto-memory** | The automatic per-project memory directory: `MEMORY.md` index + topic files, model-curated | GA since v2.1.59, February 2026, on by default [official] |
| API `memory_20250818` tool / Managed Agents memory | A client-side file-operation tool (view / create / str_replace / insert / delete / rename on a `/memories` directory you host); Managed Agents mount a workspace store at `/mnt/memory` | Tool GA since 2025-09-29; Managed Agents store in public beta since 2026-04-23 [official] |

## 1. Auto-memory architecture

**Storage.** `~/.claude/projects/<project>/memory/`, where `<project>` derives from the git repository root, so all worktrees and subdirectories of one repo share one memory directory. Machine-local, never committed. Overridable via `autoMemoryDirectory` (v2.1.74+). Disable via `/memory` toggle (`autoMemoryEnabled: false`) or `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`. [official]

**Layout.** A flat directory: `MEMORY.md` (the index) plus freeform topic files (`debugging.md`, `api-conventions.md`, ...) created by the model as needed. [official]

**Loading.** Only the first **200 lines or 25KB of MEMORY.md, whichever comes first**, is loaded at session start; anything past the threshold is silently dropped. Topic files are **never** loaded at startup; the model reads them on demand with ordinary file tools. Since v2.1.211, YAML frontmatter and block HTML comments are stripped before the limit is measured. [official] Whether the injected index rides in the system prompt or as a user-role context message is unsettled (sources conflict); the docs state CLAUDE.md content arrives as a user message after the system prompt. [corroborated, placement unsettled]

**Writing.** Model-discretionary: "Claude decides what's worth remembering based on whether the information would be useful in a future conversation." [official] The empty-state nudge reads "When you notice a pattern worth preserving across sessions, save it here." [single-source] Topic files carry YAML frontmatter with `name`, `description`, and `metadata` including a **four-type taxonomy: `user` / `feedback` / `project` / `reference`**, plus the `originSessionId` of the writing session. [corroborated via the v2.1.88 source-map leak and file dumps] The leaked guidance explicitly excludes anything derivable from the code itself from being saved. [rumor, leak-derived]

**Harness-side machinery (not just prompts; must be reimplemented for fidelity):**

- **Post-write limit check** (v2.1.210+): after every MEMORY.md write the harness measures the file; near the limit it reminds the model to keep one line per entry, move detail to topic files, and merge or drop stale entries; over the limit the write succeeds but an error instructs the model to rewrite the index. [official]
- **Staleness injection**: reading an aged memory file injects a notice that the memory is N days old and is "a point-in-time observation, not live state", to be verified against the real code before acting. [single-source, consistent with leak analyses]
- **Overflow warning at load**: "Only the first 200 lines were loaded", with a recommendation to keep MEMORY.md a concise index. [single-source]
- **UX surfaces**: "Saved N memories" / "Recalled N memories" indicators; the `/memory` command lists and opens all memory files; `/context` shows what actually loaded. [official]

**Retrieval.** There is none beyond the index: no embeddings, no ranking, no search service. Recall = index lines in context + model-initiated grep/read over the directory. This is a deliberate design bet (one analysis calls it "retrieval, storage, and conversation unified in a single reasoning loop"). [corroborated]

**Subagents.** The main conversation's auto-memory is not loaded into subagents (forks excepted, which inherit parent context). Subagents can opt into their own separate memory directory via a `memory` field with project / local / user scopes. [official]

**Compaction interaction.** Memory files trivially survive `/compact` (they live on disk), but only the project CLAUDE.md is documented as re-injected post-compaction; MEMORY.md re-injection is undocumented. [official docs silent; fidelity gap to test]

## 2. Known failure modes

These are the failure modes the design implies, each reported by users. They are what any evaluation of this
shape should expect to measure:

1. **Index-horizon loss.** Months of use push older entries past the 200-line load horizon; they still exist on disk but are invisible unless the model happens to grep. [corroborated: GitHub #24474 class + Milvus analysis]
2. **Orphaned topic files.** The model writes topic files it never reads back, because nothing indexes them and only MEMORY.md auto-loads ("index or it doesn't exist"). GitHub issue #24474, closed as not-planned. A fact saved to an unindexed file is stored but practically unreachable. [official issue]
3. **Memory present but ignored.** Issues #43393 and #37847: saved feedback sits in context yet the mistake recurs; the docs themselves note memory is "context, not enforced configuration". [official issues]
4. **Context overhead.** Issue #63903 reports an 11k-16k-token memory preamble persisting even when disabled in some builds. [official issue, version-dependent]
5. **No semantic recall.** Grep-only retrieval misses paraphrase and cross-session joins. This is where a ranked-retrieval store differentiates itself. [corroborated]

## 3. Direction of travel: Anthropic is adding consolidation

The Managed Agents memory store gained **"Auto Dream"** (research preview, May 2026): a background pass that reviews past sessions, merges and deletes contradictory memories, rewrites vague time references to exact dates, and re-indexes under the line limit; leak analyses describe a four-phase orient → gather → consolidate → prune pipeline triggered when more than 24 hours and at least 5 sessions have passed since the last cleanup. [official for the feature's existence; phase/trigger details rumor-grade]

This matters for anyone comparing the shapes: background consolidation, temporal normalization, and contradiction resolution are exactly what structured stores run as background jobs, so the two shapes are converging and the comparison target moves. `ccmem.py` implements the **GA behaviour, without consolidation**, as the base configuration; a consolidation variant modelled on the documented trigger is the natural ablation on top of it.

## 4. The API memory tool (secondary reference)

For completeness, since a harness could equally be built on it: tool type `memory_20250818`, GA, six client-side commands (`view` with `view_range`, `create` as create-or-overwrite, `str_replace` with uniqueness errors, `insert` at line, `delete` root-protected, `rename` no-overwrite), your code executes them against storage you control with path-traversal protection. The API auto-injects an aggressive protocol prompt: "ALWAYS VIEW YOUR MEMORY DIRECTORY BEFORE DOING ANYTHING ELSE... ASSUME INTERRUPTION: your context window might be reset at any moment." Anthropic reports memory tool + context editing at +39% over baseline on an internal agentic-search eval (internal, unverifiable). [official]

## 5. Benchmark landscape: the field is open

**No published evaluation of Claude Code's memory system on any conversational-memory dataset existed** as of 2026-07-21 (searched: LongMemEval, LoCoMo, ConvoMem, MemBench). Any number measured against it is therefore the first of its kind, which raises rather than lowers the burden on the reconstruction it is measured through.

Vendor self-reported numbers on adjacent systems exist and should never be cross-compared with a number measured here, because the judge and protocol differ: Mem0 claims 94.4% on LongMemEval and 92.5% on LoCoMo, and an open-source agentmemory project measures 95.2% Recall@5 on LongMemEval-S for BM25+vector. LongMemEval-V2 (arXiv 2605.12493) is emerging as a successor benchmark. [all vendor/self-reported]

## 6. Fidelity checklist

What `ccmem.py` reimplements:

1. Per-question memory directory: `MEMORY.md` + topic files, per-repo-equivalent scoping.
2. Index-only preload: first 200 lines or 25KB, frontmatter stripped from the count, silent overflow with the overflow warning line.
3. Topic files load only via model-initiated read/grep, using ordinary file tools.
4. Write policy driven by the documented discretion phrasing and the four-type frontmatter taxonomy with `originSessionId`.
5. Post-write limit check with the compress-or-rewrite nag and over-limit error.
6. Staleness notice injected when reading aged memory files.
7. No consolidation in the base arm; optional Dream-modeled ablation (24h / 5-session trigger).
8. No memory inheritance into any sub-process.
9. Index injection placed to match whatever it is being compared against (a disclosed deviation: the original's exact placement is unsettled, and holding placement equal across arms removes a confound rather than adding one).
10. An open envelope check, below, rather than validation against the shipping CLI: a closed-product run is a snapshot of whatever version shipped that week, so it cannot serve as a reproducible reference.

**Deviations from the original, disclosed.** Real Claude Code edits MEMORY.md with freeform Write/Edit tools; this reconstruction is slightly more protective: curation-time index writes are line-ops only (`append`, `replace_line`), a full-index rewrite is permitted solely in the over-limit rewrite round, and any single rewrite that would drop the index below 50% of its current line count is rejected with a corrective message and one retry (added after a live curation round collapsed a 50-line index to a handful of lines). The A3 envelope check must therefore compare index-rewrite behavior explicitly: if the real CLI routinely performs legitimate large index rewrites that the guard would block, the guard threshold (or its existence) must be revisited before scored runs.

## 7. Open gaps the docs and community cannot answer

- The exact save-decision heuristics: only the documented phrasing is public, not the full instruction block.
- MEMORY.md re-injection behavior after compaction.
- Whether the index rides in the system prompt or a user-role message.
- Per-topic-file size limits (none documented).
- Whether any Dream-style consolidation is active in the GA CLI today.

These close empirically, and anyone with access to the shipping tool can close them: run the real CLI over a handful of
histories, inspect the resulting memory directories, and compare save rates, index shapes, and read patterns against
what this reconstruction produces. Where they diverge, this document is wrong and should be corrected. That check is
published here precisely so it can be run against, rather than asserted.

---

## Sources

Official: code.claude.com/docs/en/memory.md, /sessions.md, /sub-agents.md; platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool.md, /managed-agents/memory; anthropic.com/news/context-management. GitHub issues: anthropics/claude-code #24474, #23544, #25318, #37847, #43393, #63903. Community: dbreunig.com (system-prompt teardown), giuseppegurgone.com/claude-memory, readysolutions.ai (auto-memory forensics), shloked.com (files-vs-embeddings analysis), milvus.io blog (memsearch critique), mindstudio.ai + tylerfolkman + artemxtech (v2.1.88 source-map leak analyses), zep-us/claude-system-prompt, mem0.ai benchmark blog, rohitg00/agentmemory comparison.
