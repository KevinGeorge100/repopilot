# Deploying RepoPilot on Render

One Render web service serves both the UI and the API from a single URL. The Docker image already contains the web
app, the embedding model, and three demo repos indexed at pinned commits, so the running service does no heavy work and
fits Render's free 512 MB instance.

## What you will have

- A public link such as `https://repopilot-xxxx.onrender.com`.
- Three pre-indexed repos to explore. Their example questions are **real answers saved from an evaluation run**, shown
  with a "saved from an evaluation run" label, loading in about 100 ms and costing no model calls.
- Questions typed by visitors are answered **live** by Gemini, capped per UTC day (`REPOPILOT_DAILY_ASK_CAP`, default
  150) so a public link cannot use up the free quota. When the cap or quota is reached the page says so and the examples
  keep working.

## Steps

1. **Get a free Gemini key** at <https://aistudio.google.com/api-keys>. You will paste it into Render, never into git.
2. **Create the service.** In the Render dashboard choose **New, then Blueprint**, connect your GitHub account, and pick
   the `repopilot` repository. Render reads `render.yaml`.
3. **Paste `GEMINI_API_KEY`** when Render asks for it, then **Apply**.
4. **Wait for the first build.** It installs dependencies, downloads the embedding model, and indexes the three demo
   repos (about 80 seconds on 4 CPU cores, longer on a smaller builder), then builds the web app. Watch the build log.
5. **Check it.** Open `https://<your-service>.onrender.com/api/health` (expect `{"ok":true}`), then the root URL. The
   landing page should list three repos. Open one, click an example question, then click a citation: the cited lines
   highlight in the source on the right. Type your own question to confirm live answers work.
6. **Put the link in the README.** Add a line near the top, for example `**Live demo:** https://<your-service>.onrender.com`,
   through a normal pull request.

## What to expect on the free plan

- **Sleep.** A free service spins down after about 15 minutes without traffic. The first visit afterwards waits for the
  container to start (tens of seconds). Cached example answers are instant once it is up.
- **First live question.** The embedding model loads on first use, which took about 12 seconds in testing. Memory then
  settles near 320 MB, under the 512 MB limit. Idle and while serving cached answers it uses about 73 MB.
- **No disk.** Indexes baked into the image survive restarts; anything created while running does not. That is why the
  demo refuses to index new repos.
- **Model limits.** The free Gemini tier has a daily request quota per model and returns "high demand" errors at times.
  The page turns these into plain messages, and the example questions never depend on the model.

## Settings

Set these in Render's **Environment** tab. Only `GEMINI_API_KEY` is required.

| Variable | Default | What it does |
|---|---|---|
| `GEMINI_API_KEY` | none | The model key. The only secret. |
| `REPOPILOT_PROVIDER` | `gemini` | `gemini`, `groq`, `openrouter` or `anthropic` (each needs its own key variable). |
| `REPOPILOT_MODEL` | provider default | Override the model name. |
| `REPOPILOT_DAILY_ASK_CAP` | `150` | Live questions per UTC day across all visitors. |
| `REPOPILOT_DEMO_MODE` | `1` in the image | `0` lets visitors index any public repo. Raise the plan's memory and CPU first. |
| `REPOPILOT_MAX_CHUNKS` | `2500` | With demo mode off, the largest repo a visitor may index. |
| `GITHUB_TOKEN` | none | Raises GitHub's rate limit for pull request review. |

## Changing the demo repos or examples

- Repos: edit `demo/manifest.json` (a GitHub URL and a full 40-character commit SHA each) and redeploy. The build indexes
  whatever is listed.
- Example answers: `uv run repopilot demo-export evals/results/<run> --exclude <question ids>` rewrites
  `demo/answers.json` from a finished evaluation run. Answers are copied verbatim, only passing ones are used, and each
  keeps the run and model it came from. Read them before committing.

## Troubleshooting

- **Build fails at `uv sync`.** Check the log for a missing file: the image copies `pyproject.toml`, `uv.lock`,
  `README.md` and `LICENSE`. (A missing `LICENSE` caused exactly this during testing.)
- **Landing page shows a plain repo box and no repos.** The API did not find the seeded data. Check that the build log
  shows the three `chunks in ...s` lines from `repopilot seed`, and that `REPOPILOT_WORKDIR` was not overridden.
- **"Live questions are unavailable".** No model is configured (check `GEMINI_API_KEY`), or today's cap is used up.
- **Out of memory.** Not seen at 512 MB in testing (peak about 320 MB), but if you turn demo mode off and index large
  repos, move to a larger plan.

## Honest notes on testing

The Dockerfile could not be built where it was written (no Docker daemon). Its Python stage was reproduced step by step in
a clean directory, and the server was run the way the container's `CMD` runs it, in an empty environment. That caught one
real bug (the missing `LICENSE`). The first build on Render is the first time the whole image is built end to end, so read
that build log.

To try the image yourself if you have Docker:

```bash
docker build -t repopilot .
docker run --rm -p 10000:10000 -e GEMINI_API_KEY=... -e REPOPILOT_PROVIDER=gemini repopilot
```
