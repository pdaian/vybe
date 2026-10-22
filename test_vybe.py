"""Recovery regression tests. Run with python3 -B -m unittest -v test_vybe.

The manifest and Git workspace are modeled in memory: no Codex calls, files,
branches, caches, or test artifacts are created by this suite.
"""

import copy
import io
import json
import subprocess
import sys
import types
import unittest
from contextlib import ExitStack, contextmanager, redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch


SOURCE = Path(__file__).with_name("vybe")
vybe = types.ModuleType("vybe_under_test")
vybe.__file__ = str(SOURCE)
sys.modules[vybe.__name__] = vybe
exec(compile(SOURCE.read_text(encoding="utf-8"), str(SOURCE), "exec"), vybe.__dict__)

REPO = Path("/virtual/repo")
ROOT = REPO / ".git" / "vybe"
SUPPORT = vybe.CodexSupport(True, True, True)


class MemoryFiles:
    def __init__(self):
        self.files = {}
        self.directories = set()
        self.descriptors = {}
        self.next_fd = 100

    def open(self, path, *_args):
        self.next_fd += 1
        self.descriptors[self.next_fd] = Path(path)
        return self.next_fd

    @contextmanager
    def fdopen(self, fd, *_args, **_kwargs):
        stream = io.StringIO()
        stream.fileno = lambda: fd
        try:
            yield stream
        finally:
            self.files[self.descriptors.pop(fd)] = stream.getvalue()
            stream.close()

    def replace(self, source, target):
        self.files[Path(target)] = self.files.pop(Path(source))

    def remove_tree(self, root):
        self.files = {path: text for path, text in self.files.items() if not path.is_relative_to(root)}
        self.directories = {path for path in self.directories if not path.is_relative_to(root)}

    def install(self, stack):
        stack.enter_context(patch.object(Path, "mkdir", lambda path, **kw: self.directories.add(path)))
        stack.enter_context(patch.object(Path, "exists", lambda path: path in self.files or path in self.directories))
        stack.enter_context(patch.object(Path, "is_dir", lambda path: path in self.directories))
        stack.enter_context(patch.object(Path, "iterdir", lambda path: iter(p for p in self.files if p.parent == path)))
        stack.enter_context(patch.object(Path, "read_text", lambda path, **kw: self.files[path]))
        stack.enter_context(patch.object(vybe.os, "open", self.open))
        stack.enter_context(patch.object(vybe.os, "fdopen", self.fdopen))
        stack.enter_context(patch.object(vybe.os, "fsync"))
        stack.enter_context(patch.object(vybe.os, "close", lambda fd: self.descriptors.pop(fd)))
        stack.enter_context(patch.object(vybe.os, "replace", self.replace))
        stack.enter_context(patch.object(vybe.shutil, "rmtree", self.remove_tree))


class MemoryGit:
    def __init__(self):
        self.reset_workspace()
        self.commands = []
        self.real_head = "real-base"
        self.real_branch = "main"
        self.real_dirty = ""
        self.after_command = lambda args: None

    def reset_workspace(self):
        self.branch = "main"
        self.heads = {"main": "snapshot"}
        self.trees = {"snapshot": {}}
        self.parents = {"snapshot": []}
        self.files = {}

    def commit(self, parents):
        head = f"commit-{len(self.trees)}"
        self.trees[head] = copy.deepcopy(self.files)
        self.parents[head] = parents
        self.heads[self.branch] = head

    def ancestor(self, older, newer):
        return older == newer or any(self.ancestor(older, parent) for parent in self.parents[newer])

    def run(self, args, *, cwd=None, **_kwargs):
        args = list(args)
        self.commands.append(args)
        output = ""
        if args == ["git", "rev-parse", "HEAD"]:
            output = self.real_head if cwd == REPO else self.heads[self.branch]
        elif args == ["git", "rev-parse", "--abbrev-ref", "HEAD"]:
            output = self.real_branch if cwd == REPO else self.branch
        elif args == ["git", "status", "--porcelain"]:
            output = self.real_dirty
        elif args[:4] == ["git", "show-ref", "--verify", "--quiet"]:
            name = args[-1].removeprefix("refs/heads/")
            return subprocess.CompletedProcess(args, 0 if name in self.heads else 1, "", "")
        elif args[:3] == ["git", "reset", "--soft"]:
            self.heads[self.branch] = args[3]
        elif args == ["git", "add", "-A"]:
            pass
        elif args[:2] == ["git", "commit"]:
            self.commit([self.heads[self.branch]])
        elif args[:2] == ["git", "checkout"]:
            if args[2] == "-b":
                if args[3] in self.heads:
                    raise vybe.CommandError("Branch already exists")
                self.heads[args[3]] = self.heads[self.branch]
            self.branch = args[-1]
            self.files = copy.deepcopy(self.trees[self.heads[self.branch]])
        elif args[:3] == ["git", "merge", "--no-ff"]:
            parent, child = self.heads[self.branch], self.heads[args[3]]
            if not self.ancestor(child, parent):
                self.files = copy.deepcopy(self.trees[child])
                self.commit([parent, child])
        else:
            raise AssertionError(f"Unexpected command: {args}")
        self.after_command(args)
        return subprocess.CompletedProcess(args, 0, output, "")


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(redirect_stdout(io.StringIO()))
        self.fs = MemoryFiles()
        self.fs.install(self.stack)
        self.git = MemoryGit()
        self.stack.enter_context(patch.object(vybe, "run_cmd", self.git.run))
        self.stack.enter_context(patch.object(vybe, "make_temp_snapshot", self.snapshot))
        self.calls = []
        self.behavior = {}
        self.runner = self.stack.enter_context(patch.object(vybe, "run_codex", self.codex))
        self.session = vybe.PromptSession(repo=REPO, root=ROOT)

    def snapshot(self, _repo, root):
        self.git.reset_workspace()
        self.fs.directories.update({root / "snapshot", root / "working", root / "working" / ".git"})
        return root, root / "snapshot", root / "working"

    def codex(self, _support, _working_dir, text, *, on_queue, lock_fd=None):
        name = text.split("\n\n")[-1]
        self.calls.append(name)
        saved = self.reload()
        self.assertIn('"status": "running"', self.fs.files[ROOT / "session.json"])
        self.assertTrue(saved.workspace_ready)
        self.git.files[name] = f"work from {name}"
        if name in self.behavior:
            self.behavior[name](on_queue)
        return f"summary of {name}", "", []

    def reload(self):
        session = vybe.PromptSession.load(REPO, ROOT)
        self.assertIsNotNone(session)
        return session

    def add(self, name, kind="root", parent=None):
        return self.session.add_prompt(vybe.PromptAction(kind, name), parent=parent)

    def run_chain(self):
        return vybe.run_prompt_chain(SUPPORT, self.session)

    def fail_codex(self, _on_queue):
        raise vybe.CommandError("quota exceeded")

    def test_submitted_prompt_is_saved_before_dirty_repository_check(self):
        self.git.real_dirty = " M source.py"
        self.add("root task")
        with self.assertRaises(vybe.RetryablePromptError):
            self.run_chain()
        saved = self.reload()
        self.assertEqual(saved.prompts[0].status, "unprocessed")
        self.assertFalse(saved.workspace_ready)
        self.assertEqual(self.calls, [])

    def test_failed_chain_restores_work_and_retries_only_failed_prompt(self):
        root = self.add("first")
        self.add("second", "stack", root)
        self.add("third", "stack", root)
        self.behavior["second"] = self.fail_codex
        with self.assertRaises(vybe.CommandError):
            self.run_chain()
        self.session = self.reload()
        self.assertEqual(self.session.prompts[0].status, "completed")
        self.assertEqual(self.session.prompts[0].children[0].status, "failed")
        self.assertIn("first", self.git.files)
        self.assertIn("second", self.git.files)
        del self.behavior["second"]
        trace = self.run_chain()
        self.assertEqual(self.calls, ["first", "second", "second", "third"])
        self.assertEqual(trace.summary_history, ["summary of first", "summary of second", "summary of third"])
        self.assertEqual(set(self.git.files), {"first", "second", "third"})
        self.assertEqual(self.reload().phase, "review")

    def test_live_queue_is_durable_before_failing_parent_returns(self):
        self.add("parent")

        def enqueue_then_fail(on_queue):
            for kind in ("stack", "branch", "refine"):
                on_queue(vybe.PromptAction(kind, kind))
                self.assertEqual(self.reload().prompts[0].children[-1].status, "unprocessed")
            self.fail_codex(on_queue)

        self.behavior["parent"] = enqueue_then_fail
        with self.assertRaises(vybe.CommandError):
            self.run_chain()
        self.session = self.reload()
        del self.behavior["parent"]
        self.run_chain()
        self.assertEqual(self.calls, ["parent", "parent", "refine", "branch", "stack"])
        self.assertEqual(self.git.branch, "main")

    def test_nested_branch_failure_resumes_with_balanced_graph(self):
        root = self.add("root")
        branch = self.add("branch", "branch", root)
        nested = self.add("nested", "branch", branch)
        self.add("nested stack", "stack", nested)
        self.add("last", "stack", root)
        self.behavior["nested"] = self.fail_codex
        with self.assertRaises(vybe.CommandError):
            self.run_chain()
        self.session = self.reload()
        del self.behavior["nested"]
        trace = self.run_chain()
        self.assertEqual(self.calls, ["root", "branch", "nested", "nested", "nested stack", "last"])
        depth = 0
        for event in trace.events:
            depth += {"branch_start": 1, "branch_end": -1}.get(event.event_type, 0)
            self.assertGreaterEqual(depth, 0)
        self.assertEqual(depth, 0)
        self.assertEqual(self.git.branch, "main")
        self.assertEqual(len(self.git.heads), 3)
        self.assertEqual(set(self.git.files), {"root", "branch", "nested", "nested stack", "last"})

    def test_checkpoint_failure_does_not_repeat_a_returned_prompt(self):
        self.add("task")
        with patch.object(vybe, "checkpoint_prompt", side_effect=vybe.CommandError("disk full")):
            with self.assertRaises(vybe.CommandError):
                self.run_chain()
        self.session = self.reload()
        self.assertEqual(self.session.prompts[0].status, "returned")
        self.assertEqual(self.session.prompts[0].summary, "summary of task")
        self.run_chain()
        self.assertEqual(self.calls, ["task"])

    def test_crash_after_checkpoint_commit_can_recheckpoint_without_codex(self):
        self.add("task")

        def crash(args):
            if args[:2] == ["git", "commit"]:
                raise KeyboardInterrupt

        self.git.after_command = crash
        with self.assertRaises(KeyboardInterrupt):
            self.run_chain()
        self.session = self.reload()
        self.git.after_command = lambda args: None
        self.run_chain()
        self.assertEqual(self.calls, ["task"])
        tip = self.git.heads["main"]
        self.assertEqual(self.git.parents[tip], ["snapshot"])

    def test_branch_creation_and_merge_crash_windows_are_recoverable(self):
        for command in ("checkout", "merge"):
            with self.subTest(command=command):
                self.fs.files.clear()
                self.session = vybe.PromptSession(repo=REPO, root=ROOT)
                self.calls.clear()
                root = self.add("root")
                self.add("child", "branch", root)
                self.session.prepare_workspace()

                def crash(args):
                    if args[:2] == ["git", command]:
                        raise KeyboardInterrupt

                self.git.after_command = crash
                with self.assertRaises(KeyboardInterrupt):
                    self.run_chain()
                self.session = self.reload()
                self.git.after_command = lambda args: None
                self.run_chain()
                self.assertEqual(self.calls, ["root", "child"])
                self.assertEqual(len(self.git.heads), 2)
                self.assertEqual(self.git.branch, "main")
                self.assertTrue(self.session.prompts[0].children[0].branch_merged)

    def test_branch_ref_created_before_checkout_can_resume(self):
        root = self.add("root")
        self.add("child", "branch", root)

        def crash(args):
            if args[:3] == ["git", "checkout", "-b"]:
                self.git.branch = "main"
                raise KeyboardInterrupt

        self.git.after_command = crash
        with self.assertRaises(KeyboardInterrupt):
            self.run_chain()
        self.session = self.reload()
        self.git.after_command = lambda args: None
        self.run_chain()
        self.assertEqual(self.calls, ["root", "child"])
        self.assertEqual(len(self.git.heads), 2)

    def test_interrupt_preserves_partial_work_and_queue(self):
        self.add("task")

        def interrupt(on_queue):
            on_queue(vybe.PromptAction("stack", "followup"))
            raise KeyboardInterrupt

        self.behavior["task"] = interrupt
        with self.assertRaises(KeyboardInterrupt):
            self.run_chain()
        self.session = self.reload()
        self.assertEqual(self.session.prompts[0].status, "failed")
        self.assertEqual(self.session.prompts[0].children[0].prompt, "followup")
        self.assertEqual(self.git.files["task"], "work from task")

    def test_running_prompt_after_abrupt_exit_is_retried(self):
        prompt = self.add("task")
        self.session.prepare_workspace()
        prompt.status = "running"
        prompt.starting_branch = "main"
        prompt.base_commit = "snapshot"
        self.session.save()
        self.git.files["partial"] = "unfinished edit"
        self.session = self.reload()
        self.run_chain()
        self.assertEqual(self.calls, ["task"])
        self.assertEqual(self.git.files["partial"], "unfinished edit")

    def test_failed_extend_preserves_original_history(self):
        self.add("original")
        self.run_chain()
        self.behavior["extension"] = self.fail_codex
        with patch.object(vybe, "idle_prompt_multiline", return_value="extension"):
            with self.assertRaises(vybe.CommandError):
                vybe.extend_result(REPO, SUPPORT, self.session, None)
        self.session = self.reload()
        del self.behavior["extension"]
        self.run_chain()
        self.assertEqual(self.calls, ["original", "extension", "extension"])
        self.assertEqual(self.session.trace().prompt_history, ["original", "extension"])

    def test_fresh_retry_drops_completed_work_but_keeps_pending_order(self):
        root = self.add("root")
        branch = self.add("branch", "branch", root)
        self.add("failed", "stack", branch)
        self.add("last", "stack", root)
        self.behavior["failed"] = self.fail_codex
        with self.assertRaises(vybe.CommandError):
            self.run_chain()
        self.session = self.reload()
        vybe.recover_session(self.session, "fresh")
        self.assertEqual([p.prompt for p in self.reload().prompts], ["failed", "last"])
        self.assertFalse(self.session.workspace_ready)
        del self.behavior["failed"]
        self.run_chain()
        self.assertEqual(set(self.git.files), {"failed", "last"})
        self.assertEqual(self.session.trace().prompt_history, ["failed", "last"])

    def test_atomic_write_failure_keeps_previous_manifest(self):
        self.add("first")
        previous = self.fs.files[ROOT / "session.json"]
        with patch.object(vybe.os, "replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.add("second", "stack")
        self.assertEqual(self.fs.files[ROOT / "session.json"], previous)
        self.assertEqual([p.prompt for p in self.reload().prompts], ["first"])

    def test_invalid_manifests_fail_without_replacing_saved_files(self):
        self.add("task")
        original = json.loads(self.fs.files[ROOT / "session.json"])
        missing_field = copy.deepcopy(original)
        del missing_field["prompts"][0]["status"]
        wrong_repo = dict(original, repo="/another/repo")
        for text in ("{", "null", "[]", json.dumps(missing_field), json.dumps(wrong_repo)):
            with self.subTest(text=text):
                self.fs.files[ROOT / "session.json"] = text
                with self.assertRaises(vybe.CommandError):
                    vybe.PromptSession.load(REPO, ROOT)
                self.assertEqual(self.fs.files[ROOT / "session.json"], text)

    def test_inconsistent_workspace_flag_cannot_delete_saved_work(self):
        self.add("task")
        self.run_chain()
        data = json.loads(self.fs.files[ROOT / "session.json"])
        data["workspace_ready"] = False
        self.fs.files[ROOT / "session.json"] = json.dumps(data)
        with self.assertRaises(vybe.CommandError):
            vybe.PromptSession.load(REPO, ROOT)
        self.assertEqual(self.git.files["task"], "work from task")

    def test_changed_checkout_blocks_apply_without_discarding_history(self):
        self.add("task")
        self.run_chain()
        self.git.real_head = "someone-elses-commit"
        result = types.SimpleNamespace(changed_files=[object()])
        with patch.object(vybe, "idle_prompt_line", return_value="apply"), patch.object(vybe, "apply_result") as apply:
            with self.assertRaises(vybe.RetryablePromptError):
                vybe.decision_loop(REPO, SUPPORT, self.session, result)
            apply.assert_not_called()
        self.assertEqual(self.reload().prompts[0].status, "completed")

    def test_apply_failure_keeps_session_and_marks_interrupted_apply(self):
        self.add("task")
        self.run_chain()
        result = types.SimpleNamespace(changed_files=[object()])
        with patch.object(vybe, "idle_prompt_line", return_value="apply"), patch.object(
            vybe, "apply_result", side_effect=vybe.CommandError("push failed"),
        ):
            with self.assertRaises(vybe.CommandError):
                vybe.decision_loop(REPO, SUPPORT, self.session, result)
        self.assertEqual(self.reload().phase, "applying")

    def test_quit_and_completed_restart_do_not_repeat_work(self):
        self.add("task")
        self.run_chain()
        for recovery in ("quit", "retry"):
            with self.subTest(recovery=recovery), patch.object(vybe, "prompt_restore_session", return_value=recovery), patch.object(
                vybe, "decision_loop", return_value="quit",
            ), patch.object(vybe, "session_result"), patch.object(vybe, "print_summary"):
                self.assertEqual(vybe.prompt_loop(REPO, SUPPORT, ROOT, 42), 0)
        self.assertEqual(self.calls, ["task"])
        self.assertEqual(self.reload().phase, "review")

    def test_prompt_loop_failure_quit_restart_and_retry(self):
        self.behavior["root"] = lambda queued: queued(vybe.PromptAction("stack", "failed"))
        self.behavior["failed"] = self.fail_codex
        with patch.object(vybe, "idle_prompt_multiline", return_value="root"), patch.object(
            vybe, "prompt_retry_saved_prompt", return_value="quit",
        ):
            self.assertEqual(vybe.prompt_loop(REPO, SUPPORT, ROOT, 42), 0)
        self.assertEqual(self.reload().prompts[0].children[0].status, "failed")
        del self.behavior["failed"]
        with patch.object(vybe, "prompt_restore_session", return_value="retry"), patch.object(
            vybe, "idle_prompt_line", return_value="quit",
        ), patch.object(vybe, "compute_changed_files", return_value=[]):
            self.assertEqual(vybe.prompt_loop(REPO, SUPPORT, ROOT, 42), 0)
        self.assertEqual(self.calls, ["root", "failed", "failed"])
        self.assertEqual(self.reload().phase, "review")

    def test_prompt_loop_removes_history_only_after_successful_apply(self):
        def apply(_repo, _result):
            self.assertEqual(self.reload().phase, "applying")

        changed = vybe.ChangedFile("task", "A", None, ROOT / "working" / "task")
        with patch.object(vybe, "idle_prompt_multiline", side_effect=["task", "quit"]), patch.object(
            vybe, "idle_prompt_line", return_value="apply",
        ), patch.object(vybe, "compute_changed_files", return_value=[changed]), patch.object(
            vybe, "apply_result", side_effect=apply,
        ) as apply_result:
            self.assertEqual(vybe.prompt_loop(REPO, SUPPORT, ROOT, 42), 0)
            apply_result.assert_called_once()
        self.assertEqual(self.calls, ["task"])
        self.assertIsNone(vybe.PromptSession.load(REPO, ROOT))

    def test_explicit_discard_clears_saved_session(self):
        self.add("task")
        self.assertIsNone(vybe.recover_session(self.session, "discard"))
        self.assertIsNone(vybe.PromptSession.load(REPO, ROOT))

    def test_finished_cleanup_failure_does_not_reapply(self):
        self.add("task")
        self.run_chain()
        with patch.object(vybe.shutil, "rmtree", side_effect=OSError("busy")):
            with self.assertRaises(OSError):
                self.session.discard()
        self.assertEqual(self.reload().phase, "finished")
        with patch.object(vybe, "idle_prompt_multiline", return_value="quit"), patch.object(vybe, "apply_result") as apply:
            self.assertEqual(vybe.prompt_loop(REPO, SUPPORT, ROOT, 42), 0)
            apply.assert_not_called()
        self.assertIsNone(vybe.PromptSession.load(REPO, ROOT))

    def test_missing_workspace_is_retained_and_never_silently_recreated(self):
        self.add("task")
        self.run_chain()
        self.fs.directories.remove(ROOT / "working" / ".git")
        self.session = self.reload()
        with self.assertRaises(vybe.CommandError):
            self.run_chain()
        self.assertEqual(self.calls, ["task"])
        self.assertEqual(self.reload().prompts[0].status, "completed")

    def test_recovery_menu_requires_an_explicit_choice(self):
        self.add("task")
        for answer, expected in (("yes", "retry"), ("no", "fresh"), ("discard", "discard"), ("quit", "quit")):
            with self.subTest(answer=answer), patch.object(vybe, "idle_prompt_line", side_effect=["", answer]) as ask:
                self.assertEqual(vybe.prompt_restore_session(REPO, self.session), expected)
                self.assertEqual(ask.call_count, 2)

    def test_live_submission_calls_save_before_acknowledging_queue(self):
        parent = self.add("task")
        state = vybe.PromptQueueState(
            lines=["followup", "", ""], capture_kind="stack", capture_active=True,
            on_queue=lambda action: self.session.add_prompt(action, parent),
        )
        self.assertTrue(vybe.finish_queued_prompt(state))
        self.assertEqual(self.reload().prompts[0].children[0].status, "unprocessed")
        self.assertEqual(state.actions, [vybe.PromptAction("stack", "followup")])

    def test_second_process_cannot_open_a_locked_session(self):
        with patch.object(vybe.fcntl, "flock", side_effect=BlockingIOError):
            with self.assertRaises(vybe.CommandError):
                with vybe.recovery_lock(ROOT):
                    self.fail("lock was incorrectly acquired")


class CodexProcessTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(redirect_stdout(io.StringIO()))
        self.stack.enter_context(patch.object(Path, "unlink"))
        self.stack.enter_context(patch.object(Path, "exists", return_value=False))
        self.stack.enter_context(patch.object(vybe, "build_codex_command", return_value=["codex", "exec", "task"]))
        self.stack.enter_context(patch.object(vybe, "LiveStatus"))
        self.queue_enabled = self.stack.enter_context(patch.object(vybe, "can_queue_input_during_run", return_value=False))
        self.process = MagicMock()
        self.process.pid = 12345
        self.process.stdout.fileno.return_value = 8
        self.process.stdout.readline.return_value = '{"type":"turn.failed"}\n'
        self.process.stdout.read.return_value = ""
        self.process.poll.return_value = 1
        self.process.returncode = 1
        self.popen = self.stack.enter_context(patch.object(vybe.subprocess, "Popen", return_value=self.process))
        self.select = self.stack.enter_context(patch.object(vybe.select, "select", return_value=([8], [], [])))
        self.kill = self.stack.enter_context(patch.object(vybe.os, "killpg"))

    def test_exit_and_json_errors_raise_instead_of_completing_prompt(self):
        for rc, event in ((1, "turn.failed"), (0, "turn.failed"), (0, "error")):
            with self.subTest(rc=rc, event=event):
                self.process.poll.return_value = self.process.returncode = rc
                self.process.stdout.readline.return_value = json.dumps({"type": event}) + "\n"
                with self.assertRaises(vybe.CommandError):
                    vybe.run_codex(SUPPORT, ROOT / "working", "task", lock_fd=42)
        self.assertEqual(self.popen.call_args.kwargs["pass_fds"], (42,))
        self.assertTrue(self.popen.call_args.kwargs["start_new_session"])
        self.process.stdout.close.assert_called()

    def test_transient_error_followed_by_success_is_successful(self):
        self.process.poll.return_value = self.process.returncode = 0
        self.process.stdout.readline.return_value = '{"type":"error","message":"reconnecting"}\n'
        self.process.stdout.read.return_value = '{"type":"turn.completed"}\n'
        vybe.run_codex(SUPPORT, ROOT / "working", "task")

    def test_interrupt_stops_process_and_saves_input_already_captured(self):
        queued = []
        state = vybe.PromptQueueState(lines=["followup"], capture_kind="stack", on_queue=queued.append)
        self.queue_enabled.return_value = True
        self.select.side_effect = KeyboardInterrupt
        self.process.poll.return_value = None
        self.process.wait.side_effect = [subprocess.TimeoutExpired("codex", 5), -9]
        with patch.object(vybe, "PromptQueueState", return_value=state), patch.object(
            vybe, "QueueInputController",
        ), patch.object(vybe.sys, "stdin"):
            with self.assertRaises(KeyboardInterrupt):
                vybe.run_codex(SUPPORT, ROOT / "working", "task", on_queue=queued.append)
        self.assertEqual(queued, [vybe.PromptAction("stack", "followup")])
        self.assertEqual([call.args[1] for call in self.kill.call_args_list], [vybe.signal.SIGTERM, vybe.signal.SIGKILL])
        self.process.stdout.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
