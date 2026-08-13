# memory

Per-question results and verification scripts for a controlled comparison of agent-memory
architectures: **files the model curates**, an **auto-mined structured store**, and a **trained
experience bank**.

This repository exists because published memory numbers are, at present, almost impossible to
compare. The same system has been reported at 84, 75.14 and 58.44 on the same benchmark depending
on who scored it and which question categories they counted; retrieval recall and answer accuracy
are quoted side by side as though they measured the same thing; and the reader and judge behind a
figure, which move it by more than most architectural choices do, usually go unstated. A number
published that way cannot be checked, only believed.

So the aim here is narrow and complete: **publish the evidence, not the conclusions.** Every
per-question row behind every table in
[*The Shapes of Agent Memory*](https://pinglin.tw/blog/the-shapes-of-agent-memory) is committed,
together with a script that recomputes each published figure from those rows and fails loudly if
it does not match. A reader can re-tally the scores, inspect what each system answered against the
gold answer, re-run the statistics under different assumptions, or discover that a number is wrong,
which has already happened twice and is recorded rather than quietly fixed. Nothing here is a
summary you have to trust.

---

## What was measured

One fixed open-weight model ([`Qwen3.6-35B-A3B-mxfp4`](https://huggingface.co/mlx-community/Qwen3.6-35B-A3B-mxfp4),
temperature 0) answers long-term-memory
benchmarks through one shared minimal agent loop. Only the memory layer changes between arms.

Architectures are named by what they do, not by who ships them: **file-based**, **place-organized**,
**entity-and-time**, and **hybrid** (place plus time). Where a named system is measured, it is named
and linked, and the description is drawn from its own documentation.

| Arm | Write path | Read path | What it is there to establish |
| --- | --- | --- | --- |
| **No-memory** | Nothing is stored | Nothing is retrieved | The floor. Sizes how much of each score is memory rather than the model, and proves refusing everything cannot game the judge. |
| **File-based** | An LLM curates a `MEMORY.md` index plus topic files | Index in context, then grep and read | One of the two architectures under test: memory as files the model decides what to write. |
| **Structured** | Atomic dated facts, embedded, no LLM on the write path | Ranked hybrid search | The other: memory as a store that keeps everything and ranks at read time. |
| **Oracle** | The file-based arm's store, unchanged | The entire memory directory in context, no tools | Splits the file-based arm's losses in two. With its whole store in context nothing saved can be missed, so what it still gets wrong was never written down, and what it recovers was saved but not found. |

The judge is identical across arms: a model judge plus a deterministic pass that re-classifies
refusals, so "I don't know" scores correct only when the answer genuinely was not in the history.

---

## Results

### LongMemEval-S, held out

[`scripts/longmemeval_s.py`](scripts/longmemeval_s.py)

356 non-tuning questions. Post-stratified means re-weighted to the full 500-question category
mix, so neither arm is flattered by the holdout's sample.

| Arm | Raw | Post-stratified |
| --- | ---: | ---: |
| No-memory | 0.0983 | 0.1095 |
| File-based | 0.4410 | 0.4491 |
| Oracle | 0.5618 | 0.5706 |
| **Structured** | **0.7303** | **0.7361** |

Paired difference, structured minus file-based: **+0.2869** post-stratified, McNemar discordant
134/31, exact p ≈ 1.8e-16.

**Where the gap comes from.** The oracle control answers with the file-based arm's *entire* store
in context and no search tools, so nothing saved can be missed. It lands between the two arms,
splitting the gap into **read-path friction +0.1215 (42%)** and **write-path loss +0.1654 (58%)**:
facts that were saved but not found, against facts never written down.

| Category | n | Structured | File-based |
| --- | ---: | ---: | ---: |
| Temporal-reasoning | 91 | 0.802 | 0.407 |
| Multi-session | 97 | 0.608 | 0.330 |
| Knowledge-update | 36 | 0.833 | 0.528 |
| Single-session-user | 52 | 0.923 | 0.673 |
| Single-session-assistant | 44 | 0.568 | 0.273 |
| Single-session-preference | 18 | 0.611 | 0.333 |
| **Abstention** | 18 | 0.778 | **0.889** |

Abstention, questions whose right answer is "I don't know", is the one category the file-based arm
wins here (0.889 against 0.778). It wins the equivalent category on LoCoMo too, where it is called
adversarial (0.508 against 0.246, with the no-memory floor scoring 1.000 by refusing everything).
The mechanism is the same in both places. Ranked retrieval nearly always surfaces *something*
plausible enough to tempt an answer, so the structured arm answers when it should have declined. A
curation-limited store often has nothing to offer, and the model then correctly says it does not
know. Eager retrieval needs an abstention discipline bolted on; sparse memory gets one for free.

**Cost**, dev-144, chat tokens per question. The two arms pay in different currencies, so
embedder tokens are never summed into the total.

| Chat tokens per question | File-based | Structured |
| --- | ---: | ---: |
| Writing memory (LLM curation) | 246,118 | 0 |
| Answering | 40,393 | 19,322 |
| **Total per question** | **286,512** | **19,322** |
| Total per *correct* answer | 665,447 | 27,013 |
| Embedder tokens (separate currency) | 0 | 107,797 |

The structured arm's zero on the write path is measured, not assumed: its ingest path only embeds
and upserts, with no model call in it, and a live query over the orchestration layer across the
whole ingest window found no model-invoking jobs running. Completion-token counts are lower bounds
throughout, since hidden reasoning tokens are not always reported, and the two currencies are never
summed or differenced: an embedder token and a reasoning token are not the same thing.

### LongMemEval-M

[`scripts/longmemeval_m.py`](scripts/longmemeval_m.py)

The long-haystack variant, ~500-session histories.

| System | Score | Questions |
| --- | ---: | --- |
| Hybrid (full agent loop) | 0.632 | 500 (complete set) |
| Place-organized (MemPalace, store-only) | 0.600 | 100 (pre-registered sample, seed 20260812) |
| Entity-and-time (Graphiti OSS) | None | Ingest alone ≈ 12 GPU-days, or ≈ $7,000 hosted |

Only the place-organized row is reproducible here. The two scored rows use different harnesses
*and* different samples, so the gap between them is directional; the store-only hybrid run on the
same sample was still going at publication.

### LoCoMo

[`scripts/locomo.py`](scripts/locomo.py)

300 questions, stratified across the 10 conversations. Published under both scopes because
whether the adversarial category counts is itself disputed between vendors.

| Arm | All | Excluding adversarial |
| --- | ---: | ---: |
| No-memory | 0.217 | 0.017 |
| File-based | 0.387 | 0.356 |
| **Structured** | **0.497** | **0.561** |

Structured minus file-based: **+0.110** all, **+0.205** excluding adversarial. Confidence
intervals resample whole conversations, not questions, because the questions cluster inside them:
structured, all questions, CI95 **[0.440, 0.553]**.

| Category | n | Structured | File-based |
| --- | ---: | ---: | ---: |
| Temporal | 62 | 0.694 | 0.306 |
| Temporal-inference | 54 | 0.519 | 0.259 |
| Open-domain | 61 | 0.656 | 0.410 |
| Single-hop | 62 | 0.371 | **0.435** |
| Adversarial | 61 | 0.246 | **0.508** |

Cost, ingest amortized per question: file-based **22.4k** chat tokens against structured
**11.6k**; per correct answer **58k** against **23k**.

### Store-only head-to-head

[`scripts/head_to_head.py`](scripts/head_to_head.py)

Every store stripped to its retrieval: its own top-20 for the same 1,540 non-adversarial LoCoMo
questions, one frontier reader, one frontier judge, every column produced by the same script.

| Store | LoCoMo | LongMemEval-S | Median context |
| --- | ---: | ---: | ---: |
| **Hybrid** | **0.7825** | **0.80** | 4,048 chars |
| Place-organized (MemPalace) | 0.7792 | 0.60 | 3,536 chars |
| Entity-and-time (Zep Cloud) | 0.7461 | Not run | 21,529 chars |
| Entity-and-time (Graphiti OSS) | 0.5338 | 0.35 | 7,857 chars |
| Entity-and-time (Graphiti, bge-m3) | 0.5286 | Not run | 7,896 chars |

Paired McNemar over the same questions:

| Pair | Discordant | χ² | Verdict |
| --- | ---: | ---: | --- |
| Hybrid vs Zep Cloud | 188/132 | 9.45 | Significant, p < 0.01 |
| Place-organized vs Zep Cloud | 174/123 | 8.42 | Significant, p < 0.01 |
| Hybrid vs Place-organized | 141/136 | 0.06 | **Not significant** |
| Graphiti OSS vs bge-m3 | 216/208 | 0.12 | Not significant |
| Every store vs either Graphiti | 442–485 / 80–115 | 191–276 | Significant |

Two findings worth stating against interest. The hybrid **ties a plain vector index** on LoCoMo,
so place-plus-time buys nothing there. And the **reader is worth more than most of the
architecture**: the same retrieval read by the local 35B instead of the frontier model scores
0.7130 against 0.7825, a 6.9-point swing with the store held byte-identical.

### Agentic benchmarks

[`scripts/agentic.py`](scripts/agentic.py)

Memory here is an experience bank: training-split episodes distilled into entries, retrieved
top-k into the acting model's prompt. Nothing is trained. "No memory" removes only the bank;
the harness scaffolding stays, so the ablation isolates retrieved memory.

| Actor | ALFWorld macro SR | WebShop score / SR |
| --- | ---: | ---: |
| Local 35B, no memory | 0.603 | 63.5 / 0.376 |
| Local 35B + bank | 0.645 | 66.0 / 0.418 |
| Frontier, no memory | 0.959 | 65.1 / 0.444 |
| Frontier + bank | 0.973 | 65.2 / 0.450 |
| MemHarness (GRPO-trained 7B), published | 0.852 / 0.859 OOD | 87.4 / 0.756 |

Paired ablations, memory rescued / cost:

| Column | Rescued | Cost | One-sided p | Two-sided p |
| --- | ---: | ---: | ---: | ---: |
| ALFWorld, 35B | 16 | 10 | 0.163 | 0.327 |
| ALFWorld, frontier | 2 | 0 | 0.250 | 0.500 |
| **WebShop, 35B** | **49** | **28** | **0.011** | **0.022** |
| WebShop, frontier | 33 | 30 | 0.401 | 0.801 |

One significant memory effect in the whole campaign, and it is the weak actor on WebShop. The law
that survives: **memory's value is inversely proportional to the actor's headroom.**

---

## How to reproduce

```bash
python3 scripts/verify_all.py     # standard library only, no install step
```

From a clean checkout:

```bash
git clone https://github.com/a40-labs/memory
cd memory
python3 scripts/verify_all.py          # every table above, rebuilt and checked
python3 scripts/longmemeval_s.py       # or run one benchmark at a time
```

No dependencies. Python 3.9+ (uses `math.comb`). Every script exits non-zero if any published
number fails to reproduce, so the results carry their own regression test: if a row is edited or a
statistic is implemented differently, the run goes red rather than silently disagreeing with the
post.

### What the data files contain

```
data/
  longmemeval_s/    holdout_{no_memory,file_based,structured,oracle}.json   356 rows each
                    dev144_{file_based,structured}.json                     the token ledger
  locomo/           {no_memory,file_based,structured}.json                  300 rows each
  longmemeval_m/    place_organized_sample100.json                          100 rows
  head_to_head/     {hybrid,place_organized,entity_time_cloud,...}.json     1,540 rows each
  agentic/          {alfworld,webshop}_{35b,frontier}_{baseline,memory}.json
```

Rows carry the per-question verdict, category, token counts, and (for the conversational arms)
the model's answer and the gold answer, so the grading can be re-examined and not merely
re-tallied. The head-to-head rows carry each question's retrieved-context *length* and verdict
rather than the context itself; see the provenance note below.

### What these artifacts can and cannot settle

They verify the **result**, not the **system**. A third party can re-tally every score, inspect
the answers, and re-run the statistics. Rebuilding the stores themselves needs the memory
services, which are not in this repo. Every row is a single run, and the frontier reader is not
bit-deterministic at temperature 0: identical re-runs drifted 0.3 to 0.4 points, so the fourth
decimal is noise.

---

## Provenance and credit

**Zep Cloud's column is Zep's data, not ours.** The retrieval contexts for that row are the
published outputs from [`getzep/zep-papers`](https://github.com/getzep/zep-papers), used verbatim
so their production system speaks for itself rather than through a proxy. This repo therefore
publishes only *measurements over* that data (per-question verdict, context length), never the
contexts themselves; fetch those from their repository under their license. Their published
LoCoMo result reproduces from their own artifacts, and 0.7461 is that same context re-scored
under this comparison's shared reader and judge, which is a different number for a stated reason,
not a contradiction of theirs.

**MemPalace** (MIT, [mempalace/mempalace](https://github.com/mempalace/mempalace)) is measured here
through its own retrieval, read by the shared reader. Worth stating plainly, since a comparison
should describe a rival accurately: it stores conversation text verbatim rather than extracting
facts, indexes it spatially (wings, rooms, drawers), and ships a temporal entity graph with
validity windows of its own. It also publishes its own per-question results and reproduction
commands, which is the standard this repo is trying to meet. Its published benchmark numbers are
retrieval recall (R@N), not QA accuracy, so they are not comparable to the answer-accuracy figures
above; the 0.7792 here is its retrieval read end-to-end by this comparison's reader and judge.

Also measured: [Graphiti](https://github.com/getzep/graphiti), and
[MemHarness](https://github.com/KnowledgeXLab/MemHarness), whose ALFWorld and WebShop figures are
quoted from its paper. Benchmarks: [LongMemEval](https://arxiv.org/abs/2410.10813),
[LoCoMo](https://arxiv.org/abs/2402.17753), [ALFWorld](https://alfworld.github.io/), and
[WebShop](https://webshop-pnlp.github.io/) (community mirror of the 1,000-product setting, the
official files being organization-locked).

## License

MIT, see [LICENSE](LICENSE). That covers the scripts and the result rows produced here. It does not
extend to third-party material this repository measures but does not contain: Zep Cloud's retrieval
contexts stay under [their repository's terms](https://github.com/getzep/zep-papers), and the
benchmarks themselves keep their own licenses.

## Caveats carried with every number

- **Single runs**, and the frontier reader is not bit-deterministic at temperature 0.
- **Graphiti-OSS is a best-effort parity configuration** of the open engine, not Zep's hosted product.
- **The file-based arm is a reconstruction** of a documented design, not a measurement of any
  shipping product; deviations are disclosed in the post, and several favour that arm.
- **One model family judged the main experiment.** An independent frontier judge later audited the
  head-to-head columns and preserved every ranking; the main experiment's judge remains unaudited.
- **Consolidation never ran during a scored question**, so the structured arm's numbers are a floor.
