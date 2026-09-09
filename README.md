# vybe

Terminal wrapper for `codex` inside a git repo.

Low ceremony. High signal. Snapshot the repo, run the agent, inspect the diff, apply with intent.

## What it does

- runs a long-lived prompt loop
- accepts multiline task input
- executes `codex exec` against a temp snapshot of the current repo
- includes initialized git submodule contents in that snapshot
- shows summary and changed files
- supports inspect / extend / apply / reject flow
- accepts stack, refine, and branch prompts while Codex is still running
- executes refinements first, Git-backed branch workstreams second, and stacked follow-ups last
- previews the prompt Git graph and replays it into the repository when applied
- can commit per file or as one commit
- defaults to a single commit when applying changes
- applies submodule edits in `single` commit mode by committing submodules first, then the superproject
- pushes to the configured remote after apply
- filters generated junk from change detection

## Install

```bash
sudo cp vybe /usr/bin/vybe
sudo chmod +x /usr/bin/vybe
```

Requirements:

- `python3`
- `git`
- `codex`
- OpenAI credentials configured for `codex`

## Use

Run it from inside the target repo:

```bash
vybe
```

Write the task. For multiline input, end with 4 blank lines.

The tool snapshots the repo, sends the task to `codex`, and keeps the run animation visible. The run display rotates through 40 colored, ASCII-only lunarpunk scenes every 10 seconds. Scene selection loosely follows Codex activity such as inspecting, searching, writing, executing, verifying, and working with Git. On sufficiently wide terminals, an IRC-style `#codex-activity` sidebar shows the user-visible reasoning summaries, assistant updates, and coarse tool activity emitted by Codex. It intentionally omits raw commands, tool arguments, and hidden chain-of-thought; on narrow terminals, the existing animation remains unchanged.

While Codex is working, the live keyboard controls are:

- `Enter` — stack a linear follow-up
- `R` — refine the active task with a priority correction or constraint
- `B` — start an additive branch workstream

Each key opens multiline capture; finish the prompt with 4 blank lines. The current `codex exec` process is non-interactive, so a refinement does not interrupt or rewrite the request already in flight. It runs immediately afterward, before branch and stack prompts, and is explicitly told to reconcile the correction with the existing work.

Branch workstreams execute serially so each starts from the latest integrated result. Each workstream runs on a real branch in the temporary snapshot, can itself receive refine, branch, and stack prompts, and is merged back before the next workstream. This provides deterministic additive composition instead of racing agents against the same files. Stacked prompts run after the branches captured for their parent prompt.

Before the decision menu, vybe shows the resulting prompt Git graph. Applying a branched session replays each prompt commit, local `vybe/<session>/...` branch, and merge onto the current repository branch. The local workstream branches are intentionally kept so `git log --graph --all` mirrors the prompt tree. If the result includes submodule edits or paths excluded from review, vybe safely falls back to the existing net-diff apply flow.

If the repo uses initialized submodules, their tracked contents are included in the temp workspace so Codex can inspect and edit them too.

`vybe` defaults to GPT-6 Astra with `max` reasoning, high verbosity, web search enabled when supported by the Codex CLI, and Codex `fast_mode` disabled for higher-quality coding runs. For ChatGPT Pro subscription usage, sign in to Codex with ChatGPT rather than relying on an API key.

If your installed Codex CLI or account does not yet support GPT-6 Astra, update Codex or override the model:

```bash
VYBE_CODEX_MODEL=gpt-5.6-sol vybe
```

To trade quality for speed, set `VYBE_CODEX_MODE` before launch:

```bash
VYBE_CODEX_MODE=fast vybe
VYBE_CODEX_MODE=2x vybe
VYBE_CODEX_MODE=slow vybe
```

`fast` and `2x` enable Codex `fast_mode`. `slow` disables it. If unset, `vybe` defaults to `slow`.

To tune reasoning depth, set `VYBE_CODEX_REASONING_EFFORT`:

```bash
VYBE_CODEX_REASONING_EFFORT=high vybe
VYBE_CODEX_REASONING_EFFORT=xhigh vybe
VYBE_CODEX_REASONING_EFFORT=max vybe
```

Accepted reasoning values are `low`, `medium`, `high`, `xhigh`, `extra`, and `max`. If unset, `vybe` defaults to `max`.

For GPT-6 Astra and GPT-5.6 models, `max` is passed through as Codex `max`. For older models, `max` maps to Codex `xhigh`, the strongest broadly supported reasoning effort.

To tune default response detail, set `VYBE_CODEX_VERBOSITY`:

```bash
VYBE_CODEX_VERBOSITY=high vybe
VYBE_CODEX_VERBOSITY=medium vybe
VYBE_CODEX_VERBOSITY=low vybe
```

Applying changes creates commit(s) and pushes them to the configured git remote for the current branch.

## Customize vybe with vybe

If `vybe` is in a git repo, you can use `vybe` to modify `vybe` itself.

Example:

```bash
cd /path/to/vybe-repo
vybe
```

Then give it a task such as:

```text
Update the status panel copy to be shorter.
Keep the solution minimal and production-ready.
```

Review the generated diff, inspect any changed files, and apply only when the patch is correct.

## Notes

- repo root is resolved from your current working directory
- use a token or PAT for HTTPS git auth, not a password
- git push auth can come from `GIT_REMOTE_USERNAME` / `GIT_REMOTE_TOKEN` in the script, or from `~/github.pat`
- `~/github.pat` format: first line GitHub username, second line PAT/token
- `VYBE_CODEX_MODE` accepts `fast`, `2x`, `slow`, or `normal`
- `VYBE_CODEX_REASONING_EFFORT` accepts `low`, `medium`, `high`, `xhigh`, `extra`, or `max`
- `VYBE_CODEX_MODEL` overrides the default `gpt-6-astra` model
- `VYBE_CODEX_VERBOSITY` accepts `low`, `medium`, or `high`
- do not hardcode secrets into the script

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
