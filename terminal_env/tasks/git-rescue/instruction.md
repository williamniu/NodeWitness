# Rescue a git repository

`/workspace/repo` is a git repository with two problems.

1. **Lost work.** Someone ran `git reset --hard` and lost the newest commit on `main`, whose message is `add feature flag`. Put it back on `main` as the newest commit, with the same content.
2. **Leaked secrets.** The commit `add config` added `config/secrets.env`, which holds a live API token. The token was also pasted into another tracked file, and a newer, rotated token was stashed. Make the repository safe:
   - Remove `config/secrets.env` from every commit.
   - In every other tracked file, in every commit, replace each token string with `REDACTED`. Change nothing else in those files.
   - Afterwards, nothing reachable from any ref (branches, tags, stashes or anything else under `refs/`) may contain either token.

Keep the history intact:

- `main` keeps the same commit messages in the same order.
- Branch `release/1.x` must still exist, rewritten the same way, with the same commit messages. It must share the rewritten history of `main` up to `tune parser`.
- Tag `v0.1` must stay an **annotated** tag with the same message, pointing to the rewritten `tune parser` commit.
- Branch `backup/pre-cleanup` exists only to hold the secret. Delete it.
- Do not add new files or commits.

When you finish, `HEAD` must be on `main` and the working tree must be clean (`git status --porcelain` prints nothing).

Hidden tests inspect the repository's objects and refs directly, with your repository config, hooks and replace refs ignored.
