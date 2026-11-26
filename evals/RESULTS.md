# Evaluation results

Dataset v2: 38 questions over 3 repos pinned to exact commits (see `README.md` for method). Model:
`gemini-3.5-flash-lite` on the Gemini free tier, one run per variant. Cost lines use the model's published paid
price ($0.30 per million input tokens, $2.50 per million output tokens), so they are a what-if: the runs cost nothing.

## Read this first

- **One run per variant, 38 questions.** A single question is 2.6 points and 4 to 7 questions changed outcome between
  runs, in both directions. The pass-rate gain is suggestive, not proven. I did not measure run-to-run noise.
- **The mechanical gains are firm** (questions ending with no answer, repeated searches, tokens): they have clear
  causes visible in the traces.
- **Two v2 questions are unanswered**: the free tier's daily request quota for this model ran out
  (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`). They are left out of comparisons, not counted as failures.
- **The final index was not re-run end to end.** The v2 run used an index that embeds 1500 characters and tags only the
  first window of a long function. Tagging every window and embedding 1000 characters came afterwards and are
  validated by the retrieval measurements below, which use no model. An end-to-end re-run waits for quota.
- **The questions were written by the person who built the system**, from the code at the pinned commits. This is not
  a neutral benchmark.

## Three runs

Each column uses that run's own answered questions. The paired comparison below uses the same 36 for both sides.

| | baseline | v1: loop fixes | v2: + retrieval |
|---|---|---|---|
| Questions answered | 38 | 38 | 36 (2 hit the quota) |
| Passed | 32/38 (84%) | 33/38 (87%) | 33/36 answered (92%) |
| Questions that ended with no answer | 3 | 2 | **0** |
| Repeated tool calls | 19 | 6 | **4** |
| Tokens in per question | 22,155 | 17,146 | **13,789** |
| Cost per question (paid-tier price) | $0.0073 | $0.0057 | **$0.0047** |
| Average cited span | 11.9 lines | 7.8 | **5.2** |
| Negative questions correct ("not in this repo") | 3/6 | 5/6 | 4/5 answered |
| Citations the agent had actually read | 98% | 100% | 100% |
| Citation validity | 100% | 100% | 100% |
| Steps per question | 3.8 | 3.3 | 3.3 |
| Latency p50 | 10.0s | 7.9s | 4.0s (mostly provider load) |

On the 36 questions answered in both the baseline and v2: **83% to 92%** passed (5 questions fixed, 2 regressed), tokens
per question down 39%, cost per question down 36%.

### What each step changed

- **baseline** is `main` before the evaluation existed. Reading its 9 failures: 3 questions repeated near-identical
  searches 7 to 8 times and ended with an **empty answer** (about a third of all tokens), 2 correct "not in this repo"
  answers cited lines the agent never read because our own citation check demanded a citation, and **4 were my
  scoring or ground-truth mistakes** (fixed in dataset v2; the stored baseline answers were re-scored, not re-run).
- **v1** (agent loop): a repeated search returns a short hint instead of 10k more characters; the last step removes the
  tools and asks for a best-effort answer; an honest "not found" is accepted without a repair turn once the agent has
  searched. Negative questions 3/6 to 5/6; tokens down 23%.
- **v2** (retrieval): oversized classes split into one chunk per method; each chunk records the name it defines and a
  third ranking signal matches names in the query; a model that ignores the last-step "no tools" is asked again for
  plain text; `path:12,40-45` citation lists are parsed. The empty answers and most repeated searches are gone.

## Retrieval, measured without a model

Where does the gold evidence rank? 32 positive questions, final index.

| Queries used | Name matching | hit@1 | hit@3 | hit@8 | MRR |
|---|---|---|---|---|---|
| The question text | off | 53% | 81% | 91% | 0.689 |
| The question text | **on** | **66%** | **88%** | **97%** | **0.786** |
| The baseline agent's own searches | off | 31% | 69% | 88% | 0.519 |
| The baseline agent's own searches | **on** | **53%** | **81%** | **94%** | **0.681** |

The agent's own searches are identifier-style (`def prompt(`), and name matching helps them most. The worst
thrasher, `clk-07`, is only found with name matching on.

## Index speed versus accuracy

Embedding cost grows steeply with text length. The first N characters of each chunk are embedded; keyword and name
search still see the whole chunk. (Batch size is covered in the next section: an earlier version of this page said it
made no difference, which was wrong. I had only compared 16, 32 and 64.)

| Embedded characters | chunks per second | click index build | hit@1 | hit@3 | hit@8 | MRR |
|---|---|---|---|---|---|---|
| 1500 (before) | 7.4 | 263s | 62% | 81% | 91% | 0.740 |
| **1000 (now)** | 10.3 | **175s** | 59% | 81% | **91%** | 0.729 |
| 700 | 17.7 | 128s | 62% | 78% | 88% | 0.729 |

Measured with the question text as the query, before the later change that tags every window of a long function
(which lifts the 1000-character index to 66% / 88% / 97% in the table above; the final build takes 185s).

1000 was chosen: a third faster with the same recall@8. 700 halves the time but loses a question at rank 8 and drops
`clk-06` out of the top 20. The differences are one question each, so this is a judgement, not a proof.

### Batch size: the bigger win

fastembed pads every text in a batch to the longest one, and its default batch is 256. Chunks vary a lot in length, so
most of the compute and memory goes on padding. Measured on 200 of click's chunks (1000 characters embedded):

| Batch size | chunks per second | peak memory indexing itsdangerous | vector difference vs batch 32 |
|---|---|---|---|
| 32 | 10.6 | 869 MB | none |
| 8 | 14.5 | 461 MB | none |
| 4 | 17.7 | 356 MB | none |
| **1 (now)** | **29.6** | **280 MB** | **none (max 0.0)** |

The output vectors are identical, so retrieval is unchanged (hit@1 66%, hit@8 97%, MRR 0.786, verified after the
change). `click` now indexes in **71s instead of 185s**, `itsdangerous` in 7s instead of 18s, and indexing fits in a
512 MB instance, which batch 32 did not (it needed 869 MB). Serving a question peaks at 298 MB.

## Known failures

- `its-14` fails in both later runs: asked how itsdangerous integrates with Django's session framework, the model
  describes the Django-compatible `django-concat` key derivation as "integration". The baseline answered correctly,
  so this is partly model variance.
- `clk-04` and `clk-11` flip between runs, which is why single-run differences are treated as noise.
- Fact checks are regexes. A correct answer in unexpected words can fail, and `clk-01` did when the model described
  `get_help_option` without naming it. I did not loosen the check after seeing it.

## Reproduce

```bash
uv run repopilot eval verify
uv run repopilot eval run baseline --model gemini-3.5-flash-lite --min-interval 1
uv run repopilot eval report evals/results/baseline --price-in 0.30 --price-out 2.50
uv run repopilot eval retrieval --queries-from evals/results/baseline
```
