#!/bin/bash

# Usage: update-release-branches.sh [OPTION]...
#
# Options:
#    -p          push updated branch to remote origin
#    -k <key>    key to identify the merge


# Option parser
push_branch=0
jenkins_key=""
while getopts "pk:" arg; do
    case ${arg} in
    p)    push_branch=1;;
    k)    jenkins_key=${OPTARG};;
    esac
done

if [ ${push_branch} -eq 1 ] && [ -z ${jenkins_key} ]; then
    echo "[ERROR] Missing Jenkins merge key"
    exit 1
fi


# List of branches to update
release_branches=("public_rss_release_a121")

# Branch to be merged into the release branches
source_branch="master"

# Current Git state
orig_git_state=$(git rev-parse HEAD)


# Check status of $1 and exit if non-zero
handle_exit_status() {
    if [ $1 -ne 0 ]; then
        echo "[ERROR] Failed to $2 (status: $1)"
        exit $1
    fi
}


# Check if $1 is a merge commit made by Jenkins
commit_is_jenkins_merge() {
    local author=$(git log -1 --pretty=format:'%an' --merges $1)

    if [[ ${author} == "Jenkins Builder" ]]; then
        echo 1
    else
        echo 0
    fi
}


# Create Change-Id for Gerrit
create_change_id() {
    local committer=$(git var GIT_COMMITTER_IDENT)
    local ref=$(git rev-parse HEAD)
    local hash=$({ echo "${committer}"; echo "${ref}"; } | git hash-object --stdin)
    echo "I${hash}"
}


# Update releases
for release_branch in ${release_branches[@]}; do
    echo "[INFO] Trying to update release branch \"${release_branch}\""

    echo "[INFO] Checking out release branch"
    git checkout -B staging origin/${release_branch}
    handle_exit_status $? "checkout"
    git log -1

    should_reset=$(commit_is_jenkins_merge $(git rev-parse HEAD))
    if [ ${should_reset} -eq 1 ]; then
        echo "HEAD is a merge commit created by Jenkins Builder; resetting branch to HEAD~1"
        git log -1
        git reset --hard HEAD~1
        handle_exit_status $? "reset-merge"
    fi

    echo "[INFO] Merging \"${source_branch}\" into release branch"
    git merge --verbose --no-ff origin/${source_branch}
    handle_exit_status $? "merge"
    git log -2

    if [ ${push_branch} -eq 1 ]; then
        echo "[INFO] Updating commit message"

        msg_subject="Merge by Jenkins Builder"
        msg_body="Merge ${source_branch} into ${release_branch}"
        msg_key="Key: ${jenkins_key}"
        msg_change_id="Change-Id: $(create_change_id)"

        git commit --amend -m "${msg_subject}" -m "${msg_body}" -m "${msg_key}" -m "${msg_change_id}"
        handle_exit_status $? "commit-amend"
        git log -1

        echo "[INFO] Pushing updated release branch to Gerrit for verification"
        git push --verbose origin HEAD:refs/for/${release_branch}%remove-private
        handle_exit_status $? "push"
    else
        echo "[WARN] The release branch will not be pushed to origin"
    fi
done


# Restore original state
git checkout --force ${orig_git_state}
