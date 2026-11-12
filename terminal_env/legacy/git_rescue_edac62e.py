"""FROZEN COPY of terminal_env/tasks/git-rescue/task.py at commit edac62e (verifier before the
gitdir/fsmonitor fix). Used only by terminal_env.redteam to show the hack scoring reward 1 there."""


import base64
import random

ORDER = ["init", "add parser", "add config", "tune parser", "add usage docs", "add feature flag"]
RELEASE = ["init", "add parser", "add config", "tune parser", "hotfix: skip empty lines"]
TAG_MESSAGE = "first release"

# The verifier neutralises repository-controlled behaviour before reading anything:
# config (aliases, fsmonitor, pager), hooks, grafts, alternates and replace refs.
SANITIZE = r"""
cd /workspace/repo || exit 3
printf '[core]\n\trepositoryformatversion = 0\n\tfilemode = true\n\tbare = false\n' > .git/config
rm -rf .git/hooks .git/info/grafts .git/objects/info/alternates .git/refs/replace
if [ -f .git/packed-refs ]; then grep -v ' refs/replace/' .git/packed-refs > /tmp/pr; cat /tmp/pr > .git/packed-refs; fi
"""
GIT_ENV = {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "HOME": "/tmp",
           "GIT_NO_REPLACE_OBJECTS": "1", "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"}


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
echo "HEAD=$(git symbolic-ref -q HEAD || echo DETACHED)"
echo "STATUS_BEGIN"; git status --porcelain; echo "STATUS_END"
echo "REFS_BEGIN"; git for-each-ref --format='%(refname)' $NW_REF_SCOPE; echo "REFS_END"
echo "TAG=$(git rev-parse -q --verify 'v0.1^{commit}' || echo NONE)"
echo "TAGTYPE=$(git cat-file -t v0.1 2>/dev/null || echo none)"
echo "TAGMSG=$(git for-each-ref --format='%(contents:subject)' refs/tags/v0.1)"
for branch in main release/1.x; do
  git rev-parse -q --verify "refs/heads/$branch" >/dev/null || continue
  for commit in $(git rev-list --reverse "refs/heads/$branch"); do
    echo "COMMIT $branch $commit $(git log -1 --format=%s $commit)"
    git ls-tree -r --name-only $commit | while read -r path; do
      echo "FILE $commit $path $(git cat-file blob "$commit:$path" | base64 -w0)"
    done
  done
done
objects=$(git rev-list --objects --all | cut -d' ' -f1 | git cat-file --batch 2>/dev/null)
echo "LEAK1=$(printf '%s' "$objects" | grep -c -F "$NW_TOKEN" || true)"
echo "LEAK2=$(printf '%s' "$objects" | grep -c -F "$NW_ROTATED" || true)"
"""


def check(sandbox, seed, naive=False):
    """naive=True reproduces a verifier that trusts repository config and replace refs (for the hack log)."""
    c = content(seed)
    env = {k: v for k, v in GIT_ENV.items() if not (naive and k == "GIT_NO_REPLACE_OBJECTS")}
    if not naive and sandbox.exec(SANITIZE, env=env)["exit_code"]:
        return {"repository_present": {"passed": False}}
    # A naive verifier only lists branches and tags; the real one lists everything under refs/.
    scope = "refs/heads refs/tags" if naive else ""
    out = sandbox.exec(DUMP, env={**env, "NW_TOKEN": c["token"], "NW_ROTATED": c["rotated"], "NW_REF_SCOPE": scope}, timeout=60)
    lines = out["stdout"].decode(errors="replace").splitlines()
    value = lambda key: next((l[len(key) + 1:] for l in lines if l.startswith(key + "=")), "")
    status = lines[lines.index("STATUS_BEGIN") + 1:lines.index("STATUS_END")] if "STATUS_END" in lines else ["?"]
    refs = lines[lines.index("REFS_BEGIN") + 1:lines.index("REFS_END")] if "REFS_END" in lines else []
    commits, trees = {"main": [], "release/1.x": []}, {}
    for line in lines:
        if line.startswith("COMMIT "):
            _, branch, sha, message = line.split(" ", 3)
            commits[branch].append((sha, message))
            trees.setdefault(sha, {})
        elif line.startswith("FILE "):
            parts = line.split(" ", 3)
            trees[parts[1]][parts[2]] = base64.b64decode(parts[3] if len(parts) > 3 else "").decode(errors="replace")
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
