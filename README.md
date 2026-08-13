# memory

Per-question results and verification scripts for a controlled comparison of agent-memory
architectures: **files the model curates**, an **auto-mined structured store**, and a **trained
experience bank**.

Every number published in
[*The Shapes of Agent Memory*](https://pinglin.tw/blog/the-shapes-of-agent-memory) is recomputed
here from the rows it came from. Nothing in this repo is a summary you have to trust: run
`python3 scripts/verify_all.py` and the tables in the post are rebuilt in front of you, each one
checked against the figure it is published under.

```
python3 scripts/verify_all.py     # standard library only, no install step
```

---

## What was measured

One fixed open-weight model ([`Qwen3.6-35B-A3B-mxfp4`](https://huggingface.co/mlx-community/Qwen3.6-35B-A3B-mxfp4),
temperature 0) answers long-term-memory
benchmarks through one shared minimal agent loop. Only the memory layer changes between arms.

Architectures are named by what they do, not by who ships them: **file-based**, **place-organized**,
**entity-and-time**, and **hybrid** (place plus time). Where a named system is measured, it is named
and linked, and the description is drawn from its own documentation.

| Arm | Write path | Read path |
| --- | --- | --- |
| **no-memory** | nothing is stored | nothing is retrieved (the floor) |
| **file-based** | an LLM curates a `MEMORY.md` index plus topic files | index in context, then grep and read |
| **structured** | atomic dated facts, embedded, no LLM on the write path | ranked hybrid search |
| **oracle** | the file-based arm's store, unchanged | the entire memory directory in context, no tools |

The judge is identical across arms: a model judge plus a deterministic pass that re-classifies
refusals, so "I don't know" scores correct only when the answer genuinely was not in the history.

---

## Results

### LongMemEval-S, held out (`scripts/longmemeval_s.py`)

356 non-tuning questions. Post-stratified means re-weighted to the full 500-question category
mix, so neither arm is flattered by the holdout's sample.

| Arm | Raw | Post-stratified |
| --- | ---: | ---: |
| no-memory | 0.0983 | 0.1095 |
| file-based | 0.4410 | 0.4491 |
| oracle | 0.5618 | 0.5706 |
| **structured** | **0.7303** | **0.7361** |

Paired difference, structured minus file-based: **+0.2869** post-stratified, McNemar discordant
134/31, exact p ≈ 1.8e-16.

**Where the gap comes from.** The oracle control answers with the file-based arm's *entire* store
in context and no search tools, so nothing saved can be missed. It lands between the two arms,
splitting the gap into **read-path friction +0.1215 (42%)** and **write-path loss +0.1654 (58%)**:
facts that were saved but not found, against facts never written down.

| Category | n | Structured | File-based |
| --- | ---: | ---: | ---: |
| temporal-reasoning | 91 | 0.802 | 0.407 |
| multi-session | 97 | 0.608 | 0.330 |
| knowledge-update | 36 | 0.833 | 0.528 |
| single-session-user | 52 | 0.923 | 0.673 |
| single-session-assistant | 44 | 0.568 | 0.273 |
| single-session-preference | 18 | 0.611 | 0.333 |
| **abstention** | 18 | 0.778 | **0.889** |

Abstention is the one category the file-based arm wins, on both benchmarks: a store that
remembers less over-answers less.

**Cost**, dev-144, chat tokens per question. The two arms pay in different currencies, so
embedder tokens are never summed into the total.

| Chat tokens per question | File-based | Structured |
| --- | ---: | ---: |
| writing memory (LLM curation) | 246,118 | 0 (verified) |
| answering | 40,393 | 19,322 |
| **total per question** | **286,512** | **19,322** |
| total per *correct* answer | 665,447 | 27,013 |
| embedder tokens (separate currency) | 0 | 107,797 |

### LoCoMo (`scripts/locomo.py`)

300 questions, stratified across the 10 conversations. Published under both scopes because
whether the adversarial category counts is itself disputed between vendors.

| Arm | All | Excluding adversarial |
| --- | ---: | ---: |
| no-memory | 0.217 | 0.017 |
| file-based | 0.387 | 0.356 |
| **structured** | **0.497** | **0.561** |

Structured minus file-based: **+0.110** all, **+0.205** excluding adversarial. Confidence
intervals resample whole conversations, not questions, because the questions cluster inside them:
structured, all questions, CI95 **[0.440, 0.553]**.

| Category | n | Structured | File-based |
| --- | ---: | ---: | ---: |
| temporal | 62 | 0.694 | 0.306 |
| temporal-inference | 54 | 0.519 | 0.259 |
| open-domain | 61 | 0.656 | 0.410 |
| single-hop | 62 | 0.371 | **0.435** |
| adversarial | 61 | 0.246 | **0.508** |

Cost, ingest amortized per question: file-based **22.4k** chat tokens against structured
**11.6k**; per correct answer **58k** against **23k**.

### LongMemEval-M (`scripts/longmemeval_m.py`)

The long-haystack variant, ~500-session histories.

| System | Score | Questions |
| --- | ---: | --- |
| hybrid (full agent loop) | 0.632 | 500 (complete set) |
| place-organized (MemPalace, store-only) | 0.600 | 100 (pre-registered sample, seed 20260812) |
| entity-and-time (Graphiti OSS) | none | ingest alone ≈ 12 GPU-days, or ≈ $7,000 hosted |

Only the place-organized row is reproducible here. The two scored rows use different harnesses
*and* different samples, so the gap between them is directional; the store-only hybrid run on the
same sample was still going at publication.

### Store-only head-to-head (`scripts/head_to_head.py`)

Every store stripped to its retrieval: its own top-20 for the same 1,540 non-adversarial LoCoMo
questions, one frontier reader, one frontier judge, every column produced by the same script.

| Store | LoCoMo | LongMemEval-S | Median context |
| --- | ---: | ---: | ---: |
| **hybrid** | **0.7825** | **0.80** | 4,048 chars |
| place-organized (MemPalace) | 0.7792 | 0.60 | 3,536 chars |
| entity-and-time (Zep Cloud) | 0.7461 | not run | 21,529 chars |
| entity-and-time (Graphiti OSS) | 0.5338 | 0.35 | 7,857 chars |
| entity-and-time (Graphiti, bge-m3) | 0.5286 | not run | 7,896 chars |

Paired McNemar over the same questions:

| Pair | Discordant | χ² | Verdict |
| --- | ---: | ---: | --- |
| hybrid vs Zep Cloud | 188/132 | 9.45 | significant, p < 0.01 |
| place-organized vs Zep Cloud | 174/123 | 8.42 | significant, p < 0.01 |
| hybrid vs place-organized | 141/136 | 0.06 | **not significant** |
| Graphiti OSS vs bge-m3 | 216/208 | 0.12 | not significant |
| every store vs either Graphiti | 442–485 / 80–115 | 191–276 | significant |

Two findings worth stating against interest. The hybrid **ties a plain vector index** on LoCoMo,
so place-plus-time buys nothing there. And the **reader is worth more than most of the
architecture**: the same retrieval read by the local 35B instead of the frontier model scores
0.7130 against 0.7825, a 6.9-point swing with the store held byte-identical.

### Agentic benchmarks (`scripts/agentic.py`)

Memory here is an experience bank: training-split episodes distilled into entries, retrieved
top-k into the acting model's prompt. Nothing is trained. "No memory" removes only the bank;
the harness scaffolding stays, so the ablation isolates retrieved memory.

| Actor | ALFWorld macro SR | WebShop score / SR |
| --- | ---: | ---: |
| local 35B, no memory | 0.603 | 63.5 / 0.376 |
| local 35B + bank | 0.645 | 66.0 / 0.418 |
| frontier, no memory | 0.959 | 65.1 / 0.444 |
| frontier + bank | 0.973 | 65.2 / 0.450 |
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

## Reproducing

```bash
git clone https://github.com/a40-labs/memory
cd memory
python3 scripts/verify_all.py          # every table above, rebuilt and checked
python3 scripts/longmemeval_s.py       # or run one at a time
```

No dependencies. Python 3.9+ (uses `math.comb`). Every script exits non-zero if any published
number fails to reproduce, so it works as a regression test on the results themselves.

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

## Caveats carried with every number

- **Single runs**, and the frontier reader is not bit-deterministic at temperature 0.
- **Graphiti-OSS is a best-effort parity configuration** of the open engine, not Zep's hosted product.
- **The file-based arm is a reconstruction** of a documented design, not a measurement of any
  shipping product; deviations are disclosed in the post, and several favour that arm.
- **One model family judged the main experiment.** An independent frontier judge later audited the
  head-to-head columns and preserved every ranking; the main experiment's judge remains unaudited.
- **Consolidation never ran during a scored question**, so the structured arm's numbers are a floor.
