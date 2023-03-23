#!/bin/bash


# SHA1("Jenkins_merge")
JENKINS_MERGE_KEY="e99f5f0b803aa8fb494916a7fe6a2ef240e40dab"

# Branch hint to use when adding current release branch to a commit message
RELEASE_BRANCH_HINT="Target-branch: "

# To indicate an invalid release branch name
RELEASE_BRANCH_NOT_FOUND="__branch_not_found__"


# Check status of $1 and exit if non-zero.
handle_exit_status() {
    if [ $1 -ne 0 ]; then
        echo "[ERROR] Failed to $2 (status: $1)"
        exit $1
    fi
}


# Check if $1 is a merge commit made by Jenkins
commit_is_jenkins_merge() {
    local key=$(git log -1 --pretty=format:'%B' $1 | grep --only-matching --max-count=1 ${JENKINS_MERGE_KEY})
    if [[ ${key} == ${JENKINS_MERGE_KEY} ]]; then
        echo 1
    else
        echo 0
    fi
}

# Get release branch name from a Jenkins merge commit ($1)
# Assumes that the branch contains at least 7 characters.
get_release_branch_from_jenkins_merge_commit() {
    local branch_hint=$(git log -1 --pretty=format:'%B' $1 | grep -E --only-matching --max-count=1 "${RELEASE_BRANCH_HINT}.{7,}")
    if [[ ${branch_hint} == "${RELEASE_BRANCH_HINT}"* ]]; then
        echo ${branch_hint} | cut -d' ' -f2
    else
        echo ${RELEASE_BRANCH_NOT_FOUND}
    fi
}
