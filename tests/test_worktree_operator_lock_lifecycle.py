"""Execute the operator's published blocks, never a test-only locking algorithm.

Linux integration tests require the installed agent-bash CLI, GNU flock/timeout,
Git and Python. State/helper routing and repositories are disposable; no network
or real provider mutations. Socket barriers establish causal order. All waits
and teardown have deadlines (polling here observes fixtures, not agent turns).
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import select
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[1]
# Explicit override is retained for source-intervention runs; evidence must bind it.
GUIDE = Path(os.environ.get("WORKTREE_OPERATOR_SOURCE", ROOT / "agents/worktree-operator.md")).resolve(strict=True)
DEADLINE = 12


def block(label):
    blocks = re.findall(r"```(?:bash|python)\n(.*?)```", GUIDE.read_text(), re.S)
    return next(text for text in blocks if text.startswith("# " + label + "\n"))


def run(*args, **kwargs):
    return subprocess.run(args, text=True, capture_output=True, timeout=DEADLINE, **kwargs)


def git(repo, *args):
    result = run("git", "-C", str(repo), *args, env=dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1"))
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def until(check, seconds=DEADLINE):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        select.select([], [], [], 0.02)
    pytest.fail("fixture deadline exceeded")


class Barrier:
    def __init__(self, path):
        self.server = socket.socket(socket.AF_UNIX)
        self.server.settimeout(DEADLINE)
        address = "@wt-" + uuid.uuid4().hex
        self.server.bind("\0" + address[1:])
        self.server.listen()
        self.path = address
        self.connections = []
        self.pidfds = []

    def entered(self):
        connection, _ = self.server.accept()
        connection.settimeout(DEADLINE)
        self.connections.append(connection)
        pid = int(connection.recv(100))
        fd = os.pidfd_open(pid)
        self.pidfds.append(fd)
        return connection, fd

    def close(self):
        for fd in self.pidfds:
            if not select.select([fd], [], [], 0)[0]:
                signal.pidfd_send_signal(fd, signal.SIGKILL)
            os.close(fd)
        for connection in self.connections:
            connection.close()
        self.server.close()


def exited(fd):
    return bool(select.select([fd], [], [], 0)[0])


def acquire_now(path):
    with path.open("a") as descriptor:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)


OWNER = '''import json, os, subprocess, sys
result = subprocess.run(["bash", sys.argv[1]], env=dict(os.environ, lock_owner_pid=str(os.getpid())), capture_output=True, text=True)
print(result.stdout, end="", flush=True)
print(result.stderr, end="", file=sys.stderr, flush=True)
while sys.stdin.buffer.read(1) == b"c":
    job = json.loads(result.stdout)
    cancel = subprocess.run(["agent-bash", "cancel", job["handle"]], capture_output=True, text=True)
    print(json.dumps(dict(cancel_rc=cancel.returncode, stderr=cancel.stderr)), flush=True)
'''
WORKER = r'''import os, pathlib, signal, socket, sys
signal.signal(signal.SIGTERM, signal.SIG_IGN)
signal.signal(signal.SIGINT, signal.SIG_IGN)
sock = socket.socket(socket.AF_UNIX)
sock.connect("\0" + sys.argv[1][1:])
sock.sendall(str(os.getpid()).encode())
action = sock.recv(10)
if action == b"mutate":
    pathlib.Path(os.environ["repo_root"], "mutation").write_text("committed fixture effect")
    sys.exit(0)
sys.exit(int(action or b"0"))
'''


class Runtime:
    def __init__(self, tmp_path, repo):
        for executable in ("agent-bash", "flock", "timeout"):
            assert shutil.which(executable), f"required integration dependency: {executable}"
        self.path, self.repo = tmp_path, repo
        binary_dir = tmp_path / "bin"
        binary_dir.mkdir()
        shutil.copy2(shutil.which("agent-bash"), binary_dir / "agent-bash")
        helper = binary_dir / "fixture-helper"
        helper.write_text("#!/bin/sh\nif [ \"$1\" = session ] && [ \"$2\" = of-pid ]; then\n"
                          "  printf '%s\\n' '{\"found\":true,\"invocation_uuid\":\"11111111-1111-4111-8111-111111111111\",\"session_id\":\"infa949-fixture\"}'\nfi\n")
        helper.chmod(0o700)
        (binary_dir / "agent-bash.toml").write_text(
            f'state_root = "{tmp_path / "state"}"\nagent_runner_bin = "{helper}"\n')
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith(("AGENT_BASH_", "OULIPOLY_"))}
        self.env.update(PATH=str(binary_dir) + os.pathsep + self.env["PATH"], XDG_STATE_HOME=str(tmp_path / "state"),
                        AGENT_BASH_AGENT_RUNNER_BIN=str(helper),
                        AGENT_BASH_OWNER_SESSION_ID="infa949-fixture",
                        AGENT_BASH_OWNER_INVOCATION_UUID="11111111-1111-4111-8111-111111111111",
                        OULIPOLY_PARENT_INVOCATION='{"source":"opencode","id":"11111111-1111-4111-8111-111111111111"}',
                        repo_root=str(repo), GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1",
                        lock_acquire_seconds="1", lock_hold_seconds="6", lock_cleanup_seconds="3")
        self.lock_script = tmp_path / "lock.sh"
        self.lock_script.write_text(block("worktree-lock-section-v1"))
        self.admission = tmp_path / "admission.sh"
        self.admission.write_text(block("worktree-lock-admission-v1"))
        self.owner_script = tmp_path / "owner.py"
        self.owner_script.write_text(OWNER)
        self.worker = tmp_path / "worker.py"
        self.worker.write_text(WORKER)
        self.owners, self.handles = [], []

    def start(self, body, **limits):
        index = len(self.owners)
        section = self.path / f"section-{index}.sh"
        section.write_text(body)
        env = dict(self.env, section_script=str(section), lock_section_path=str(self.lock_script), **limits)
        acted = [self.lock_script, self.admission, self.owner_script, self.worker, section,
                 self.path / "bin/agent-bash", self.path / "bin/agent-bash.toml", self.path / "bin/fixture-helper",
                 lock_path(self.repo).parent / "config"]
        acted += [self.path / name for name in ("publication.py", "effects.py", "remove.py", "prepare.sh", "provider.json", "transport.json", "bin/gh", "bin/git")
                  if (self.path / name).exists()]
        before = dict(command=[sys.executable, str(self.owner_script), str(self.admission)],
                      guide=str(GUIDE), guide_sha256=hashlib.sha256(GUIDE.read_bytes()).hexdigest(),
                      files={str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in acted},
                      environment={key: value for key, value in env.items()
                                   if key in ("PATH", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM")
                                   or key not in os.environ or key.startswith(("lock_", "AGENT_BASH_", "OULIPOLY_"))})
        material = self.path / f"material-{index}"
        material.mkdir()
        for number, path in enumerate(acted):
            shutil.copyfile(path, material / f"{number}-{path.name}")
        (self.path / f"execution-{index}.json").write_text(json.dumps(before, indent=2))
        owner = subprocess.Popen([sys.executable, str(self.owner_script), str(self.admission)],
                                 env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True)
        self.owners.append(owner)
        assert select.select([owner.stdout], [], [], DEADLINE)[0], "no admission response"
        line = owner.stdout.readline()
        assert line, owner.stderr.read()
        admission = json.loads(line)
        assert Path(admission["state_dir"]).is_relative_to(self.path), admission
        assert admission.get("dispatch_state") != "registration-outcome-unknown", admission
        self.handles.append(admission["handle"])
        (self.path / f"admission-{index}.json").write_text(json.dumps(admission, indent=2))
        meta = json.loads(Path(admission["meta"]).read_text())
        if "--cancel-on-owner-exit" in self.admission.read_text():
            assert admission["delivery_mode"] == "sync"
            assert meta["cancel_owner"]["pid"] == owner.pid
            assert meta["cancel_owner"]["starttime_ticks"] > 0
            assert meta["cancel_owner"]["boot_id"]
        return owner, admission

    def cli(self, *args):
        result = run("agent-bash", *args, env=self.env)
        assert result.returncode == 0, result.stderr
        return result.stdout

    def terminal(self, admission):
        def observed():
            status = self.cli("status", "--observe-only", "--full", admission["handle"])
            assert not status.startswith("ERROR "), status
            return status if status.startswith("DONE ") else None
        status = until(observed)
        (self.path / (admission["handle"] + "." + uuid.uuid4().hex + ".terminal.txt")).write_text(status)
        return status

    def worker_body(self, barrier):
        return f'exec "{sys.executable}" "{self.worker}" "{barrier.path}"\n'

    def close(self):
        for owner in self.owners:
            if owner.poll() is None:
                owner.kill()
            owner.wait(timeout=DEADLINE)
        for handle in self.handles:
            self.terminal({"handle": handle})


@pytest.fixture
def repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "Fixture")
    git(repo, "config", "user.email", "fixture@example.invalid")
    git(repo, "-c", "commit.gpgsign=false", "commit", "--allow-empty", "-m", "base")
    return repo


@pytest.fixture
def runtime(tmp_path, repo):
    fixture = Runtime(tmp_path, repo)
    try:
        yield fixture
    finally:
        fixture.close()


@pytest.fixture
def barrier(tmp_path):
    fixture = Barrier(tmp_path / "barrier.sock")
    try:
        yield fixture
    finally:
        fixture.close()


def lock_path(repo):
    return Path(git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir")) / "worktree-operator.lock"


@pytest.mark.parametrize("value", ["0", "-1", "1.5", "nan", "301", "01", "1;true"])
def test_invalid_acquire_limits_do_not_execute(runtime, value):
    _, job = runtime.start('touch "$repo_root/mutation"', lock_acquire_seconds=value)
    assert "rc=64 " in runtime.terminal(job)
    assert not (runtime.repo / "mutation").exists()
    assert not lock_path(runtime.repo).exists()


def test_bounded_acquire_has_no_late_waiter(runtime):
    path = lock_path(runtime.repo)
    with path.open("a") as holder:
        fcntl.flock(holder, fcntl.LOCK_EX)
        start = time.monotonic()
        _, job = runtime.start('touch "$repo_root/mutation"')
        assert "rc=75 " in runtime.terminal(job)
        assert time.monotonic() - start < 5
        assert not (runtime.repo / "mutation").exists()
    acquire_now(path)
    assert not (runtime.repo / "mutation").exists()


@pytest.mark.parametrize("exit_code", [0, 1, 42])
def test_success_and_mechanical_error_release(runtime, barrier, exit_code):
    _, job = runtime.start(runtime.worker_body(barrier))
    connection, child = barrier.entered()
    with pytest.raises(BlockingIOError):
        acquire_now(lock_path(runtime.repo))
    connection.sendall(b"mutate" if exit_code == 0 else str(exit_code).encode())
    assert f"rc={exit_code} " in runtime.terminal(job)
    assert (runtime.repo / "mutation").exists() == (exit_code == 0)
    assert exited(child)
    acquire_now(lock_path(runtime.repo))


@pytest.mark.parametrize("how", ["cli-cancel", "SIGINT", "SIGTERM", "SIGKILL", "exit"])
def test_owner_interruption_retires_term_ignoring_work(runtime, barrier, how):
    owner, job = runtime.start(runtime.worker_body(barrier))
    _, child = barrier.entered()
    if how == "cli-cancel":
        owner.stdin.write("c")
        owner.stdin.flush()
        assert select.select([owner.stdout], [], [], DEADLINE)[0]
        assert json.loads(owner.stdout.readline())["cancel_rc"] == 0
    elif how == "exit":
        owner.stdin.write("x")
        owner.stdin.flush()
    else:
        owner.send_signal(getattr(signal, how))
    # The worker ignores TERM and INT. Exclusion must remain until it exits.
    def retired_without_unlock():
        if exited(child):
            return True
        try:
            acquire_now(lock_path(runtime.repo))
        except BlockingIOError:
            return False
        # The worker may exit between the pidfd check and the independent probe.
        assert exited(child), "exclusion released before worker retirement"
        return True
    until(retired_without_unlock, 6)
    status = runtime.terminal(job)
    assert "reason=owner-exit" in status or "reason=cancel-request" in status
    assert "rc=0 " not in status
    assert not (runtime.repo / "mutation").exists()
    acquire_now(lock_path(runtime.repo))


def test_hold_deadline_does_not_unlock_live_worker(runtime, barrier):
    _, job = runtime.start(runtime.worker_body(barrier), lock_hold_seconds="1", lock_cleanup_seconds="1")
    _, child = barrier.entered()
    def retired_without_unlock():
        if exited(child):
            return True
        try:
            acquire_now(lock_path(runtime.repo))
        except BlockingIOError:
            return False
        # The worker may exit between the pidfd check and the independent probe.
        assert exited(child), "exclusion released before worker retirement"
        return True
    until(retired_without_unlock, 5)
    assert re.search(r"rc=(124|137) ", runtime.terminal(job))
    assert not (runtime.repo / "mutation").exists()
    acquire_now(lock_path(runtime.repo))


def test_unrelated_holder_survives_waiter_owner_exit(runtime):
    path = lock_path(runtime.repo)
    with path.open("a") as holder:
        fcntl.flock(holder, fcntl.LOCK_EX)
        owner, job = runtime.start('touch "$repo_root/mutation"', lock_acquire_seconds="6")
        owner.kill()
        assert "reason=owner-exit" in runtime.terminal(job)
        with pytest.raises(BlockingIOError):
            acquire_now(path)
    acquire_now(path)
    assert not (runtime.repo / "mutation").exists()


GH = r'''#!/usr/bin/env python3
import json, os, pathlib, signal, socket, sys
path = pathlib.Path(os.environ["FAKE_PROVIDER"])
state = json.loads(path.read_text())
args = sys.argv[1:]
with open(str(path) + ".calls", "a") as output:
    output.write(json.dumps(args) + "\n")
mode = state.get("mode", "normal")

def save():
    path.write_text(json.dumps(state))

def effect():
    with open(os.environ["PUBLICATION_EFFECTS"], "a") as output:
        output.write(json.dumps(dict(tool="gh", argv=args)) + "\n")

if args[:2] == ["repo", "view"]:
    assert args == ["repo", "view", "fixture/project", "--json", "id,nameWithOwner,url"]
    print(json.dumps(state["repo"]))
elif args[:2] == ["pr", "list"]:
    with open(str(path) + ".queries", "a") as output:
        output.write(json.dumps(args) + "\n")
    expected = state["query"].copy()
    if args[5] == "all":
        expected[5] = "all"
    assert args == expected, "candidate query mismatch: " + repr(args)
    if args[5] == "all" and mode == "diagnostic-failed":
        sys.exit(2)
    print(json.dumps(state["prs"]))
elif args[:2] == ["pr", "create"]:
    assert args == ["pr", "create", "--repo", "fixture/project", "--draft", "--head", "topic",
                    "--base", "main", "--title", "Title", "--body-file", state["body_file"]]
    assert pathlib.Path(state["body_file"]).read_text() == "Body"
    state["prs"].append(state["new_pr"])
    save()
    effect()
    if mode == "create-paused":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        sock = socket.socket(socket.AF_UNIX)
        sock.connect("\0" + state["barrier"][1:])
        sock.sendall(str(os.getpid()).encode())
        sock.recv(1)
    url = state["new_pr"]["url"]
    outputs = {"create-empty": "", "create-malformed": "created", "create-multiple": url + "\n" + url,
               "create-foreign": "https://github.com/other/project/pull/1", "diagnostic-failed": ""}
    print(outputs.get(mode, url))
    sys.exit(1 if mode == "create-error" else 0)
elif args[:2] == ["pr", "view"]:
    assert args == ["pr", "view", state["new_pr"]["url"], "--repo", "fixture/project", "--json", state["query"][-1]]
    state["views"] = state.get("views", 0) + 1
    save()
    row = json.loads(json.dumps(state["prs"][0]))
    if mode == "view-failed" or (state["views"] > 1 and mode == "closed-read-failed"):
        sys.exit(2)
    if mode == "view-malformed":
        print("not json")
        sys.exit(0)
    if mode.startswith("verify-"):
        row.update(state["view_override"])
    elif mode in ["close-error", "close-error-closed", "close-noeffect", "closed-read-failed", "closed-other", "normal-reconcile"] and state["views"] == 1:
        row["headRefOid"] = "0" * 40
    if state["views"] > 1 and mode == "closed-other":
        row.update(url="https://github.com/fixture/project/pull/2", number=2)
    print(json.dumps(row))
elif args[:2] == ["pr", "close"]:
    assert args == ["pr", "close", state["new_pr"]["url"], "--repo", "fixture/project", "--comment",
                    "Closed automatically after open-pr postcondition verification failed."]
    if mode not in ["close-error", "close-noeffect"]:
        state["prs"][0]["state"] = "CLOSED"
    save()
    effect()
    sys.exit(1 if mode in ["close-error", "close-error-closed"] else 0)
else:
    raise SystemExit("unexpected provider call: " + repr(args))
'''

GIT = r'''#!/usr/bin/env python3
import json, os, pathlib, subprocess, sys
args = sys.argv[1:]
config = json.loads(pathlib.Path(os.environ["LOCAL_TRANSPORT"]).read_text())
actual = args.copy()
operation = args[2] if args[:1] == ["-C"] else args[0]
if operation in ["push", "ls-remote"]:
    position = 3
    target = args[position]
    with open(os.environ["LOCAL_TRANSPORT"] + ".calls", "a") as output:
        output.write(json.dumps(dict(argv=args, target=target)) + "\n")
    if target not in config["urls"]:
        raise SystemExit("unmapped publication target: " + target)
    actual[position] = config["urls"][target]
result = subprocess.run([config["git"], *actual], text=True, capture_output=True, close_fds=False)
if operation in ["push", "ls-remote"]:
    with open(os.environ["LOCAL_TRANSPORT"] + ".results", "a") as output:
        output.write(json.dumps(dict(argv=args, acted_argv=actual, rc=result.returncode,
                                     stdout=result.stdout, stderr=result.stderr)) + "\n")
if operation == "push":
    with open(os.environ["PUBLICATION_EFFECTS"], "a") as output:
        output.write(json.dumps(dict(tool="git", argv=args, rc=result.returncode)) + "\n")
if operation == "ls-remote" and config.get("readback"):
    print(config["readback"]["stdout"], end="")
    sys.exit(config["readback"]["rc"])
print(result.stdout, end="")
print(result.stderr, end="", file=sys.stderr)
sys.exit(result.returncode)
'''


class Publication:
    def __init__(self, runtime):
        self.runtime, self.repo, self.path = runtime, runtime.repo, runtime.path
        self.remote = self.path / "remote.git"
        git(self.path, "init", "--bare", str(self.remote))
        git(self.repo, "remote", "add", "origin", str(self.remote))
        git(self.repo, "push", "origin", "main")
        git(self.repo, "remote", "set-url", "--push", "origin", "https://github.com/fixture/project.git")
        self.worktrees = self.path / "worktrees"
        self.target = self.worktrees / "topic"
        git(self.repo, "worktree", "add", "-b", "topic", str(self.target))
        git(self.target, "-c", "commit.gpgsign=false", "commit", "--allow-empty", "-m", "topic head")
        self.provider_path = self.path / "provider.json"
        self.provider = dict(repo=dict(id="repo-id", nameWithOwner="fixture/project",
                                      url="https://github.com/fixture/project"), prs=[],
                             query=["pr", "list", "--repo", "fixture/project", "--state", "open",
                                    "--head", "topic", "--base", "main", "--json",
                                    "url,number,state,isDraft,baseRefName,baseRefOid,headRefName,headRefOid,headRepository,headRepositoryOwner"])
        self.write_provider()
        gh = self.path / "bin/gh"
        gh.write_text(GH)
        gh.chmod(0o700)
        self.guard = self.path / "publication.py"
        self.guard.write_text(block("worktree-publication-identity-v1"))
        self.snapshot = self.path / "snapshot.json"
        self.output = self.path / "decision.json"
        self.effects = self.path / "publication-effects"
        self.engine = self.path / "effects.py"
        self.engine.write_text(block("worktree-publication-effects-v1"))
        self.result = self.path / "publication-result.json"
        self.other_remote = self.path / "other.git"
        git(self.path, "init", "--bare", str(self.other_remote))
        self.transport = self.path / "transport.json"
        self.transport.write_text(json.dumps(dict(git=shutil.which("git"), urls={
            "https://github.com/fixture/project.git": str(self.remote),
            "https://github.com/fixture/other.git": str(self.other_remote)})))
        boundary = self.path / "bin/git"
        boundary.write_text(GIT)
        boundary.chmod(0o700)
        self.writer_dir = self.path / "writer"
        self.writer_dir.mkdir()
        (self.writer_dir / "pr-body.md").write_text("Body")
        (self.writer_dir / "pr-body.md.title").write_text("Title")
        runtime.env.update(FAKE_PROVIDER=str(self.provider_path), publication_identity_script=str(self.guard),
                           snapshot=str(self.snapshot), worktrees_root=str(self.worktrees), name="topic",
                           branch_name="topic", base_branch="main", repo_slug="fixture/project",
                           writer_dir=str(self.writer_dir), writer_rc="0", writer_log_rc="0",
                           publication_effects_script=str(self.engine), publication_result_path=str(self.result),
                           LOCAL_TRANSPORT=str(self.transport), PUBLICATION_EFFECTS=str(self.effects))
        self.provider["body_file"] = str(self.writer_dir / "pr-body.md")
        self.write_provider()

    def write_provider(self):
        self.provider_path.write_text(json.dumps(self.provider))

    def capture(self):
        body = ('python3 "$publication_identity_script" capture "$snapshot" "$repo_root" '
                '"$worktrees_root" "$name" "$branch_name" "$base_branch" "$repo_slug" '
                f'> "{self.output}"\n')
        _, job = self.runtime.start(body)
        assert "rc=0 " in self.runtime.terminal(job)
        result = json.loads(self.output.read_text())
        self.provider["new_pr"] = self.exact_pr()
        self.write_provider()
        return result

    def start_publish(self):
        body = (block("worktree-writer-output-v1") + block("worktree-publication-functions-v1")
                + block("worktree-publication-dispatch-v1"))
        return self.runtime.start(body)

    def publish(self):
        _, job = self.start_publish()
        return self.runtime.terminal(job)

    def events(self):
        return [json.loads(line) for line in self.effects.read_text().splitlines()] if self.effects.exists() else []

    def observed(self):
        return json.loads(self.result.read_text())

    def calls(self):
        return [json.loads(line) for line in Path(str(self.provider_path) + ".calls").read_text().splitlines()]

    def exact_pr(self):
        identity = json.loads(self.snapshot.read_text())
        return dict(url="https://github.com/fixture/project/pull/1", number=1, state="OPEN", isDraft=True,
                    baseRefName="main", baseRefOid=identity["base_sha"],
                    headRefName="topic", headRefOid=identity["head_sha"],
                    headRepository=dict(nameWithOwner="fixture/project", name="project"),
                    headRepositoryOwner=dict(login="fixture"))


@pytest.fixture
def publication(runtime):
    return Publication(runtime)


def test_writer_turn_is_unlocked_and_unchanged_tuple_publishes(publication, barrier):
    p = publication
    assert p.capture()["action"] == "create"
    before = p.snapshot.read_bytes()
    # A real separate writer process pauses on a socket outside lock admission.
    writer = subprocess.Popen([sys.executable, str(p.runtime.worker), str(barrier.path)])
    try:
        connection, writer_pid = barrier.entered()
        _, other = p.runtime.start("true")
        assert "rc=0 " in p.runtime.terminal(other)
        assert not exited(writer_pid), "writer barrier was not concurrent with second lock use"
        connection.sendall(b"0")
        writer.wait(timeout=DEADLINE)
        assert "rc=0 " in p.publish()
        assert_publication_transport(p)
        assert p.snapshot.read_bytes() == before
    finally:
        if writer.poll() is None:
            writer.kill()
        writer.wait(timeout=DEADLINE)


def change_identity(p, change):
    if change == "head":
        git(p.target, "-c", "commit.gpgsign=false", "commit", "--allow-empty", "-m", "new head")
    elif change == "base":
        git(p.repo, "-c", "commit.gpgsign=false", "commit", "--allow-empty", "-m", "new base")
        git(p.repo, "push", str(p.remote), "main")
    elif change == "branch":
        git(p.target, "checkout", "-b", "changed")
    elif change == "registration":
        git(p.repo, "worktree", "lock", "--reason", "changed registration", str(p.target))
    elif change == "missing-registration":
        git(p.repo, "worktree", "move", str(p.target), str(p.worktrees / "moved"))
    elif change == "dirty":
        (p.target / "untracked").write_text("dirty")
    elif change == "push-url":
        git(p.repo, "remote", "set-url", "--push", "origin", "git@github.com:fixture/project.git")
    elif change == "foreign-push-url":
        git(p.repo, "remote", "set-url", "--push", "origin", "https://github.com/other/project.git")
    elif change == "fetch-url":
        alias = p.path / "alias.git"
        alias.symlink_to(p.remote, target_is_directory=True)
        git(p.repo, "remote", "set-url", "origin", str(alias))
    elif change == "provider-repository":
        p.provider["repo"]["id"] = "different-repository-id"
        p.write_provider()
    elif change == "base-ref-name":
        git(p.remote, "branch", "other-base", "main")
        p.runtime.env["base_branch"] = "other-base"
    elif change == "head-ref-name":
        git(p.target, "branch", "-m", "other-head")
        p.runtime.env["branch_name"] = "other-head"
    elif change == "root":
        p.runtime.env["repo_root"] = str(p.target)
    else:
        raise AssertionError(change)


@pytest.mark.parametrize("change", ["head", "base", "branch", "registration", "missing-registration", "dirty",
                                    "push-url", "foreign-push-url", "fetch-url", "provider-repository",
                                    "base-ref-name", "head-ref-name", "root"])
def test_writer_boundary_identity_drift_blocks_publication(publication, change):
    p = publication
    p.capture()
    before = p.snapshot.read_bytes()
    change_identity(p, change)
    result = p.publish()
    assert "rc=76 " in result, result
    assert not p.effects.exists()
    assert p.snapshot.read_bytes() == before
    acquire_now(lock_path(p.repo))


@pytest.mark.parametrize("race", ["exact", "ambiguous", "foreign-head", "foreign-target", "base-oid", "head-oid", "not-draft", "closed"])
def test_writer_boundary_provider_race_never_duplicates(publication, race):
    p = publication
    p.capture()
    row = p.exact_pr()
    p.provider["prs"] = [row]
    if race == "ambiguous":
        p.provider["prs"].append(dict(row, number=2, url="https://github.com/fixture/project/pull/2"))
    elif race == "foreign-head":
        row["headRepositoryOwner"]["login"] = "other"
    elif race == "foreign-target":
        row["url"] = "https://github.com/other/project/pull/1"
    elif race == "base-oid":
        row["baseRefOid"] = "0" * 40
    elif race == "head-oid":
        row["headRefOid"] = "0" * 40
    elif race == "not-draft":
        row["isDraft"] = False
    elif race == "closed":
        row["state"] = "CLOSED"
    p.write_provider()
    result = p.publish()
    if race == "exact":
        assert "rc=0 " in result
        assert not p.effects.exists()
        assert p.observed()["status"] == "VERIFIED"
        assert p.calls()[-1][:3] == ["pr", "view", row["url"]]
    else:
        assert "rc=76 " in result
        assert not p.effects.exists()
    acquire_now(lock_path(p.repo))


@pytest.mark.parametrize("failure", ["nonzero", "log-error", "missing", "empty", "symlink"])
def test_writer_failure_has_no_publication_or_lock_waiter(publication, failure):
    p = publication
    p.capture()
    body = p.writer_dir / "pr-body.md"
    if failure == "nonzero":
        p.runtime.env["writer_rc"] = "1"
    elif failure == "log-error":
        p.runtime.env["writer_log_rc"] = "1"
    elif failure == "missing":
        body.unlink()
    elif failure == "empty":
        body.write_text("")
    elif failure == "symlink":
        body.unlink()
        body.symlink_to(p.snapshot)
    # Pre-admission validation is the same published block used in section B.
    validation = p.path / "validate-writer.sh"
    validation.write_text(block("worktree-writer-output-v1"))
    result = run("bash", str(validation), env=p.runtime.env)
    assert result.returncode == 65
    assert not p.effects.exists()
    assert len(p.runtime.handles) == 1
    acquire_now(lock_path(p.repo))


@pytest.mark.parametrize("pattern", ["marker-holder", "unbounded-waiter"])
def test_retained_unsafe_shapes_outlive_owner_but_are_contained(runtime, barrier, pattern):
    # Retained RCA shapes, run only behind an independent fixture deadline.
    # The sockets instrument acquisition without changing either lock lifetime.
    path = lock_path(runtime.repo)
    runtime.admission.write_text(block("worktree-lock-admission-v1")
                                 .replace("--delivery sync", "--delivery async")
                                 .replace('--cancel-on-owner-exit --owner-pid "$lock_owner_pid"', ""))
    old = runtime.path / "retained.sh"
    notify = runtime.worker_body(barrier).replace("exec ", "")
    if pattern == "marker-holder":
        old.write_text(f'exec 9>"{path}"\nflock -x 9\n' + notify +
                       f'touch "{runtime.path}/lock.ready"\nwhile [ ! -e "{runtime.path}/lock.release" ]; do sleep 1; done\n')
    else:
        acquired = runtime.path / "old-acquired.sh"
        acquired.write_text(notify + f'touch "{runtime.path}/lock-state"\nsleep 1200\n')
        old.write_text(f'flock -x "{path}" bash "{acquired}"\n')
    runtime.lock_script.write_text(f'exec timeout --kill-after=1s 5s bash "{old}"\n')
    holder = path.open("a")
    try:
        if pattern == "unbounded-waiter":
            fcntl.flock(holder, fcntl.LOCK_EX)
        owner, job = runtime.start("true")
        if pattern == "marker-holder":
            connection, child = barrier.entered()
            connection.sendall(b"0")
        owner.kill()
        owner.wait(timeout=DEADLINE)
        # Owner death does NOT cancel the old async lifetime.
        assert runtime.cli("status", "--observe-only", job["handle"]).startswith("RUNNING ")
        if pattern == "unbounded-waiter":
            fcntl.flock(holder, fcntl.LOCK_UN)
            connection, child = barrier.entered()  # waiter acquired AFTER abandonment
            connection.sendall(b"0")
        with pytest.raises(BlockingIOError):
            acquire_now(path)
        runtime.cli("cancel", job["handle"])
        assert "reason=cancel-request" in runtime.terminal(job)
    finally:
        holder.close()
        runtime.cli("cancel", job["handle"])
        runtime.terminal(job)
    acquire_now(path)


def test_identity_guard_subprocess_retains_exclusion_on_owner_loss(publication, barrier):
    p = publication
    # Exercise the guard's real subprocess boundary, not only a direct exec child.
    (p.path / "bin/gh").write_text(
        f'#!/bin/sh\nexec "{sys.executable}" "{p.runtime.worker}" "{barrier.path}"\n')
    body = ('python3 "$publication_identity_script" capture "$snapshot" "$repo_root" '
            '"$worktrees_root" "$name" "$branch_name" "$base_branch" "$repo_slug"\n')
    owner, job = p.runtime.start(body)
    _, child = barrier.entered()
    owner.kill()
    path = lock_path(p.repo)
    def retired_without_unlock():
        if exited(child):
            return True
        try:
            acquire_now(path)
        except BlockingIOError:
            return False
        assert exited(child), "guard dropped lock FD across a live subprocess boundary"
        return True
    until(retired_without_unlock, 6)
    assert "reason=owner-exit" in p.runtime.terminal(job)
    assert not p.effects.exists()
    acquire_now(path)


class Removal:
    def __init__(self, runtime):
        self.runtime, self.repo, self.path = runtime, runtime.repo, runtime.path
        (self.repo / "tracked").write_text("retain\n")
        git(self.repo, "add", "tracked")
        git(self.repo, "-c", "commit.gpgsign=false", "commit", "-m", "tracked fixture")
        self.remote = self.path / "remote.git"
        git(self.path, "init", "--bare", str(self.remote))
        git(self.repo, "remote", "add", "origin", str(self.remote))
        git(self.repo, "push", "origin", "main")
        git(self.repo, "fetch", "origin", "main")
        self.worktrees = self.path / "worktrees"
        self.target = self.worktrees / "topic"
        git(self.repo, "worktree", "add", "-b", "topic", str(self.target))
        self.identity_script = self.path / "remove.py"
        self.identity_script.write_text(block("worktree-remove-identity-v1"))
        runtime.env.update(remove_identity_script=str(self.identity_script),
                           worktrees_root=str(self.worktrees), name="topic",
                           branch_name="topic", base_branch="main")
        self.prepare_script = self.path / "prepare.sh"
        self.prepare_script.write_text(block("worktree-remove-prepare-v1") +
                                      "python3 -c 'import json,os; print(json.dumps({k: os.environ[k] for k in [\"remove_identity\", \"worktree_path\"]}))'\n")

    def prepare(self):
        record = self.path / ("prepare-" + uuid.uuid4().hex)
        before = dict(command=["bash", "-euo", "pipefail", str(self.prepare_script)],
                      files={str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in (self.prepare_script, self.identity_script, lock_path(self.repo).parent / "config")})
        record.with_suffix(".before.json").write_text(json.dumps(before, indent=2))
        result = run("bash", "-euo", "pipefail", str(self.prepare_script), env=self.runtime.env)
        record.with_suffix(".result.json").write_text(
            json.dumps(dict(rc=result.returncode, stdout=result.stdout, stderr=result.stderr)))
        if result.returncode == 0:
            self.runtime.env.update(json.loads(result.stdout))
        return result

    def remove(self):
        _, job = self.runtime.start(block("worktree-remove-section-v1"))
        return self.runtime.terminal(job)

    def state(self):
        common = lock_path(self.repo).parent
        return dict(refs=git(self.repo, "show-ref"), fetch_head=(common / "FETCH_HEAD").read_bytes(),
                    registration=git(self.repo, "worktree", "list", "--porcelain", "-z"),
                    head=git(self.target, "rev-parse", "HEAD"),
                    status=git(self.target, "--no-optional-locks", "status", "--porcelain=v1", "-z"),
                    index=Path(git(self.target, "rev-parse", "--git-path", "index")).read_bytes())

    def advance_remote(self):
        git(self.repo, "-c", "commit.gpgsign=false", "commit", "--allow-empty", "-m", "new base")
        git(self.repo, "push", str(self.remote), "main")
        assert git(self.remote, "rev-parse", "main") != git(self.repo, "rev-parse", "refs/remotes/origin/main")


@pytest.fixture
def removal(runtime):
    return Removal(runtime)


def test_remove_acquisition_timeout_never_fetches_or_mutates(removal):
    r = removal
    r.advance_remote()
    # A stat-stale but content-clean tracked file must not refresh the index pre-lock.
    tracked = r.target / "tracked"
    stamp = tracked.stat().st_mtime_ns + 2_000_000_000
    os.utime(tracked, ns=(stamp, stamp))
    before = r.state()
    path = lock_path(r.repo)
    with path.open("a") as holder:
        fcntl.flock(holder, fcntl.LOCK_EX)
        assert r.prepare().returncode == 0
        start = time.monotonic()
        assert "rc=75 " in r.remove()
        assert time.monotonic() - start < 5
        assert r.state() == before
    acquire_now(path)
    assert r.target.is_dir()
    assert r.state() == before


def test_remove_fetches_fresh_base_and_verifies_both_postconditions(removal):
    r = removal
    r.advance_remote()
    head = git(r.target, "rev-parse", "HEAD")
    assert r.prepare().returncode == 0
    assert "rc=0 " in r.remove()
    assert not r.target.exists()
    assert str(r.target) not in git(r.repo, "worktree", "list", "--porcelain")
    assert git(r.repo, "rev-parse", "refs/remotes/origin/main") == git(r.remote, "rev-parse", "main")
    assert git(r.repo, "rev-parse", "refs/heads/topic") == head
    acquire_now(lock_path(r.repo))


@pytest.mark.parametrize("change", ["dirty", "head", "branch", "registration", "missing-registration"])
def test_remove_identity_change_refuses_removal(removal, change):
    r = removal
    assert r.prepare().returncode == 0
    change_identity(r, change)
    assert "rc=65 " in r.remove()
    assert (r.target if change != "missing-registration" else r.worktrees / "moved").exists()
    acquire_now(lock_path(r.repo))


def test_remove_dirty_preparation_cannot_admit(removal):
    r = removal
    (r.target / "untracked").write_text("retain")
    before = r.state()
    result = r.prepare()
    assert result.returncode == 65
    assert "dirty-worktree" in result.stderr
    assert not r.runtime.handles
    assert r.state() == before


@pytest.mark.parametrize("field", ["repo", "state", "head", "base", "json"])
def test_provider_oracle_rejects_wrong_candidate_query(publication, field):
    p = publication
    p.capture()
    p.provider["prs"] = [p.exact_pr()]
    p.write_provider()
    before = p.snapshot.read_bytes()
    old = {"repo": '"--repo", identity["repo_slug"]',
           "state": '"--state", "open"', "head": '"--head", identity["branch"]',
           "base": '"--base", identity["base_branch"]', "json": '"--json", fields'}[field]
    new = '"--' + field + '", "unrelated"'
    original = p.guard.read_text()
    assert original.count(old) == 1
    p.guard.write_text(original.replace(old, new))
    assert "rc=76 " in p.publish()
    assert not p.effects.exists()
    assert p.snapshot.read_bytes() == before
    queries = [json.loads(line) for line in Path(str(p.provider_path) + ".queries").read_text().splitlines()]
    assert queries[0] == p.provider["query"]
    wrong = p.provider["query"].copy()
    wrong[wrong.index("--" + field) + 1] = "unrelated"
    assert queries == [p.provider["query"], wrong]
    acquire_now(lock_path(p.repo))


def assert_publication_transport(p):
    identity = json.loads(p.snapshot.read_text())
    events = p.events()
    assert [event['tool'] for event in events] == ['git', 'gh']
    assert events[0]['argv'] == ['-C', str(p.target), 'push', identity['push_url'],
                                 identity['head_ref'] + ':' + identity['head_ref']]
    assert events[0]['rc'] == 0
    assert events[1]['argv'] == ['pr', 'create', '--repo', identity['repo_slug'], '--draft',
                                 '--head', identity['branch'], '--base', identity['base_branch'],
                                 '--title', 'Title', '--body-file', str(p.writer_dir / 'pr-body.md')]
    assert git(p.remote, 'rev-parse', 'refs/heads/topic') == identity['head_sha']
    assert git(p.remote, 'rev-parse', 'refs/heads/main') == identity['base_sha']
    assert git(p.remote, 'for-each-ref', '--format=%(refname)') == 'refs/heads/main\nrefs/heads/topic'
    assert git(p.other_remote, 'for-each-ref', '--format=%(refname)') == ''
    readbacks = [json.loads(line) for line in Path(str(p.transport) + '.results').read_text().splitlines()]
    assert readbacks[1]['argv'] == ['ls-remote', '--exit-code', '--refs', identity['push_url'], identity['head_ref']]
    assert readbacks[1]['stdout'] == identity['head_sha'] + '\t' + identity['head_ref'] + '\n'
    assert p.observed()['status'] == 'VERIFIED'
    assert p.observed()['observed_identity'] == p.exact_pr()
    assert p.calls()[-1] == ['pr', 'view', p.exact_pr()['url'], '--repo', identity['repo_slug'], '--json', p.provider['query'][-1]]


def set_provider_mode(p, mode, **values):
    p.provider.update(mode=mode, **values)
    p.write_provider()


def test_publication_ignores_ambient_target_and_ref_variables(publication):
    p = publication
    p.capture()
    p.runtime.env.update(push_url='https://github.com/fixture/other.git', worktree_path=str(p.repo),
                         base_sha='0' * 40, head_sha='0' * 40, head_ref='refs/heads/main')
    assert 'rc=0 ' in p.publish()
    assert_publication_transport(p)


@pytest.mark.parametrize('intervention', ['target-url', 'destination-ref', 'source-ref'])
def test_publication_transport_oracle_distinguishes_source_interventions(publication, intervention):
    p = publication
    p.capture()
    old, new = {
        'target-url': ('"push", identity["push_url"]', '"push", "https://github.com/fixture/other.git"'),
        'destination-ref': ('identity["head_ref"] + ":" + identity["head_ref"]', 'identity["head_ref"] + ":refs/heads/other"'),
        'source-ref': ('identity["head_ref"] + ":" + identity["head_ref"]', '"refs/heads/main:" + identity["head_ref"]'),
    }[intervention]
    original = p.engine.read_text()
    assert original.count(old) == 1
    (p.path / 'effects-original.py').write_text(original)
    p.engine.write_text(original.replace(old, new))
    (p.path / 'intervention.json').write_text(json.dumps(dict(
        operation=intervention, original_sha256=hashlib.sha256(original.encode()).hexdigest(),
        acted_sha256=hashlib.sha256(p.engine.read_bytes()).hexdigest(), replaced=old, replacement=new)))
    result = p.publish()
    assert 'rc=77 ' in result
    assert p.observed()['reason'] == 'remote-head-unverified'
    assert p.observed()['mutation_state'] == 'unknown'
    assert not any(call[:2] == ['pr', 'create'] for call in p.calls())
    with pytest.raises(AssertionError):
        assert_publication_transport(p)
    assert len(p.events()) == 1 and p.events()[0]['rc'] == 0
    if intervention == 'target-url':
        assert git(p.other_remote, 'rev-parse', 'topic') == p.exact_pr()['headRefOid']
    elif intervention == 'destination-ref':
        assert git(p.remote, 'rev-parse', 'other') == p.exact_pr()['headRefOid']
    else:
        assert git(p.remote, 'rev-parse', 'topic') == p.exact_pr()['baseRefOid']


@pytest.mark.parametrize('readback', [dict(rc=2, stdout=''), dict(rc=0, stdout=''),
                                    dict(rc=0, stdout='0' * 40 + '\trefs/heads/topic\n'),
                                    dict(rc=0, stdout='malformed\n')])
def test_remote_readback_failure_stops_before_provider_create(publication, readback):
    p = publication
    p.capture()
    transport = json.loads(p.transport.read_text())
    transport['readback'] = readback
    p.transport.write_text(json.dumps(transport))
    assert 'rc=77 ' in p.publish()
    assert p.observed()['reason'] == 'remote-head-unverified'
    assert p.observed()['mutation_state'] == 'unknown'
    assert [event['tool'] for event in p.events()] == ['git']
    assert git(p.remote, 'rev-parse', 'topic') == p.exact_pr()['headRefOid']


@pytest.mark.parametrize('mode', ['create-empty', 'create-malformed', 'create-multiple', 'create-foreign',
                                 'create-error', 'diagnostic-failed'])
def test_unusable_create_output_never_owns_diagnostic_candidates(publication, mode):
    p = publication
    p.capture()
    set_provider_mode(p, mode)
    assert 'rc=77 ' in p.publish()
    observed = p.observed()
    assert observed['reason'] == 'create-outcome-unverified'
    assert observed['mutation_state'] == 'unknown'
    assert 'created_pr_url' not in observed
    assert json.loads(p.provider_path.read_text())['prs'] == [p.exact_pr()]
    expected = p.provider['query'].copy()
    expected[5] = 'all'
    assert p.calls()[-1] == expected
    assert sum(call == expected for call in p.calls()) == 1
    assert not any(call[:2] in [['pr', 'view'], ['pr', 'close']] for call in p.calls())
    assert observed['diagnostic_candidates']['rc'] == (2 if mode == 'diagnostic-failed' else 0)


@pytest.mark.parametrize('mode,mutation_state', [('normal-reconcile', 'reconciled'),
                                                ('close-error', 'unknown'), ('close-error-closed', 'unknown'),
                                                ('close-noeffect', 'unknown'), ('closed-read-failed', 'unknown'),
                                                ('closed-other', 'unknown'), ('view-failed', 'unknown'),
                                                ('view-malformed', 'unknown')])
def test_created_pr_cleanup_requires_owned_close_and_exact_closed_readback(publication, mode, mutation_state):
    p = publication
    p.capture()
    set_provider_mode(p, mode)
    assert 'rc=77 ' in p.publish()
    observed = p.observed()
    assert observed['status'] == 'BLOCKED'
    assert observed['reason'] == 'created-pr-postcondition-unverified'
    assert observed['created_pr_url'] == p.exact_pr()['url']
    assert observed['mutation_state'] == mutation_state
    closes = [call for call in p.calls() if call[:2] == ['pr', 'close']]
    assert len(closes) == 1 and closes[0][2] == observed['created_pr_url']
    assert p.calls()[-1][:3] == ['pr', 'view', observed['created_pr_url']]
    assert git(p.remote, 'rev-parse', 'topic') == p.exact_pr()['headRefOid']
    if mutation_state == 'reconciled':
        proof = observed['reconciliation']
        assert proof['close_result']['rc'] == 0
        assert proof['closed_provider_identity'] == dict(p.exact_pr(), state='CLOSED')
        assert json.loads(p.provider_path.read_text())['prs'] == [dict(p.exact_pr(), state='CLOSED')]


@pytest.mark.parametrize('field,value', [('url', 'https://github.com/other/project/pull/1'), ('number', 2),
                                       ('state', 'CLOSED'), ('isDraft', False), ('baseRefName', 'other'),
                                       ('baseRefOid', '0' * 40), ('headRefName', 'other'), ('headRefOid', '0' * 40),
                                       ('headRepository', dict(nameWithOwner='other/project', name='project')),
                                       ('headRepositoryOwner', dict(login='other'))])
def test_reused_pr_readback_drift_never_closes_or_publishes(publication, field, value):
    p = publication
    p.capture()
    p.provider['prs'] = [p.exact_pr()]
    set_provider_mode(p, 'verify-' + field, view_override={field: value})
    assert 'rc=77 ' in p.publish()
    assert p.observed()['reason'] == 'reused-pr-postcondition-unverified'
    assert p.observed()['mutation_state'] == 'none'
    assert not p.effects.exists()
    assert json.loads(p.provider_path.read_text())['prs'] == [p.exact_pr()]
    assert p.calls()[-1][:3] == ['pr', 'view', p.exact_pr()['url']]


def test_owner_exit_after_provider_effect_retains_unknown_journal(publication, barrier):
    p = publication
    p.capture()
    set_provider_mode(p, 'create-paused', barrier=barrier.path)
    owner, job = p.start_publish()
    _, child = barrier.entered()
    observed = p.observed()
    assert observed['phase'] == 'create' and observed['mutation_state'] == 'unknown'
    assert observed['in_flight'][:3] == ['gh', 'pr', 'create']
    assert json.loads(p.provider_path.read_text())['prs'] == [p.exact_pr()]
    with pytest.raises(BlockingIOError):
        acquire_now(lock_path(p.repo))
    owner.kill()
    status = p.runtime.terminal(job)
    assert 'reason=owner-exit' in status and 'rc=0 ' not in status
    assert exited(child)
    assert p.observed() == observed
    assert p.observed()['status'] == 'IN_PROGRESS'
    assert not any(call[:2] == ['pr', 'close'] for call in p.calls())
    assert git(p.remote, 'rev-parse', 'topic') == p.exact_pr()['headRefOid']
    acquire_now(lock_path(p.repo))


@pytest.mark.parametrize('mode', ['view-failed', 'view-malformed'])
def test_reused_pr_unreadable_verification_never_mutates_it(publication, mode):
    p = publication
    p.capture()
    p.provider['prs'] = [p.exact_pr()]
    set_provider_mode(p, mode)
    assert 'rc=77 ' in p.publish()
    assert p.observed()['reason'] == 'reused-pr-postcondition-unverified'
    assert p.observed()['mutation_state'] == 'none'
    assert p.observed()['observed_identity'] is None
    assert not p.effects.exists()
    assert json.loads(p.provider_path.read_text())['prs'] == [p.exact_pr()]
    assert p.calls()[-1][:3] == ['pr', 'view', p.exact_pr()['url']]
