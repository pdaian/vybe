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
- saves submitted prompts and completed work for recovery after errors or restarts
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

The tool snapshots the repo, sends the task to `codex`, and keeps the run animation visible. The live view fills the terminal height and follows window resizes, including inside GNU Screen; each animation scales vertically to fill the space between the status header and keyboard controls on the last row. The run display rotates through 40 colored, ASCII-only lunarpunk scenes every 10 seconds. Scene selection loosely follows Codex activity such as inspecting, searching, writing, executing, verifying, and working with Git. On sufficiently wide terminals, an IRC-style `#codex-activity` sidebar fills the height alongside the animation and shows the user-visible reasoning summaries, assistant updates, and coarse tool activity emitted by Codex. It intentionally omits raw commands, tool arguments, and hidden chain-of-thought; on narrow terminals, the sidebar is hidden.

The query timer shows seconds through five minutes, then minutes and seconds. After more than five hours it shows hours, minutes, and seconds; after more than five days it adds days; after more than five months it adds months. Months use fixed 30-day durations. Longer formats include all smaller units, using whole seconds. The spinner and full-screen status view use the same format.

While Codex is working, the live keyboard controls are:

- `Enter` — stack a linear follow-up
- `R` — refine the active task with a priority correction or constraint
- `B` — start an additive branch workstream
- `Up` / `Down` — scroll the activity sidebar one line at a time

The sidebar retains the latest 32 activity messages. Scrolling up holds your place as new updates arrive, until those messages leave the retained history. Scrolling back to the bottom resumes following live updates; the sidebar footer shows whether you are live or how many lines up you have scrolled.

`Enter`, `R`, and `B` each open multiline capture; finish the prompt with 4 blank lines. The current `codex exec` process is non-interactive, so a refinement does not interrupt or rewrite the request already in flight. It runs immediately afterward, before branch and stack prompts, and is explicitly told to reconcile the correction with the existing work.

Branch workstreams execute serially so each starts from the latest integrated result. Each workstream runs on a real branch in the temporary snapshot, can itself receive refine, branch, and stack prompts, and is merged back before the next workstream. This provides deterministic additive composition instead of racing agents against the same files. Stacked prompts run after the branches captured for their parent prompt.

Submitted prompts are saved as **unprocessed** before execution, including live stack, refine, branch, and extend prompts. Each successful response saves its summary and a Git checkpoint before the next prompt runs. The snapshot, working files, prompt tree, and recovery manifest live in `$(git rev-parse --git-path vybe)` (normally `.git/vybe`), outside the tracked files. Saving uses an atomic manifest replacement. Network errors, quota failures, and interruptions retain completed work, the interrupted prompt's partial edits, and queued follow-ups.

When you restart in the same repository checkout, vybe offers these recovery choices:

- **Yes:** restore the saved session and retry its failed or interrupted prompt, then continue the queue in its original refine / branch / stack order. Completed prompts are not sent to Codex again. If all prompts already completed, return to review.
- **No (retry fresh):** discard the saved work and completed history, take a new snapshot of the current repository, and run the unfinished prompts with their queued follow-ups. If none remain, start a new session.
- **Discard:** remove the saved session and start a new one.
- **Quit:** keep everything saved for later.

After a failure, Enter retries with the saved work; `fresh`, `discard`, and `quit` have the same meanings as above. The decision menu also supports `q` to quit with the result saved. Restoring a session restores its workspace; applying changes to the real repository still uses the normal review and apply menu. Saved data is removed after a successful apply or explicit rejection/discard. Only one vybe process can use a checkout's recovery data at a time.

Applying saved work requires the original repository branch and HEAD and a clean working tree. An interrupted apply keeps its recovery data and requires you to inspect and resolve any partially applied changes; vybe will not silently replay commits onto a changed checkout. Recovery files are local to this checkout and are not included in commits or pushes.

Before the decision menu, vybe shows the resulting prompt Git graph. Applying a branched session replays each prompt commit, local `vybe/<session>/...` branch, and merge onto the current repository branch. The local workstream branches are intentionally kept so `git log --graph --all` mirrors the prompt tree. If the result includes submodule edits or paths excluded from review, vybe safely falls back to the existing net-diff apply flow.

If the repo uses initialized submodules, their tracked contents are included in the temp workspace so Codex can inspect and edit them too.

`vybe` defaults to GPT-6.2 Astra with `max` reasoning, high verbosity, web search enabled when supported by the Codex CLI, and the standard service tier (`service_tier = "default"`, with Codex `fast_mode` disabled). For ChatGPT Pro subscription usage, sign in to Codex with ChatGPT rather than relying on an API key.

If your installed Codex CLI or account does not yet support GPT-6.2 Astra, update Codex or override the model with one available to your account, such as GPT-6.1 Sol:

```bash
VYBE_CODEX_MODEL=gpt-6.1-sol vybe
```

To change processing speed, set `VYBE_CODEX_MODE` before launch:

```bash
VYBE_CODEX_MODE=fast vybe
VYBE_CODEX_MODE=2x vybe
VYBE_CODEX_MODE=slow vybe
```

`fast` and `2x` enable Codex `fast_mode` and explicitly select `service_tier = "fast"`. `slow` and `normal` disable it and select the standard tier, overriding a saved service-tier preference. If unset, `vybe` defaults to `slow`. Fast mode changes speed and usage, while the model and reasoning effort stay the same; `2x` is an alias, not a guaranteed speed multiplier.

To tune reasoning depth, set `VYBE_CODEX_REASONING_EFFORT`:

```bash
VYBE_CODEX_REASONING_EFFORT=high vybe
VYBE_CODEX_REASONING_EFFORT=xhigh vybe
VYBE_CODEX_REASONING_EFFORT=max vybe
VYBE_CODEX_REASONING_EFFORT=ultra vybe
```

Accepted reasoning values are `low`, `medium`, `high`, `xhigh`, `extra`, `max`, and `ultra`. If unset, `vybe` defaults to `max`.

For GPT-6.2 Astra, GPT-6.2 Sol, GPT-6 Astra, GPT-6.1 Sol, GPT-6 Sol, GPT-6 Luna, and GPT-5.6 models (including dated snapshots), `max` is passed through as Codex `max`. For other models, the existing compatibility mapping sends `xhigh`; choose an explicit lower effort if the model requires it. `extra` is an alias for `max`.

`ultra` is passed through unchanged and requires support from your selected model, Codex CLI, and account. It combines maximum reasoning with subagent delegation where supported. GPT-6 Luna supports `max`, but not `ultra`.

To tune default response detail, set `VYBE_CODEX_VERBOSITY`:

```bash
VYBE_CODEX_VERBOSITY=high vybe
VYBE_CODEX_VERBOSITY=medium vybe
VYBE_CODEX_VERBOSITY=low vybe
```

See the official [Codex model guidance](https://learn.chatgpt.com/docs/models), [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference), and [speed settings](https://learn.chatgpt.com/docs/agent-configuration/speed) for current availability and supported parameters.

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
- `VYBE_CODEX_REASONING_EFFORT` accepts `low`, `medium`, `high`, `xhigh`, `extra`, `max`, or `ultra`
- `VYBE_CODEX_MODEL` overrides the default `gpt-6.2-astra` model
- `VYBE_CODEX_VERBOSITY` accepts `low`, `medium`, or `high`
- do not hardcode secrets into the script

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
