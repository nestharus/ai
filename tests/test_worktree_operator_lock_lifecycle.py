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
        acted += [self.path / name for name in ("publication.py", "remove.py", "prepare.sh", "provider.json", "bin/gh")
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


GH = '''#!/usr/bin/env python3
import json, os, pathlib, sys
state = json.loads(pathlib.Path(os.environ["FAKE_PROVIDER"]).read_text())
args = sys.argv[1:]
if args[:2] == ["repo", "view"]:
    assert args[2] == "fixture/project"
    print(json.dumps(state["repo"]))
elif args[:2] == ["pr", "list"]:
    with open(os.environ["FAKE_PROVIDER"] + ".queries", "a") as output:
        output.write(json.dumps(args) + "\\n")
    assert args == state["query"], "candidate query mismatch: " + repr(args)
    print(json.dumps(state["prs"]))
else:
    raise SystemExit("unexpected provider mutation: " + repr(args))
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
        self.writer_dir = self.path / "writer"
        self.writer_dir.mkdir()
        (self.writer_dir / "pr-body.md").write_text("Body")
        (self.writer_dir / "pr-body.md.title").write_text("Title")
        runtime.env.update(FAKE_PROVIDER=str(self.provider_path), publication_identity_script=str(self.guard),
                           snapshot=str(self.snapshot), worktrees_root=str(self.worktrees), name="topic",
                           branch_name="topic", base_branch="main", repo_slug="fixture/project",
                           writer_dir=str(self.writer_dir), writer_rc="0", writer_log_rc="0")

    def write_provider(self):
        self.provider_path.write_text(json.dumps(self.provider))

    def capture(self):
        body = ('python3 "$publication_identity_script" capture "$snapshot" "$repo_root" '
                '"$worktrees_root" "$name" "$branch_name" "$base_branch" "$repo_slug" '
                f'> "{self.output}"\n')
        _, job = self.runtime.start(body)
        assert "rc=0 " in self.runtime.terminal(job)
        return json.loads(self.output.read_text())

    def publish(self):
        # Stub only external effects; actual published validation and dispatch select them.
        body = block("worktree-writer-output-v1") + f'''
publish_new_pr() {{ printf 'push\\ncreate\\n' >> "{self.effects}"; }}
verify_reused_pr() {{ printf 'reuse\\n' >> "{self.effects}"; }}
''' + block("worktree-publication-dispatch-v1")
        _, job = self.runtime.start(body)
        return self.runtime.terminal(job)

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
        assert p.effects.read_text() == "push\ncreate\n"
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
        assert p.effects.read_text() == "reuse\n"
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
