# vybe

Terminal wrapper for `codex` inside a git repo.

Low ceremony. High signal. Snapshot the repo, run the agent, inspect the diff, apply with intent.

## What it does

- runs a long-lived prompt loop
- accepts multiline task input
- executes `codex exec` against a temp snapshot of the current repo
- shows summary and changed files
- supports inspect / extend / apply / reject flow
- can commit per file or as one commit
- defaults to a single commit when applying changes
- can push after apply
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

The tool snapshots the repo, sends the task to `codex`, then lets you inspect, extend with another prompt against the same session, and decide what lands.

To control Codex speed mode, set `VYBE_CODEX_MODE` before launch:

```bash
VYBE_CODEX_MODE=fast vybe
VYBE_CODEX_MODE=2x vybe
VYBE_CODEX_MODE=slow vybe
```

`fast` and `2x` enable Codex `fast_mode`. `slow` disables it. If unset, `vybe` defaults to `fast`.

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
- do not hardcode secrets into the script

## License

GPL-3.0-or-later. See [LICENSE](/tmp/codex-run-7nbnrh1a/working/LICENSE).
