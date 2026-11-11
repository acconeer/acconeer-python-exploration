import groovy.transform.Field

@Library('sw-jenkins-library@67e8e85f6bb9e8c6139a0477378160532c361d75') _

enum BuildScope {
    SANITY, HOURLY, NIGHTLY
}

enum BuildTrigger {
    CHANGE, CRON_TIMER, TAG
}

@Field
def pythonVersionsForBuildScope = [
    (BuildScope.SANITY)  : ['3.12'],
    (BuildScope.HOURLY)  : ['3.12', '3.13'],
    (BuildScope.NIGHTLY) : ['3.12', '3.13'],
]

@Field
def integrationTestA2RssVersionsForBuildScope = [
    (BuildScope.SANITY)  : [branch: 'master'],
    (BuildScope.HOURLY)  : [branch: 'master'],
    (BuildScope.NIGHTLY) : [branch: 'master', tag: 'a2-v1.2.0'],
]

@Field
def integrationTestA121RssVersionsForBuildScope = [
    (BuildScope.SANITY)  : [branch: 'master'],
    (BuildScope.HOURLY)  : [tag: 'a121-v1.14.0'],
    (BuildScope.NIGHTLY) : [branch: 'master', tag: 'a121-v1.14.0'],
]

@Field
def integrationTestA111RssVersionsForBuildScope = [
    (BuildScope.SANITY)  : [],
    (BuildScope.HOURLY)  : [branch: 'master'],
    (BuildScope.NIGHTLY) : [branch: 'master', tag: 'a111-v2.15.5'],
]

// Entries are [branch: ...], [tag: ...] or, for a build that carries no tag,
// [commit: '<build storage folder>'].
@Field
def modelTestA121RssVersionForBuildScope = [
    (BuildScope.SANITY)  : [commit: 'interim/sw-main/master/2026/2026-10-29/a2-v1.2.0-rc3-26-gfe1467084c'],
    (BuildScope.HOURLY)  : [commit: 'interim/sw-main/master/2026/2026-10-29/a2-v1.2.0-rc3-26-gfe1467084c'],
    (BuildScope.NIGHTLY) : [commit: 'interim/sw-main/master/2026/2026-10-29/a2-v1.2.0-rc3-26-gfe1467084c'],
]

@Field
def modelTestA2RssVersionForBuildScope = [
    (BuildScope.SANITY)  : [commit: 'interim/sw-main/master/2026/2026-09-11/a2-v1.0.0-rc2-441-gc50b8af62f'],
    (BuildScope.HOURLY)  : [commit: 'interim/sw-main/master/2026/2026-09-11/a2-v1.0.0-rc2-441-gc50b8af62f'],
    (BuildScope.NIGHTLY) : [commit: 'interim/sw-main/master/2026/2026-09-11/a2-v1.0.0-rc2-441-gc50b8af62f'],
]

@Field
String dockerArgs = '--mount type=volume,src=uv-cache,dst=/home/ci/.cache/uv'

boolean messageOnFailure = true

@Field
String previewUrl = null

// Only Gerrit's NN/CCCCC/PP branches are changes.
boolean isChange() {
    return env.BRANCH_NAME ==~ /\d+\/\d+\/\d+/
}

def getCronTriggers(String branchName) {
    def triggers = []

    if (branchName == 'master') {
        // Hourly: every hour between 9:00 & 17:00, Monday through Friday
        // Nightly: every day at 23:00
        triggers << cron('0 9-17 * * 1-5\n0 23 * * *')
    }

    return pipelineTriggers(triggers)
}

def hatchWrap(String command) {
    // Ensure the presence of '_version.py'
    // (See https://github.com/ofek/hatch-vcs?tab=readme-ov-file#write-version-to-file)
    sh 'hatch build --hooks-only'
    sh "hatch ${command}"
}

BuildTrigger getBuildTrigger() {
    if (env.TAG_NAME) {
        return BuildTrigger.TAG
    }

    if (!currentBuild.getBuildCauses('hudson.triggers.TimerTrigger$TimerTriggerCause').isEmpty()) {
        return BuildTrigger.CRON_TIMER
    }

    return BuildTrigger.CHANGE
}

BuildScope getBuildScope(BuildTrigger buildTrigger) {
    if (buildTrigger == BuildTrigger.TAG) {
        return BuildScope.NIGHTLY
    }

    if (buildTrigger != BuildTrigger.CRON_TIMER) {
        return BuildScope.SANITY
    }

    def hour = new Date()[Calendar.HOUR_OF_DAY]

    if (hour <= 17) {
        return BuildScope.HOURLY
    }

    return BuildScope.NIGHTLY
}

def finishBuild(boolean messageOnFailure) {
    stage('Report to gerrit') {
        int score = currentBuild.currentResult == 'SUCCESS' ? 1 : -1
        String message = (
            "${currentBuild.currentResult}: ${env.BUILD_URL}, " +
            "Duration: ${currentBuild.durationString - ' and counting'}"
        )
        if (previewUrl != null) {
            message += ", Docs preview: ${previewUrl}"
        }

        try {
            finishBuildStorage()
        } finally {
            gerritReview labels: [Verified: score], message: message
        }
    }

    if (messageOnFailure && (currentBuild.currentResult == 'FAILURE')) {
        withCredentials([string(credentialsId: 'teams-robot', variable: 'TEAMS_API_TOKEN')]) {
            office365ConnectorSend webhookUrl: TEAMS_API_TOKEN,
            adaptiveCards: true
        }
    }
}

def manageReleaseBranches(boolean update) {
    stage('Manage release branches') {
        node('docker') {
            ws('workspace/exptool') {
                printNodeInfo()
                checkoutAndCleanup()

                buildDocker(path: 'docker').inside(dockerArgs) {
                    withCredentials([gitUsernamePassword(credentialsId: '1bef2b16-6cd9-4836-a014-421199e7fb0f'),
                                     string(variable: 'RELEASE_BRANCHES',
                                            credentialsId: 'et_update_release_branches')])
                    {
                        if (update) {
                            sh "git config user.name 'Jenkins Builder'"
                            sh "git config user.email 'ai@acconeer.com'"
                            sh(
                                'tests/release_branch/release_branch_update.sh' +
                                " -b ${env.BRANCH_NAME}" +
                                " -p ${RELEASE_BRANCHES}"
                            )
                        } else {
                            sh(
                                'tests/release_branch/release_branch_push.sh' +
                                " -b ${env.BRANCH_NAME}" +
                                " -p ${RELEASE_BRANCHES}"
                            )
                        }
                    }
                }
            }
        }
    }
}

try {
    // Ensure cron triggers are setup (for periodic jobs) and old builds are discarded
    properties([
        getCronTriggers(env.BRANCH_NAME),
        buildDiscarder(logRotator(daysToKeepStr: '14')),
    ])

    def buildTrigger = getBuildTrigger()
    def buildScope = getBuildScope(buildTrigger)

    def pythonVersions = pythonVersionsForBuildScope[buildScope]
    def integrationTestA121RssVersions = integrationTestA121RssVersionsForBuildScope[buildScope]
    def integrationTestA111RssVersions = integrationTestA111RssVersionsForBuildScope[buildScope]
    def integrationTestA2RssVersions = integrationTestA2RssVersionsForBuildScope[buildScope]
    def modelTestA121RssVersion = modelTestA121RssVersionForBuildScope[buildScope]
    def modelTestA2RssVersion = modelTestA2RssVersionForBuildScope[buildScope]

    if (isChange()) {
        messageOnFailure = false
    }

    // Change builds have no changeset, so Jenkins would show "Branch indexing".
    if (env.GERRIT_CHANGE_SUBJECT) {
        currentBuild.description = "${env.GERRIT_CHANGE_SUBJECT} (${env.GERRIT_PATCHSET_UPLOADER_NAME})"
    }

    stage('Report start to Gerrit') {
        gerritReview labels: [Verified: 0], message: "Test started:: ${env.BUILD_URL}, Scope: ${buildScope}"
    }

    // Without this, buildDocker gets the Dockerfile's default stage, dev.
    env.TARGET_STAGE = 'ci'

    boolean isJenkinsMerge = false

    // Only matches version on the form "vX.Y.Z" where X, Y, Z are integers
    def version_regex = /v\d+\.\d+\.\d+/

    // Release candidates, "vX.Y.Z-rcN", don't match and so are never published.
    boolean isRelease = env.TAG_NAME ==~ version_regex
    boolean isPrepareRelease = env.GERRIT_CHANGE_SUBJECT ==~ /Prepare release ${version_regex}/

    if (isRelease || isPrepareRelease) {
        stage('Release gate: algo bundle on developer site') {
            node('docker') {
                ws('workspace/exptool') {
                    printNodeInfo()
                    checkoutAndCleanup()

                    buildDocker(path: 'docker').inside(dockerArgs) {
                        withCredentials([usernamePassword(credentialsId: 'tools-devsite',
                                                          passwordVariable: 'DEV_PASSWORD',
                                                          usernameVariable: 'DEV_USERNAME')])
                        {
                            hatchWrap 'run app:python internal_tools/check_released_algo_bundle.py'
                        }
                    }
                }
            }
        }
    }

    if (isRelease) {
        stage('Release gate: release candidate on the same commit') {
            node('docker') {
                ws('workspace/exptool') {
                    printNodeInfo()
                    checkoutAndCleanup()

                    withCredentials([gitUsernamePassword(credentialsId: '1bef2b16-6cd9-4836-a014-421199e7fb0f')]) {
                        sh 'git fetch --tags origin'
                    }
                    String releaseCandidates = sh(
                        returnStdout: true,
                        script: "git tag --list --points-at HEAD '${env.TAG_NAME}-rc*'"
                    ).trim()
                    if (!releaseCandidates) {
                        error(
                            "${env.TAG_NAME} has no release candidate on its commit. Tag the commit " +
                            "${env.TAG_NAME}-rc<N>, build that tag, then build ${env.TAG_NAME} again."
                        )
                    }
                }
            }
        }
    }

    // Meant to catch common (and fast to detect) errors.
    stage('Lint') {
        node('docker') {
            ws('workspace/exptool') {
                printNodeInfo()
                checkoutAndCleanup()

                // Read from this checkout so a build with no release branch work takes no node for it.
                isJenkinsMerge = sh(returnStatus: true, script: '''#!/bin/bash
                    source tests/release_branch/release_branch_utils.sh
                    [ "$(commit_is_jenkins_merge HEAD)" -eq 1 ]
                ''') == 0

                buildDocker(path: 'docker').inside(dockerArgs) {
                    sh 'python3 -V'
                    hatchWrap 'check code'
                    hatchWrap 'check fmt'
                }
            }
        }
    }

    def parallel_steps = [:]

    parallel_steps['Build package & documentation'] = {
        node('docker') {
            ws('workspace/exptool') {
                stage('Build package & documentation') {
                    printNodeInfo()
                    checkoutAndCleanup()

                    buildDocker(path: 'docker').inside(dockerArgs) {
                        sh 'python3 -V'
                        hatchWrap 'build'
                        if (buildScope == BuildScope.NIGHTLY) {
                            hatchWrap 'run docs:nightlybuild'
                        }
                        else
                        {
                            hatchWrap 'run docs:build'
                        }
                    }
                    archiveArtifacts artifacts: 'dist/*', allowEmptyArchive: true
                    stash includes: 'dist/**', name: 'dist'
                }

                if (isChange()) {
                    stage('Docs preview') {
                        timeout(time: 15, unit: 'MINUTES') {
                            // The default version is from git describe, and the checkout has no tags.
                            String version = sh(script: 'git rev-parse --short=8 HEAD',
                                                returnStdout: true).trim()
                            createBuildStorage(buildType: 'change',
                                               version: version,
                                               archive: false,
                                               project: 'acconeer-python-exploration')

                            def stageFolder = createAndStore(stageName: env.STAGE_NAME,
                                                             nodeLabel: 'docker',
                                                             status: true,
                                                             artifacts: ['docs/_build/html'])

                            previewUrl = getBuildStorageUrl(stage: stageFolder,
                                                            path: 'docs/_build/html/index.html')

                            // Reviewers can read the docs before the tests finish.
                            gerritReview labels: [Verified: 0], message: "Docs preview: ${previewUrl}"
                        }
                    }
                }
            }
        }
    }

    parallel_steps['Mypy'] = {
        node('docker') {
            ws('workspace/exptool') {
                stage('Mypy') {
                    printNodeInfo()
                    checkoutAndCleanup()
                    buildDocker(path: 'docker').inside(dockerArgs) {
                        hatchWrap 'run mypy:check --no-incremental'
                    }
                }
            }
        }
    }

    parallel_steps[(
        "Test (py=${pythonVersions}, " +
        "rss_a121=${integrationTestA121RssVersions}, " +
        "rss_a111=${integrationTestA111RssVersions}, " +
        "rss_a2=${integrationTestA2RssVersions})"
    )] = {
        node('docker') {
            ws('workspace/exptool') {
                printNodeInfo()
                checkoutAndCleanup()

                stage("Fetch A111 stashes (${integrationTestA111RssVersions})") {
                    integrationTestA111RssVersions.each { rssVersion ->
                        def rssVersionName = rssVersion.getValue()
                        def stashFolder = "stash/a111/${rssVersionName}"

                        sh "mkdir -p ${stashFolder}"

                        findBuildAndCopyArtifacts(
                            [
                                projectName: 'sw-main',
                                artifactNames: ['out/internal_stash_binaries_sanitizer_a111.tgz'],
                                // e.g. (branch): 'master' or (tag): 'a111-vX.Y.Z'
                                (rssVersion.getKey()): rssVersion.getValue(),
                            ]
                        )
                        sh "tar -xzf out/internal_stash_binaries_sanitizer_a111.tgz -C ${stashFolder}"
                    }
                }

                stage("Fetch A121 stashes (${integrationTestA121RssVersions})") {
                    integrationTestA121RssVersions.each { rssVersion ->
                        def rssVersionName = rssVersion.getValue()
                        def stashFolder = "stash/a121/${rssVersionName}"

                        sh "mkdir -p ${stashFolder}"

                        findBuildAndCopyArtifacts(
                            [
                                projectName: 'sw-main',
                                artifactNames: ['out/internal_stash_binaries_sanitizer_a121.tgz'],
                                // e.g. (branch): 'master' or (tag): 'a121-vX.Y.Z'
                                (rssVersion.getKey()): rssVersion.getValue(),
                            ]
                        )
                        sh "tar -xzf out/internal_stash_binaries_sanitizer_a121.tgz -C ${stashFolder}"
                    }
                }

                stage("Fetch A121 model regression stashes ${modelTestA121RssVersion}") {
                    modelTestA121RssVersion.each { rssVersion ->
                        def rssVersionType = rssVersion.getKey()
                        def rssVersionName = rssVersion.getValue()
                        def stashFolder = "stash/model_a121/${rssVersionName}"
                        def artifacts = ['out/internal_stash_python_libs_a121.tgz', 'out/internal_stash_tests_a121.tgz']

                        sh "mkdir -p ${stashFolder}"

                        if (rssVersionType == 'commit') {
                            // A commit is not a build Jenkins can search for, so its
                            // artifacts are taken straight from the build storage folder.
                            retrieveArtifacts(
                                folder: rssVersionName,
                                stage: 'compile',
                                artifacts: artifacts
                            )
                        } else {
                            findBuildAndCopyArtifacts(
                                [
                                    projectName: 'sw-main',
                                    artifactNames: artifacts,
                                    // e.g. (branch): 'master' or (tag): 'a121-vX.Y.Z'
                                    (rssVersionType): rssVersionName,
                                ]
                            )
                        }
                        sh "tar -xzf out/internal_stash_python_libs_a121.tgz -C ${stashFolder}"
                        sh "tar -xzf out/internal_stash_tests_a121.tgz -C ${stashFolder}"
                    }
                }

                stage("Fetch A2 stashes (${integrationTestA2RssVersions})") {
                    integrationTestA2RssVersions.each { rssVersion ->
                        def rssVersionName = rssVersion.getValue()
                        def stashFolder = "stash/a2/${rssVersionName}"

                        sh "mkdir -p ${stashFolder}"

                        findBuildAndCopyArtifacts(
                            [
                                projectName: 'sw-main',
                                artifactNames: ["out/internal_stash_binaries_x86_64_a2r2.tgz"],
                            ] << rssVersion // e.g. [branch: 'master'] or [tag: 'a2-vX.Y.Z']
                        )
                        sh "tar -xzf out/internal_stash_binaries_x86_64_a2r2.tgz -C ${stashFolder}"
                    }
                }

                stage("Fetch A2 model stashes (${modelTestA2RssVersion})") {
                    modelTestA2RssVersion.each { rssVersion ->
                        def rssVersionType = rssVersion.getKey()
                        def rssVersionName = rssVersion.getValue()
                        def stashFolder = "stash/model_a2/${rssVersionName}"

                        sh "mkdir -p ${stashFolder}"

                        if (rssVersionType == 'commit') {
                            retrieveArtifacts(
                                folder: rssVersionName,
                                stage: 'compile',
                                artifacts: ['out/internal_stash_python_libs_a2.tgz', 'out/internal_stash_tests_a2r2.tgz', 'out/internal_stash_walle_project_a2r2.tgz']
                            )
                        } else {
                            findBuildAndCopyArtifacts(
                                [
                                    projectName: 'sw-main',
                                    artifactNames: ['out/internal_stash_python_libs_a2.tgz', 'out/internal_stash_tests_a2r2.tgz', 'out/internal_stash_walle_project_a2r2.tgz'],
                                ] << rssVersion // e.g. [branch: 'master'] or [tag: 'a2-vX.Y.Z']
                            )
                        }
                        sh "tar -xzf out/internal_stash_python_libs_a2.tgz -C ${stashFolder}"
                        sh "tar -xzf out/internal_stash_tests_a2r2.tgz -C ${stashFolder}"
                        sh "tar -xzf out/internal_stash_walle_project_a2r2.tgz -C ${stashFolder}"
                    }
                }

                String algoBundleZip
                stage('Fetch algo bundle') {
                    // A reused workspace still holds the zip of the build before
                    sh 'rm -f dist/acconeer_algo_bundle_*.zip'
                    // The algo bundle build the tests marked algo_bundle run on: its
                    // build storage folder. Its plugins' code must match this commit's,
                    // but every build reads the same credential, so moving it moves the
                    // pin of all of them.
                    withCredentials([string(credentialsId: 'et_module_bundle_folder',
                                            variable: 'ALGO_BUNDLE_FOLDER')])
                    {
                        retrieveArtifacts(folder: ALGO_BUNDLE_FOLDER, stage: 'build', artifacts: ['dist'])
                    }
                    def zips = findFiles(glob: 'dist/acconeer_algo_bundle_*.zip')
                    if (zips.size() != 1) {
                        error("Expected one dist/acconeer_algo_bundle_*.zip in the build that credential " +
                              "et_module_bundle_folder points to, found: ${zips}")
                    }
                    algoBundleZip = zips[0].path
                }

                stage("Run tests (${pythonVersions})") {
                    printNodeInfo()
                    buildDocker(path: 'docker').inside(dockerArgs) {
                        withCredentials([usernamePassword(credentialsId: 'tools-devsite',
                                                          passwordVariable: 'DEV_PASSWORD',
                                                          usernameVariable: 'DEV_USERNAME')])
                        {
                            String versionSelection = '-py=' + pythonVersions.join(',')
                            String devsiteSelection = buildScope == BuildScope.NIGHTLY ? '--test-devsite' : ''

                            def a121_es_binaries = findFiles(glob: (
                                'stash/a121/*/out/customer/a121/internal_sanitizer_x86_64/out/' +
                                'acc_exploration_server_a121'
                            ))
                            def a111_es_binaries = findFiles(glob: (
                                'stash/a111/*/out/customer/a111/internal_sanitizer_x86_64/out/' +
                                'acc_exploration_server_a111'
                            ))
                            def a2_es_binaries = findFiles(glob: (
                                'stash/a2/*/out/customer/a2/internal_linux_x86_64/out/' +
                                'acc_exploration_server_a2'
                            ))

                            def a121_sensor_current_limits_matches = findFiles(
                                glob: 'stash/model_a121/**/python_libs/**/sensor_current_limits.yaml'
                            )
                            def a121_module_current_limits_matches = findFiles(
                                glob: 'stash/model_a121/**/python_libs/**/module_current_limits.yaml'
                            )
                            def a121_inter_sweep_idle_state_current_limits_matches = findFiles(
                                glob: 'stash/model_a121/**/python_libs/**/inter_sweep_idle_states_limits.yaml'
                            )
                            def a121_memory_usage_yaml_matches = findFiles(
                                glob: 'stash/model_a121/**/tests/a121/**/memory_usage.yaml'
                            )

                            def a2_sensor_current_limits_matches = findFiles(
                                glob: 'stash/model_a2/**/python_libs/**/sensor_current_limits.yaml'
                            )
                            def a2_timing_limits_matches = findFiles(
                                glob: 'stash/model_a2/**/python_libs/**/timing_limits.yaml'
                            )
                            def a2_computation_limits_matches = findFiles(
                                glob: 'stash/model_a2/**/walle/**/computation_test/asserts.yaml'
                            )
                            def a2_memory_usage_yaml_matches = findFiles(
                                glob: 'stash/model_a2/**/tests/a2/**/memory_usage.yaml'
                            )

                            echo "a121_es_binaries=${a121_es_binaries}"
                            echo "a111_es_binaries=${a111_es_binaries}"
                            echo "a121_sensor_current_limits_matches=${a121_sensor_current_limits_matches}"
                            echo "a121_module_current_limits_matches=${a121_module_current_limits_matches}"
                            echo "a121_inter_sweep_idle_state_current_limits_matches=${a121_inter_sweep_idle_state_current_limits_matches}"
                            echo "a121_memory_usage_yaml_matches=${a121_memory_usage_yaml_matches}"

                            echo "a2_sensor_current_limits_matches=${a2_sensor_current_limits_matches}"
                            echo "a2_timing_limits_matches=${a2_timing_limits_matches}"
                            echo "a2_computation_limits_matches=${a2_computation_limits_matches}"
                            echo "a2_memory_usage_yaml_matches=${a2_memory_usage_yaml_matches}"

                            // The reference yamls are passed as --option=value: pytest
                            // parses the arguments before the conftest that defines the
                            // options, so a separate value is taken for a test path and
                            // collects the RSS repo's own conftest next to the yaml.
                            // The exploration server options take several values, which
                            // that form cannot express; they point at out/ directories
                            // with no conftest to pick up.
                            hatchWrap """test ${versionSelection} --parallel --cover tests/ src/ \
                                --a121-exploration-server-paths ${a121_es_binaries.join(' ')} \
                                --a111-exploration-server-paths ${a111_es_binaries.join(' ')} \
                                --a2-exploration-server-paths ${a2_es_binaries.join(" ")} \
                                --sensor-current-limits-path=${a121_sensor_current_limits_matches[0]} \
                                --module-current-limits-path=${a121_module_current_limits_matches[0]} \
                                --inter-sweep-idle-state-current-limits-path=${a121_inter_sweep_idle_state_current_limits_matches[0]} \
                                --memory-usage-path=${a121_memory_usage_yaml_matches[0]} \
                                --a2-sensor-current-limits-path=${a2_sensor_current_limits_matches[0]} \
                                --a2-timing-limits-path=${a2_timing_limits_matches[0]} \
                                --a2-computation-time-limits-path=${a2_computation_limits_matches[0]} \
                                --a2-memory-usage-path=${a2_memory_usage_yaml_matches[0]} \
                                --algo-bundle=${algoBundleZip} \
                                ${devsiteSelection}
                            """

                            hatchWrap "run test:coverage html --directory=htmlcov/"
                            archiveArtifacts artifacts: 'htmlcov/', allowEmptyArchive: false
                        }
                    }
                }
            }
        }
    }

    parallel_steps['failFast'] = buildScope != BuildScope.NIGHTLY

    parallel parallel_steps

    if (env.TAG_NAME ==~ version_regex) {
        node('docker') {
            ws('workspace/exptool') {
                printNodeInfo()
                checkoutAndCleanup()

                buildDocker(path: 'docker').inside(dockerArgs) {
                    env.TWINE_NON_INTERACTIVE = '1'
                    stage('Retrieve binaries from build step') {
                        unstash 'dist'
                    }
                    stage('Publish to Test PyPI') {
                        withCredentials([usernamePassword(credentialsId: 'testpypi',
                                                          passwordVariable: 'TWINE_PASSWORD',
                                                          usernameVariable: 'TWINE_USERNAME')])
                        {
                            sh 'twine upload -r testpypi dist/*'
                        }
                    }
                    stage('Publish to PyPI') {
                        withCredentials([usernamePassword(credentialsId: 'pypi',
                                                          passwordVariable: 'TWINE_PASSWORD',
                                                          usernameVariable: 'TWINE_USERNAME')])
                        {
                            sh 'twine upload dist/*'
                        }
                    }
                }
            }
        }
    }

    boolean updateReleaseBranches = buildTrigger == BuildTrigger.CRON_TIMER && buildScope == BuildScope.NIGHTLY
    boolean pushReleaseBranch = (buildScope == BuildScope.SANITY && isJenkinsMerge
                                 && currentBuild.currentResult == 'SUCCESS')

    if (updateReleaseBranches || pushReleaseBranch) {
        manageReleaseBranches(updateReleaseBranches)
    }
} catch (exception) {
    currentBuild.result = 'FAILURE'
}

finishBuild(messageOnFailure)
