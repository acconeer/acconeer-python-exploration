#!/bin/bash


source tests/release_branch/release_branch_utils.sh

ref_head=$(git rev-parse HEAD)

jenkins_merge=$(commit_is_jenkins_merge ${ref_head})
if [ ${jenkins_merge} -eq 1 ]; then

    release_branch=$(get_release_branch_from_jenkins_merge_commit ${ref_head})
    if [[ ${release_branch} != ${RELEASE_BRANCH_NOT_FOUND} ]]; then

        echo "[INFO] Found Jenkins merge commit targeted for release branch: ${release_branch}"

        git fetch origin ${release_branch}
        handle_exit_status $? "fetch"

        git push --force origin HEAD:refs/heads/${release_branch}
        handle_exit_status $? "push-refs-heads"

        tests/release_branch/release_branch_update.sh -b ${release_branch} $@
    fi
fi
