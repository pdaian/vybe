# vybe

Terminal wrapper for `codex` inside a git repo.

Low ceremony. High signal. Snapshot the repo, run the agent, inspect the diff, apply with intent.

## What it does

- runs a long-lived prompt loop
- accepts multiline task input
- executes `codex exec` against a temp snapshot of the current repo
- shows summary and changed files
- supports inspect / apply / reject flow
- can commit per file or as one commit
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

The tool snapshots the repo, sends the task to `codex`, then lets you inspect and decide what lands.

## Notes

- repo root is resolved from your current working directory
- use a token or PAT for HTTPS git auth, not a password
- do not hardcode secrets into the script

## License

GPL-3.0-or-later. See [LICENSE](/tmp/codex-run-7nbnrh1a/working/LICENSE).
