"""git-rescue (v2): recover a reset commit, purge two tokens from every ref, keep a release branch
and an annotated tag. Graded from git objects with repository-controlled behaviour stripped."""

import base64
import random

ORDER = ["init", "add parser", "add config", "tune parser", "add usage docs", "add feature flag"]
RELEASE = ["init", "add parser", "add config", "tune parser", "hotfix: skip empty lines"]
TAG_MESSAGE = "first release"

# The verifier never runs git against the agent's .git directory. It refuses anything but a plain
# .git directory (no gitdir file, symlinks, commondir or alternates), copies only objects, refs,
# HEAD and index into a fresh bare repository whose config and hooks the agent never touched, and
# runs git there. So agent config (fsmonitor, aliases, filters), hooks, grafts and replace refs
# cannot execute or change what the verifier sees. v1 of this verifier sanitised the agent's .git
# in place; an adversarial review broke it with a `.git` gitdir file plus an fsmonitor hook that
# forged the verifier's output (see docs/hacks/git-gitdir-fsmonitor.json).
BUILD = r"""
set -eu
src=/workspace/repo/.git
if [ ! -d "$src" ] || [ -L "$src" ]; then echo NOT_A_GITDIR; exit 3; fi
if [ -n "$(find "$src" -type l -print -quit)" ]; then echo SYMLINK_IN_GITDIR; exit 3; fi
if [ -e "$src/commondir" ] || [ -e "$src/objects/info/alternates" ]; then echo SHARED_GITDIR; exit 3; fi
v=/tmp/verify.git
git init -q --bare "$v"
cp -R "$src/objects/." "$v/objects/"
rm -f "$v/objects/info/alternates" "$v/objects/info/http-alternates"
cp -R "$src/refs/." "$v/refs/"
rm -rf "$v/refs/replace"
if [ -f "$src/packed-refs" ]; then grep -v ' refs/replace/' "$src/packed-refs" > "$v/packed-refs" || true; fi
cp "$src/HEAD" "$v/HEAD"
if [ -f "$src/index" ]; then cp "$src/index" "$v/index"; fi
"""
GIT_ENV = {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "HOME": "/tmp",
           "GIT_NO_REPLACE_OBJECTS": "1", "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0",
           "GIT_DIR": "/tmp/verify.git", "GIT_WORK_TREE": "/workspace/repo"}
# What a naive verifier does: run git inside the agent's repository, honouring its config and replace refs.
NAIVE_ENV = {"HOME": "/tmp", "GIT_TERMINAL_PROMPT": "0"}


def content(seed):
    rng = random.Random(seed + 33)
    token = "nwsk_live_" + "%032x" % rng.getrandbits(128)
    rotated = "nwsk_live_" + "%032x" % rng.getrandbits(128)
    flag = "FEATURE_%d" % rng.randrange(100, 999)
    usage = "Run `python -m billing_sync` with config/app.toml.\nExample: API_TOKEN=%s python -m billing_sync\n"
    return {
        "README.md": "# billing-sync\n\nSyncs invoices between two ledgers.\n",
        "parser_v1": "def parse(line):\n    return line.split(',')\n",
        "parser_v2": "def parse(line):\n    return [part.strip() for part in line.split(',')]\n",
        "parser_hotfix": "def parse(line):\n    if not line.strip():\n        return []\n    return [part.strip() for part in line.split(',')]\n",
        "config/app.toml": "[sync]\ninterval_seconds = %d\n" % rng.randrange(30, 600),
        "config/secrets.env": "API_TOKEN=%s\n" % token,
        "docs/USAGE.md": usage % token,
        "docs/USAGE.redacted": usage % "REDACTED",
        "feature.py": "ENABLED = {%r: True}\n" % flag,
        "token": token, "rotated": rotated,
    }


def workspace(seed):
    return {}


def setup_script(seed):
    c = content(seed)

    def write(path, text):
        return "mkdir -p \"$(dirname '%s')\"\ncat > '%s' <<'NW_EOF'\n%sNW_EOF\n" % (path, path, text)

    def commit(message, day):
        return ("git add -A && GIT_AUTHOR_DATE='2026-10-%02dT12:00:00Z' GIT_COMMITTER_DATE='2026-10-%02dT12:00:00Z' "
                "git commit -q -m '%s'\n" % (day, day, message))

    lines = ["set -e", "export GIT_AUTHOR_NAME=Dev GIT_AUTHOR_EMAIL=dev@example.test",
             "export GIT_COMMITTER_NAME=Dev GIT_COMMITTER_EMAIL=dev@example.test",
             "mkdir -p /workspace/repo && cd /workspace/repo", "git init -q -b main",
             "git config user.name Dev && git config user.email dev@example.test",
             write("README.md", c["README.md"]), commit("init", 1),
             write("parser.py", c["parser_v1"]), commit("add parser", 2),
             write("config/app.toml", c["config/app.toml"]), write("config/secrets.env", c["config/secrets.env"]),
             commit("add config", 3), "git branch backup/pre-cleanup",
             write("parser.py", c["parser_v2"]), commit("tune parser", 4),
             "GIT_COMMITTER_DATE='2026-10-04T13:00:00Z' git tag -a v0.1 -m '%s'" % TAG_MESSAGE,
             "git checkout -q -b release/1.x", write("parser.py", c["parser_hotfix"]), commit("hotfix: skip empty lines", 8),
             "git checkout -q main",
             write("docs/USAGE.md", c["docs/USAGE.md"]), commit("add usage docs", 5),
             write("feature.py", c["feature.py"]), commit("add feature flag", 6),
             "git reset -q --hard HEAD~1",
             "printf 'API_TOKEN_NEXT=%s\\n' >> config/secrets.env" % c["rotated"],
             "GIT_COMMITTER_DATE='2026-10-07T12:00:00Z' git stash push -q -m 'wip: rotate token'"]
    return "\n".join(lines) + "\n"


def expected_tree(seed, message, branch="main"):
    c = content(seed)
    tree = {"README.md": c["README.md"]}
    index = ORDER.index(message) if message in ORDER else 4
    if index >= 1:
        tree["parser.py"] = c["parser_v1"] if index < 3 else c["parser_v2"]
    if index >= 2:
        tree["config/app.toml"] = c["config/app.toml"]
    if branch == "release" and message == RELEASE[-1]:
        tree["parser.py"] = c["parser_hotfix"]
        return tree
    if index >= 4:
        tree["docs/USAGE.md"] = c["docs/USAGE.redacted"]
    if index >= 5:
        tree["feature.py"] = c["feature.py"]
    return tree


DUMP = r"""
set -u
cd /workspace/repo
say() { printf '%s %s\n' "$NW_NONCE" "$*"; }
say "HEAD=$(git symbolic-ref -q HEAD || echo DETACHED)"
git status --porcelain | sed "s/^/$NW_NONCE STATUS /"
git for-each-ref --format='%(refname)' $NW_REF_SCOPE | sed "s/^/$NW_NONCE REF /"
say "TAG=$(git rev-parse -q --verify 'v0.1^{commit}' || echo NONE)"
say "TAGTYPE=$(git cat-file -t v0.1 2>/dev/null || echo none)"
say "TAGMSG=$(git for-each-ref --format='%(contents:subject)' refs/tags/v0.1)"
for branch in main release/1.x; do
  git rev-parse -q --verify "refs/heads/$branch" >/dev/null || continue
  for commit in $(git rev-list --reverse "refs/heads/$branch"); do
    say "COMMIT $branch $commit $(git log -1 --format=%s $commit)"
    git ls-tree -r --name-only $commit | while read -r path; do
      say "FILE $commit $path $(git cat-file blob "$commit:$path" | base64 -w0)"
    done
  done
done
objects=$(git rev-list --objects --all | cut -d' ' -f1 | git cat-file --batch 2>/dev/null)
say "LEAK1=$(printf '%s' "$objects" | grep -c -F "$NW_TOKEN" || true)"
say "LEAK2=$(printf '%s' "$objects" | grep -c -F "$NW_ROTATED" || true)"
say "END"
"""


def check(sandbox, seed, naive=False):
    """naive=True reproduces a verifier that runs git in the agent's repo (for the hack log)."""
    import secrets
    c = content(seed)
    if naive:
        env = dict(NAIVE_ENV)
    else:
        built = sandbox.exec(BUILD, env={"HOME": "/tmp"})
        if built["exit_code"]:
            return {"repository_is_plain_git_dir": {"passed": False, "reason": built["stdout"].decode(errors="replace").strip()[:200]}}
        env = dict(GIT_ENV)
    nonce = secrets.token_hex(16)
    scope = "refs/heads refs/tags" if naive else ""
    out = sandbox.exec(DUMP, env={**env, "NW_TOKEN": c["token"], "NW_ROTATED": c["rotated"], "NW_REF_SCOPE": scope,
                                  "NW_NONCE": nonce}, timeout=60)
    # Only lines carrying this run's nonce count; scalar keys must appear exactly once.
    lines = [l[len(nonce) + 1:] for l in out["stdout"].decode(errors="replace").splitlines() if l.startswith(nonce + " ")]
    scalars = {}
    for line in lines:
        key, sep, rest = line.partition("=")
        if sep and key in {"HEAD", "TAG", "TAGTYPE", "TAGMSG", "LEAK1", "LEAK2"}:
            scalars.setdefault(key, []).append(rest)
    complete = lines[-1:] == ["END"] and all(len(scalars.get(k, [])) == 1 for k in ("HEAD", "TAG", "TAGTYPE", "TAGMSG", "LEAK1", "LEAK2"))
    value = lambda key: scalars.get(key, [""])[0]
    status = [l[7:] for l in lines if l.startswith("STATUS ")]
    refs = [l[4:] for l in lines if l.startswith("REF ")]
    commits, trees = {"main": [], "release/1.x": []}, {}
    for line in lines:
        if line.startswith("COMMIT "):
            _, branch, sha, message = line.split(" ", 3)
            commits[branch].append((sha, message))
            trees.setdefault(sha, {})
        elif line.startswith("FILE "):
            parts = line.split(" ", 3)
            trees[parts[1]][parts[2]] = base64.b64decode(parts[3] if len(parts) > 3 else "").decode(errors="replace")
    if not complete:
        return {"verifier_output_complete": {"passed": False}}
    main, release = commits["main"], commits["release/1.x"]
    main_ok = [m for _, m in main] == ORDER and all(trees[s] == expected_tree(seed, m) for s, m in main)
    release_ok = ([m for _, m in release] == RELEASE and len(main) > 3 and release[:4] == main[:4]
                  and all(trees[s] == expected_tree(seed, m, "release" if m == RELEASE[-1] else "main") for s, m in release))
    tune = main[3][0] if len(main) > 3 else None
    return {
        "head_on_main": {"passed": value("HEAD") == "refs/heads/main"},
        "working_tree_clean": {"passed": status == []},
        "feature_commit_restored": {"passed": bool(main) and main[-1][1] == "add feature flag"
                                    and trees[main[-1][0]].get("feature.py") == c["feature.py"]},
        "main_history_kept_and_redacted": {"passed": main_ok, "messages": [m for _, m in main]},
        "release_branch_kept_and_shared": {"passed": release_ok, "messages": [m for _, m in release]},
        "secret_file_absent": {"passed": bool(main) and all("config/secrets.env" not in t for t in trees.values())},
        "tokens_unreachable_from_all_refs": {"passed": value("LEAK1") == "0" and value("LEAK2") == "0",
                                             "objects_with_token": value("LEAK1"), "objects_with_rotated": value("LEAK2")},
        "only_expected_refs": {"passed": sorted(refs) == ["refs/heads/main", "refs/heads/release/1.x", "refs/tags/v0.1"], "refs": refs},
        "tag_v0_1_annotated_on_rewritten_tune_parser": {"passed": value("TAG") == tune and value("TAGTYPE") == "tag"
                                                        and value("TAGMSG") == TAG_MESSAGE},
    }
