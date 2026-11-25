# Contributing

## Workflow (trunk-based)
- `main` is always releasable. No direct pushes; every change lands through a pull request.
- Branch from `main`, keep branches short-lived (days, not weeks): `feat/<topic>`, `fix/<topic>`, `chore/<topic>`.
- Keep PRs small and single-purpose (aim for under 400 changed lines). Split refactors from behaviour changes.
- PRs are **squash-merged** so history on `main` is one reviewed commit per change.

## Commit and PR titles
[Conventional Commits](https://www.conventionalcommits.org): `type(scope): imperative summary`
(`feat`, `fix`, `perf`, `refactor`, `test`, `docs`, `chore`, `ci`). The body explains **why**, not what.

## Definition of done
1. `make check` passes (lint, tests, web lint/types/build). CI runs the same steps.
2. Behaviour changes have tests. Anything that touches retrieval, prompts or citation checking also needs an
   eval before/after (see `evals/` once it lands) in the PR description.
3. UI changes include a screenshot (desktop and mobile).
4. Design decisions that change the architecture are recorded in `DECISIONS.md`.
5. A code owner has reviewed it. Reviewers check correctness, tests, security (untrusted input, secrets), and
   whether the change is the smallest one that solves the problem.

## Security
Do not commit secrets. See `SECURITY.md`.
