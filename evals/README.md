# RepoPilot evaluation

How we measure whether RepoPilot's answers are right, and whether a change made them better or worse.

## What is measured

38 questions over three repos pinned to exact commits (`itsdangerous` and `click` in Python, `slugify` in
JavaScript). Question types: 17 facts, 6 reasoning, 9 multi-hop, and 6 negative questions whose correct answer is
"this is not in the repo" (for example "How does click support asyncio?"). Negative questions test whether the
agent invents an answer.

A question **passes** only when all of these hold:

1. **Facts:** every expected fact (a regex written for the question) appears in the answer.
2. **Evidence:** at least one verified citation overlaps the gold lines I wrote down for the question.
3. **Citations:** none is invalid (file or lines do not exist) and none is unread (real lines the agent never retrieved).
4. **Finished:** the agent stopped on its own, not on a step or token limit.

Negative questions skip the evidence rule and may cite nothing, but they still fail if they cite a file that does
not exist or if they confidently describe a feature that is absent.

Scoring is deterministic: no LLM judge. That makes runs reproducible and free of judge bias, at a price: regex
facts can miss a correct answer phrased in an unexpected way, and can accept a wrong answer that happens to
use the right words. Read the failures list in every report before trusting a number.

Other numbers reported: citation validity, share of citations the agent had read, average cited span in lines
(tightness), latency p50 and p95, steps, tokens per question, optional cost, and index build time.

## Ground truth

`evals/data/questions.json`. Every gold range has an `anchor` string that must appear inside the range.
`repopilot eval verify` checks out each repo at its pinned commit and fails if any range or anchor has drifted.
Run it whenever the dataset changes.

## Running it

```bash
uv run repopilot eval verify                      # network, no LLM key
export REPOPILOT_PROVIDER=gemini GEMINI_API_KEY=...
uv run repopilot eval run baseline --min-interval 2
uv run repopilot eval report evals/results/baseline --price-in 0.30 --price-out 2.50

# compare a change against the baseline
uv run repopilot eval run variant --k 5
uv run repopilot eval report evals/results/variant --baseline evals/results/baseline
```

Retrieval alone (no model, free, exact):

```bash
uv run repopilot eval retrieval                      # where does the gold evidence rank for each question?
uv run repopilot eval retrieval --no-symbols         # same index, name matching off: an exact ablation
uv run repopilot eval retrieval --queries-from evals/results/baseline   # replay a run's own searches
uv run repopilot eval retrieval --embed-chars 700    # build an alternative index: accuracy against speed
```

`--k`, `--max-chars`, `--max-steps` change the agent without code edits. Runs are resumable (`--fresh` starts over),
retry provider failures but not wrong answers, record any other exception instead of crashing, and stop at
`--token-cap`. Traces are written to `evals/results/<label>/traces.jsonl` (git-ignored): one line per question with
timestamped steps, tokens, latency, the verification report and the score.

## Reading results honestly

- With 38 questions a single question is 2.6 points. The report prints a 95% interval; differences smaller than
  the interval are noise. The comparison section lists exactly which questions changed outcome.
- Latency on a free tier mostly reflects provider load, not our code. Compare tokens and steps for efficiency.
- Free-tier tokens cost nothing; the cost line uses the model's published paid price, so it is a what-if.
- Free-tier quotas are per model per day. A long run can end early; the same command resumes, and reports leave
  questions a provider error prevented out of paired comparisons.
- The questions were written by the same person who built the system, from the code at the pinned commits. They
  are not a neutral benchmark. A fair next step is a second author, or questions taken from real user sessions.
