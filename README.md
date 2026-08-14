# memory

Per-question results and verification scripts for a controlled comparison of agent-memory
architectures: **files the model curates**, an **auto-mined structured store**, and a **trained
experience bank**.

This repository exists because published memory numbers are hard to compare. One system's LoCoMo
result has appeared as **84**, **58.44** and **75.14**: Zep reported 84; mem0's CTO
[filed an issue](https://github.com/getzep/zep-papers/issues/5) arguing the correct figure was
58.44 (the adversarial category counted in the numerator but excluded from the denominator); Zep
[re-ran with the error fixed and reported 75.14](https://blog.getzep.com/lies-damn-lies-statistics-is-mem0-really-sota-in-agent-memory/),
noting mem0's own number has been [cited at both 67 and 92.5](https://arxiv.org/abs/2504.19413).
One benchmark, one system, a 25-point spread, and the memory architecture never changed. Two more
habits compound it: **retrieval recall and answer accuracy quoted side by side** as if they
measured the same thing, and **the reader and judge behind a figure left unstated**, though
swapping the reader alone moves a score by
[more than the architecture does](#store-only-head-to-head). A number published without its frame
cannot be checked, only believed.

So the aim here is narrow and complete: **publish the evidence, not the conclusions.** Every
per-question row behind every table in
[*The Shapes of Agent Memory*](https://pinglin.tw/blog/the-shapes-of-agent-memory) is committed,
with a script that recomputes each published figure from those rows and fails loudly on any
mismatch. A reader can re-tally the scores, inspect answers against gold, re-run the statistics
under different assumptions, or discover that a number is wrong, which has already happened twice
and is recorded rather than quietly fixed.

## TL;DR

The same findings as the post, each with the figure it rests on and the section that rebuilds it.

- **The structured store beats files on accuracy and on cost at once.** +28.7 points on held-out
  LongMemEval-S questions (0.7361 against 0.4491, post-stratified), at 19.3k reasoning tokens per
  question against 286.5k. [Details](#longmemeval-s-held-out)
- **Files win where the right answer is "I don't know".** Abstention 0.889 against 0.778, and the
  equivalent LoCoMo category 0.508 against 0.246: eager retrieval needs an abstention discipline
  that sparse memory gets for free. [Details](#locomo)
- **Against interest: the hybrid ties a plain vector index** on LoCoMo (χ² = 0.06), so
  place-plus-time buys nothing there. On the long-haystack benchmark the same pair separates:
  hybrid 0.750 against 0.600, paired on one pre-registered sample, p = 0.008. Structure pays
  where histories are long, and no single benchmark ranks memory systems.
  [Details](#longmemeval-m)
- **The ruler can outweigh the architecture.** Identical retrieval read by `gpt-4o-mini` instead of the local
  35B scores 0.7825 against 0.7130, a bigger move than any difference between the three stores that work
  on LoCoMo (0.3 to 3.6 points); on long-haystack LongMemEval-M the same store pair separates by 15, so
  which factor dominates depends on the benchmark. Numbers do not travel across protocols.
  [Details](#store-only-head-to-head)
- **On agentic benchmarks, memory earns in proportion to the actor's headroom.** Real points for a
  weak actor (WebShop success +4.2, the agentic benchmarks' only significant memory-ablation effect), noise at
  the frontier, and a bar that only training reaches: even the trained system's own released bank,
  injected into its own frozen actor, is a null. [Details](#agentic-benchmarks)

---

## What was measured

One fixed open-weight model ([`Qwen3.6-35B-A3B-mxfp4`](https://huggingface.co/mlx-community/Qwen3.6-35B-A3B-mxfp4),
temperature 0) answers long-term-memory benchmarks through one shared minimal agent loop. Only
the memory layer changes between arms.

Architectures are named by what they do, not by who ships them: **file-based**, **place-organized**,
**entity-and-time**, and **hybrid** (place plus time). Where a named system is measured, it is named
and linked, and the description is drawn from its own documentation.

| Arm | Write path | Read path | What it is there to establish |
| --- | --- | --- | --- |
| **No-memory** | Nothing is stored | Nothing is retrieved | The floor. Sizes how much of each score is memory rather than the model, and proves refusing everything cannot game the judge. |
| **File-based** | An LLM curates a `MEMORY.md` index plus topic files | Index in context, then grep and read | One of the two architectures under test: memory as files the model decides what to write. |
| **Structured** | Atomic dated facts, embedded, no LLM on the write path | Ranked hybrid search | The other: memory as a store that keeps everything and ranks at read time. |
| **Oracle** | The file-based arm's store, unchanged | The entire memory directory in context, no tools | Splits the file-based arm's losses in two. With its whole store in context nothing saved can be missed, so what it still gets wrong was never written down, and what it recovers was saved but not found. |

Two of these arms were built for this study, so they are specified here rather than drawn from
anyone's documentation:

- **Structured (the hybrid).** A place-organized write path files dated atomic facts with no LLM
  at ingest; validity windows, borrowed from the entity-and-time lineage, let a new fact close an
  old one's rather than compete with it at recall; and an associative graph learned from which
  places co-occur in retrievals beyond chance lets recall reach items the query never ranked. The
  place-plus-time combination is not unique
  ([MemPalace](https://github.com/mempalace/mempalace) ships validity windows too); the
  usage-learned layer is what differs. It deliberately omits the graph lineage's expensive half:
  no LLM at ingest, so no entity resolution and no maintained summaries.
- **File-based.** A reconstruction of a shipping coding agent's auto-memory (a `MEMORY.md` index
  over model-curated topic files), not a reimplementation written to lose. The original is
  closed-source, so [`systems/file-based/`](systems/file-based) publishes the per-claim sourced
  survey it is built from, the mechanism itself, its tests, and a toy chatbot that runs the loop
  live, plus an open envelope check for anyone with the real tool to falsify it.

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

Abstention, questions whose right answer is "I don't know", is the one category the file-based
arm wins, both here (0.889 vs 0.778) and in LoCoMo's adversarial category (0.508 vs 0.246). Same
mechanism both times: ranked retrieval nearly always surfaces *something* plausible enough to
tempt an answer, while a curation-limited store often has nothing to offer, so the model correctly
declines. Eager retrieval needs an abstention discipline bolted on; sparse memory gets one free.

**Cost**, dev-144, chat tokens per question. The two arms pay in different currencies, so
embedder tokens are never summed into the total.

| Chat tokens per question | File-based | Structured |
| --- | ---: | ---: |
| Writing memory (LLM curation) | 246,118 | 0 |
| Answering | 40,393 | 19,322 |
| **Total per question** | **286,512** | **19,322** |
| Total per *correct* answer | 665,447 | 27,013 |
| Embedder tokens (separate currency) | 0 | 107,797 |

The structured arm's zero on the write path is measured, not assumed: its ingest only embeds and
upserts, and a live query across the ingest window found no model-invoking jobs. Completion-token
counts are lower bounds throughout (hidden reasoning tokens are not always reported), and the two
currencies are never summed: an embedder token and a reasoning token are not the same thing.

### LongMemEval-M

[`scripts/longmemeval_m.py`](scripts/longmemeval_m.py)

The long-haystack variant, ~500-session histories. Both store-only arms ran on the same
pre-registered 100-question sample (seed 20260812): one retrieval and one reader call each,
official per-question-type judging, so the comparison is paired.

| System | Score | Questions |
| --- | ---: | --- |
| **Hybrid (store-only)** | **0.750** | 100 (pre-registered sample, seed 20260812) |
| Place-organized (MemPalace, store-only) | 0.600 | The same 100 |
| Hybrid (full agent loop) | 0.632 | 500 (complete set; different harness, directional only) |
| Entity-and-time (Graphiti OSS) | None | Ingest alone ≈ 12 GPU-days, or ≈ $7,000 hosted |

Paired McNemar on the store-only pair: rescued 22 / lost 7, exact two-sided **p = 0.008**. The
+15-point gap clears the sample's CI95 of ±10, so the question LoCoMo left open is answered:
place-plus-time buys nothing at short histories, and pays decisively at long ones. The hybrid
swept the single-session categories (14/14 and 11/11) and won on multi-session content, exactly
where structure should pay.

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
questions, one shared reader and judge (`gpt-4o-mini`, the model the graph vendor's own published numbers
were scored with), every store's row produced by the same script.

| Store | LoCoMo | LongMemEval-S | Median context |
| --- | ---: | ---: | ---: |
| **Hybrid** | **0.7825** | **0.80** † | 4,048 chars |
| Place-organized (MemPalace) | 0.7792 | 0.60 † | 3,536 chars |
| Entity-and-time (Zep Cloud) | 0.7461 | Not run | 21,529 chars |
| Entity-and-time (Graphiti OSS) | 0.5338 | 0.35 | 7,857 chars |
| Entity-and-time (Graphiti, bge-m3) | 0.5286 | Not run | 7,896 chars |

† The LongMemEval-S column's Graphiti row (0.35) and the agent-loop row it is compared against
(0.72) reproduce from published rows (`scripts/longmemeval_s.py`); the hybrid store-only 0.80 and
MemPalace 0.60 do not, because those runs never persisted per-question contexts, and re-deriving
contexts now would pair answers with retrievals that did not produce them. Both scores carry that
caveat wherever they appear.

Paired McNemar over the same questions:

| Pair | Discordant | χ² | Verdict |
| --- | ---: | ---: | --- |
| Hybrid vs Zep Cloud | 188/132 | 9.45 | Significant, p < 0.01 |
| Place-organized vs Zep Cloud | 174/123 | 8.42 | Significant, p < 0.01 |
| Hybrid vs Place-organized | 141/136 | 0.06 | **Not significant** |
| Graphiti OSS vs bge-m3 | 216/208 | 0.12 | Not significant |
| Every store vs either Graphiti | 442–485 / 80–115 | 191–276 | Significant |

Two findings worth stating against interest. The first: the hybrid **ties a plain vector index** on
LoCoMo, so place-plus-time buys nothing there.

The second is that **on this benchmark the reader outweighs every architectural difference among
the stores that work** (the ordering inverts on [LongMemEval-M](#longmemeval-m), where the same
hybrid-versus-flat pair separates by 15 points). Reading byte-identical retrieval with a weaker
model scores 0.7130 instead of 0.7825. Set that swing beside the architectural gaps it is
competing with:

| What changed | From | To | Points lost |
| --- | --- | --- | ---: |
| **The reader**, same retrieval | **`gpt-4o-mini` 0.7825** | **`Qwen3.6-35B-A3B-mxfp4` 0.7130** | **6.9** |
| The store, same reader | Hybrid 0.7825 | Place-organized 0.7792 | 0.3 |
| The store, same reader | Hybrid 0.7825 | Zep Cloud 0.7461 | 3.6 |
| The store, same reader | Place-organized 0.7792 | Zep Cloud 0.7461 | 3.3 |
| The embedder inside one store | Graphiti OSS 0.5338 | Graphiti bge-m3 0.5286 | 0.5 |
| The store, the *cheapest* route into the open engine | Zep Cloud 0.7461 | Graphiti OSS 0.5338 | 21.2 |

Read a row as: hold everything else fixed, change this one thing, and the score falls by that much.
Changing the reader costs more than changing between any two of the three stores that work. The only
thing that costs more is dropping to Graphiti OSS, and the last row is the cheapest route there: the
other five store-to-Graphiti pairings cost 21.8 to 25.4. Three things sit behind these numbers and should not be
conflated:

- **The reader** answers from whatever context it receives. Identical for every store, which is
  what makes the store comparison valid; swapping it is the 6.9-point row.
- **The extractor** runs inside the store at ingest and decides what is ever written down. Part of
  the store being compared, not of the harness around it.
- **The pipeline** is what the extractor runs in: how many passes per message, what it resolves,
  what it keeps.

So which explains the 21 points between Zep Cloud and Graphiti OSS? Not the reader: it is the same
model for both. Not the extraction model's capability either, since the open engine ran with the same
class of extractor the vendor's published numbers were built with and still landed at 0.53. What is
left is everything the hosted service does around that extractor, and that is where this comparison
reaches the edge of what it can honestly claim. `head_to_head.py` recomputes the ranking itself, so
the ordering is derived rather than quoted.

**What this study cannot see.** Zep Cloud is a hosted product, and its row here is Zep's own published
context. What is measurable is what reaches the reader on each side, not the ingestion or ranking that
produced it. The open engine's contexts are visibly thinner, carrying fewer stored facts and much shorter
entity summaries, but that is a property of the released artifacts rather than a description of anyone's
internals. One known difference does not favour Zep: their published ingestion reads a `blip_captions`
key where the LoCoMo field is `blip_caption`
([zep-papers#9](https://github.com/getzep/zep-papers/issues/9)), dropping image captions that the runs
here kept.

None of this suggests their published number is wrong. It reproduces from their own released grades, and
their contexts re-scored under this study's reader and judge give 0.7461, within a point of their
published 75.14. The 21-point gap is real and reproducible; its cause is not observable from
outside. Read "the hosted pipeline" as a label for the unobserved remainder, not a mechanism
verified here.

### Cross-family judge audit

[`scripts/judge_audit.py`](scripts/judge_audit.py)

The head-to-head's judge could favour answers that resemble its own style, so an independent
frontier judge from a different vendor (`claude-sonnet-5`) re-judged all five stores' published
responses on a frozen 100-question sample. Recomputed here from the per-question rows: the
independent judge grades a uniform 4 to 7 points stricter, agreement is 0.91 to 0.96 with kappa
0.82 to 0.89 and a 0.05 agreement spread (no arm-differential bias), and **every ranking is
preserved**, with the hybrid's win over Zep Cloud significant under the independent judge alone
(21/8, p = 0.024) and the hybrid-MemPalace tie holding. The level shifts; the order does not.

### Agentic benchmarks

[`scripts/agentic.py`](scripts/agentic.py)

Memory here is an experience bank: training-split episodes distilled into entries, retrieved
top-k into the acting model's prompt. Nothing is trained. "No memory" removes only the bank;
the harness scaffolding stays, so the ablation isolates retrieved memory.

| Actor | ALFWorld macro SR | WebShop score / SR |
| --- | ---: | ---: |
| Local 35B, no memory | 0.603 | 63.5 / 0.376 |
| Local 35B + bank | 0.645 | 66.0 / 0.418 |
| Frontier actor (`claude-sonnet-5`), no memory | 0.959 | 65.1 / 0.444 |
| Frontier actor + bank | 0.973 | 65.2 / 0.450 |
| MemHarness (GRPO-trained 7B), published | 0.852 / 0.859 OOD | 87.4 / 0.756 |

Paired ablations, memory rescued / cost:

| Column | Rescued | Cost | One-sided p | Two-sided p |
| --- | ---: | ---: | ---: | ---: |
| ALFWorld, 35B | 16 | 10 | 0.163 | 0.327 |
| ALFWorld, frontier | 2 | 0 | 0.250 | 0.500 |
| **WebShop, 35B** | **49** | **28** | **0.011** | **0.022** |
| WebShop, frontier | 33 | 30 | 0.401 | 0.801 |

One significant memory effect in the whole campaign, and it is the weak actor on WebShop.

The complementary probe runs the other direction: hold the *trained* system's frozen 7B actor
fixed on WebShop (full catalog, n=500) and swap what its memory holds.

| Arm (frozen trained 7B) | Score | SR |
| --- | ---: | ---: |
| No memory | 71.0 | 0.300 |
| Its own released bank, its own retrieval semantics | 69.5 | 0.306 |
| The same bank, situation-match retrieval | 69.1 | 0.298 |

A three-way statistical tie (all pairwise two-sided p ≥ 0.52; every delta ≤ 1.9 points): at a
frozen actor, not even the trained system's own bank helps, under either retrieval semantics. Its
published margin is carried by the training, not by the bank content or retrieval mechanics,
which is the untrained-side confirmation of its own ablation showing raw replay *hurts* the
trained policy. The law that survives the whole campaign: **memory's value is inversely
proportional to the actor's headroom.**

---

## How to reproduce

```bash
git clone https://github.com/a40-labs/memory
cd memory
python3 scripts/verify_all.py          # every table above, rebuilt and checked
python3 scripts/longmemeval_s.py       # or run one benchmark at a time
python3 systems/file-based/test_ccmem.py   # the file-based mechanism against its survey
```

No install step and no dependencies: standard library only, Python 3.9+. Every script exits
non-zero if any published number fails to reproduce, so the results carry their own regression
test. [`systems/file-based/`](systems/file-based) also ships a toy chatbot that runs the
file-based loop live against any OpenAI-compatible endpoint: chat, curate at session end, recall
in a fresh session.

### What the data files contain

```
data/
  longmemeval_s/    holdout_{no_memory,file_based,structured,oracle}.json   356 rows each
                    dev144_{file_based,structured}.json                     the token ledger
                    {graphiti_oss,hybrid_agentloop}_sample100.json          the store-only sample
  locomo/           {no_memory,file_based,structured}.json                  300 rows each
  longmemeval_m/    {hybrid_storeonly,place_organized}_sample100.json       100 paired rows each
  head_to_head/     {hybrid,place_organized,entity_time_cloud,...}.json     1,540 rows each
  agentic/          {alfworld,webshop}_{35b,frontier}_{baseline,memory}.json
                    webshop_frozen7b_{baseline,their_bank,situation_match}.json   the store swap
                    alfworld_frozen7b_baseline.json                         the cross-stack disclosure
judge_audit/        sonnet_rows.json    all five stores under an independent frontier judge
systems/
  file-based/       ccmem.py          the file-based arm's mechanism, stdlib only
                    README.md         the per-claim sourced survey it implements
                    test_ccmem.py     22 tests pinning the mechanism to the survey
                    chatbot.py        a toy chatbot running the whole loop live
```

Rows carry the per-question verdict, category, token counts, and (for the conversational arms)
the model's answer and the gold answer, so the grading can be re-examined and not merely
re-tallied. The head-to-head rows carry each question's retrieved-context *length* and verdict
rather than the context itself; see the provenance note below.

### What these artifacts can and cannot settle

They verify the **result**, not the **system**. A third party can re-tally every score, inspect the
answers, and re-run the statistics. Every row is a single run, and the hosted reader is not
bit-deterministic at temperature 0: identical re-runs drifted 0.3 to 0.4 points, so the fourth
decimal is noise.

Rebuilding the systems is a separate matter. The structured, place-organized and entity-and-time
stores need memory services that are not in this repo. The file-based arm's mechanism is published
in `systems/file-based/`: enough to inspect or re-implement how memory was written, capped, aged
and searched, but the benchmark runner and its curation prompt stay unpublished: an auditable
specification of the arm, not a turnkey reproduction.

---

## Provenance and credit

**Zep Cloud's row is Zep's data, not ours.** Its retrieval contexts are the published outputs
from [`getzep/zep-papers`](https://github.com/getzep/zep-papers), used verbatim so their
production system speaks for itself. This repo publishes only *measurements over* that data
(per-question verdict, context length), never the contexts; fetch those from their repository
under their license. Their published result reproduces from their own artifacts; 0.7461 is the
same context re-scored under this comparison's shared reader and judge, a different number for a
stated reason rather than a contradiction of theirs.

**MemPalace** (MIT, [mempalace/mempalace](https://github.com/mempalace/mempalace)) is measured
through its own retrieval, read by the shared reader. Stated plainly, because a comparison should
describe a rival accurately: it stores conversation text verbatim, indexes it spatially (wings,
rooms, drawers), and ships a temporal entity graph with validity windows of its own. It publishes
per-question results and reproduction commands, the standard this repo is trying to meet. Its own
published numbers are retrieval recall (R@N), not QA accuracy; the 0.7792 here is its retrieval
read end-to-end by this comparison's reader and judge.

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

- **Single runs**, and the hosted reader is not bit-deterministic at temperature 0.
- **Graphiti OSS is a best-effort parity configuration** of the vendor's open-source engine, not their hosted product.
- **The file-based arm is a reconstruction** of a documented design, not a measurement of any
  shipping product; deviations are disclosed in the post, and several favour that arm.
- **One model family judged the main experiment.** An independent frontier judge audited the
  head-to-head stores and preserved every ranking (`scripts/judge_audit.py` recomputes it); the
  main experiment's file-versus-structured judge remains unaudited.
- **Consolidation never ran during a scored question**, so the structured arm's numbers are a floor.
