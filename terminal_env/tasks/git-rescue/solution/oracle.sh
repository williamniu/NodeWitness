set -e
cd /workspace/repo
export FILTER_BRANCH_SQUELCH_WARNING=1
# 1. Recover the reset commit from the reflog; it is a child of HEAD.
lost=$(git log -g --format='%H %s' | awk '$2=="add" && $3=="feature" && $4=="flag" {print $1; exit}')
git reset -q --hard "$lost"
# 2. Learn the tokens before deleting anything that holds them.
token=$(git show backup/pre-cleanup:config/secrets.env | sed -n 's/^API_TOKEN=//p')
rotated=$(git stash show -p stash@{0} | sed -n 's/^+API_TOKEN_NEXT=//p')
git stash clear
git branch -D backup/pre-cleanup
# 3. Rewrite every branch and tag: drop the secrets file, redact tokens elsewhere.
export NW_T1="$token" NW_T2="$rotated"
git filter-branch -f --tree-filter '
  rm -f config/secrets.env
  grep -rlF -e "$NW_T1" -e "$NW_T2" . 2>/dev/null | while read -r f; do
    sed -i -e "s/$NW_T1/REDACTED/g" -e "s/$NW_T2/REDACTED/g" "$f"
  done' --tag-name-filter cat -- --branches --tags >/dev/null 2>&1
git for-each-ref --format='%(refname)' refs/original | xargs -r -n1 git update-ref -d
rm -f config/secrets.env
git checkout -q main
git reflog expire --expire=now --all
git gc -q --prune=now
git status --porcelain
git for-each-ref --format='%(objecttype) %(refname)'
git log --oneline --graph --all
