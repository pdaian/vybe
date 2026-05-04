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
- queues follow-up prompts while Codex is still running, then auto-extends in order
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

The tool snapshots the repo, sends the task to `codex`, keeps the run animation visible, and lets you press `Enter` to open multiline follow-up capture while it is still working. Queued prompts run automatically in order before you inspect and decide what lands.

If the repo uses initialized submodules, their tracked contents are included in the temp workspace so Codex can inspect and edit them too.

`vybe` defaults to GPT-5.5 with `max` reasoning and Codex `fast_mode` disabled for higher-quality coding runs. `max` maps to Codex `xhigh`, the highest reasoning effort currently supported by GPT-5.5 in the Codex CLI.

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
- do not hardcode secrets into the script

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
