#!/usr/bin/env bash
# What every review starts from, gathered the same way each time.
set -euo pipefail

if ! git rev-parse --git-dir >/dev/null 2>&1; then
    echo "Not in a git repository."
    exit 0
fi

rev=${1:-HEAD}
not_found="Not a commit or range: '$rev'. Resolve it to a ref and rerun this script."
revs=$(git rev-parse --revs-only "$rev" 2>/dev/null) || revs=
if [[ $revs == *^* ]]; then
    mapfile -t commits < <(git rev-list --reverse "$rev")
    if ((${#commits[@]} == 0)); then
        echo "Empty range: '$rev'."
        exit 0
    fi
elif git rev-parse --verify --quiet "$rev^{commit}" >/dev/null; then
    commits=("$rev")
else
    echo "$not_found"
    exit 0
fi

# The image report for commits that add or change images. Only these start hatch.
image_check() {
    local out err
    git show --format= --name-only --diff-filter=AM --diff-merges=first-parent "$1" -- \
        ':(icase)*.png' ':(icase)*.jpg' ':(icase)*.jpeg' | grep -q . || return 0
    echo "=== Image check ==="
    err=$(mktemp)
    out=$(cd "$(git rev-parse --show-toplevel)" &&
        hatch run docs:compress-images --rev "$1" 2>"$err") || out="not run: $(tail -n 1 "$err")"
    rm -f "$err"
    echo "$out"
}

# Claude Code saves longer output to a file and shows only a preview.
budget=${BASH_MAX_OUTPUT_LENGTH:-30000}
heads=()
for c in "${commits[@]}"; do
    head=$(
        if ((${#commits[@]} > 1)); then
            echo "##### $(git log -1 --format='%h %s' "$c")"
        fi
        echo "=== Message and stat ==="
        git show --stat "$c"
        echo "=== Remote branches containing it ==="
        git branch -r --contains "$c" | grep . || echo "none"
        image_check "$c"
        echo "=== Diff ==="
    )
    heads+=("$head")
    budget=$((budget - ${#head} - 200))
done

if ((budget < 0 && ${#commits[@]} > 1)); then
    echo "Too many commits (${#commits[@]}) to show here: review a narrower range of these."
    git log --no-walk=unsorted --format='%h %s' "${commits[@]}"
    exit 0
fi

for i in "${!commits[@]}"; do
    c=${commits[i]}
    echo "${heads[i]}"
    patch=$(git show --format= --patch --diff-merges=first-parent "$c")
    lines=$(wc -l <<<"$patch")
    if ((lines <= 500 && ${#patch} < budget)); then
        echo "$patch"
        budget=$((budget - ${#patch}))
    else
        echo "Left out ($lines lines): read the files that matter with 'git show $c -- <path>'."
    fi
done
