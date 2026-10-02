#!/bin/bash

usage() {
    echo "Usage: release_branch_update.sh [OPTION] source_branch_1:destination_branch_1 [source_branch_2:destination_branch_2, ...]"
    echo
    echo "Options:"
    echo "    -b    current branch"
    echo "    -p    push updated branch to remote origin"
}

OPTSTRING=":pb:"
push_branch=0

while getopts ${OPTSTRING} opt; do
    case ${opt} in
        p)
            push_branch=1
            ;;
        b)
            current_branch=${OPTARG}
            ;;
        :)
            echo "Option -${OPTARG} requires an arguemnt."
            echo
            usage
            exit 1
            ;;
        ?)
            echo "Invalid option: -${OPTARG}."
            echo
            usage
            exit 1
            ;;
    esac
done

if [ -z "$current_branch" ]; then
    echo "Need to specify current branch."
    echo
    usage
    exit 1
fi

positional_args=${@:$OPTIND:$#}

if [ -z "$positional_args" ]; then
    echo "Need to specify at least one source_branch:destination_branch."
    echo
    usage
    exit 1
fi

# Include helpers.
source tests/release_branch/release_branch_utils.sh

# List of branches to update.
src_dest_branches=$positional_args

# Staging branch for the update handling.
staging_branch="staging"

# Current Git state.
orig_git_state=$(git rev-parse HEAD)


# Check if the current branch is already up to date.
is_already_up_to_date() {
    local result=$(git merge --no-commit --no-ff origin/$1)

    if [[ "${result}" == *"Already up to date"* ]]; then
        echo 1
    else
        git merge --abort
        echo 0
    fi
}


# Create Change-Id for Gerrit.
create_change_id() {
    local committer=$(git var GIT_COMMITTER_IDENT)
    local ref=$(git rev-parse HEAD)
    local hash=$({ echo "${committer}"; echo "${ref}"; } | git hash-object --stdin)
    echo "I${hash}"
}


# Merge source branch $1 into release branch $2. Run it in a subshell:
# handle_exit_status exits.
update_release_branch() {
    local source_branch=$1
    local release_branch=$2

    echo "[INFO] Trying to update release branch \"${release_branch}\" from \"${source_branch}\""

    #
    # Check out release into temporary staging branch.
    #

    echo "[INFO] Checking out release branch"
    git checkout -B ${staging_branch} origin/${release_branch}
    handle_exit_status $? "checkout"

    #
    # Skip if the branch is already up to date.
    #

    already_up_to_date=$(is_already_up_to_date ${source_branch})
    if [ ${already_up_to_date} -eq 1 ]; then
        echo "[INFO] The release branch ${release_branch} is already up to date"
        return 0
    fi

    #
    # Reset if last commit is a merge made by the Jenkins updater (hence by this script).
    #

    should_reset=$(commit_is_jenkins_merge $(git rev-parse HEAD))
    if [ ${should_reset} -eq 1 ]; then
        echo "[INFO] HEAD is a merge commit created by Jenkins Builder; resetting to HEAD~1"
        git log -1
        git reset --hard HEAD~1
        handle_exit_status $? "reset-merge"
    fi

    #
    # Merge source branch (e.g. master|main) into the staging branch.
    #

    echo "[INFO] Merging \"${source_branch}\" into \"${release_branch}\""
    git merge --verbose --no-ff origin/${source_branch}
    handle_exit_status $? "merge"
    git log -2

    #
    # Amend the commit message with needed info.
    #

    echo "[INFO] Updating merge commit message"
    msg_subject="Merge by Jenkins Builder"
    msg_body="Merge ${source_branch} into ${release_branch}"
    msg_key="Key: ${JENKINS_MERGE_KEY}"
    msg_target_branch="${RELEASE_BRANCH_HINT}${release_branch}"
    msg_change_id="Change-Id: $(create_change_id)"

    git commit --amend -m "${msg_subject}" -m "${msg_body}" -m "${msg_key}" -m "${msg_target_branch}" -m "${msg_change_id}"
    handle_exit_status $? "commit-amend"
    git log -1

    #
    # Push to Gerrit for review (done automatically by Jenkins)
    #

    if [ ${push_branch} -eq 1 ]; then
        echo "[INFO] Pushing updated release branch to Gerrit for verification"
        git push --verbose origin HEAD:refs/for/${release_branch}%ready
        handle_exit_status $? "push-refs-for"
    else
        echo "[WARN] The release branch will not be pushed to origin"
    fi
}


# Update releases. A failed branch doesn't stop the others.
failed_branches=()
for src_dest_branch in ${src_dest_branches[@]}; do
    IFS=':' read -r -a branches <<< "$src_dest_branch"
    source_branch=${branches[0]}
    release_branch=${branches[1]}

    echo "Comparing current branch: ${current_branch} with source branch: ${source_branch}"

    if [[ ( -n "$source_branch" && -n "$release_branch" && "$source_branch" == "$current_branch" ) ]]; then
        if ! ( update_release_branch ${source_branch} ${release_branch} ); then
            failed_branches+=("${source_branch}:${release_branch}")
        fi

        echo "[INFO] Restoring git status to original state"
        git merge --abort 2> /dev/null
        git checkout --force ${orig_git_state}
        git branch -D ${staging_branch} 2> /dev/null
    fi
done

for failed_branch in "${failed_branches[@]}"; do
    IFS=':' read -r -a branches <<< "$failed_branch"
    source_branch=${branches[0]}
    release_branch=${branches[1]}

    # Without the Jenkins merge key, the next update merges on top of the
    # resolution instead of resetting it away.
    echo "[ERROR] Failed to update ${release_branch} (see above). If the merge conflicted, merge it by hand:"
    echo "    git fetch origin && git switch --detach origin/${release_branch} && git merge --no-ff origin/${source_branch} -m 'Merge ${source_branch} into ${release_branch}'"
    echo "Resolve any conflicts, then: git commit --no-edit --cleanup=strip && git push origin HEAD:refs/for/${release_branch}"
done

if [ ${#failed_branches[@]} -ne 0 ]; then
    exit 1
fi
