import groovy.transform.Field

@Library('sw-jenkins-library@67e8e85f6bb9e8c6139a0477378160532c361d75') _

enum BuildScope {
    SANITY, HOURLY, NIGHTLY
}

@Field
def pythonVersionsForBuildScope = [
    (BuildScope.SANITY)  : ['3.12'],
    (BuildScope.HOURLY)  : ['3.12', '3.13'],
    (BuildScope.NIGHTLY) : ['3.12', '3.13'],
]

@Field
def integrationTestA121RssVersionsForBuildScope = [
    (BuildScope.SANITY)  : [branch: 'master'],
    (BuildScope.HOURLY)  : [tag: 'a121-v1.13.0'],
    (BuildScope.NIGHTLY) : [branch: 'master', tag: 'a121-v1.13.0'],
]

@Field
def integrationTestA111RssVersionsForBuildScope = [
    (BuildScope.SANITY)  : [],
    (BuildScope.HOURLY)  : [branch: 'master'],
    (BuildScope.NIGHTLY) : [branch: 'master', tag: 'a111-v2.15.5'],
]

@Field
def integrationTestA2RssVersionsForBuildScope = [
    (BuildScope.SANITY)  : [branch: 'master'],
    (BuildScope.HOURLY)  : [branch: 'master'],
    (BuildScope.NIGHTLY) : [branch: 'master'],
]

// Entries are [branch: ...], [tag: ...] or, for a build that carries no tag,
// [commit: '<build storage folder>'].
@Field
def modelTestA121RssVersionForBuildScope = [
    (BuildScope.SANITY)  : [commit: 'interim/sw-main/master/2026/2026-09-22/a2-v1.1.0-rc1-25-g4984fc76c6'],
    (BuildScope.HOURLY)  : [commit: 'interim/sw-main/master/2026/2026-09-22/a2-v1.1.0-rc1-25-g4984fc76c6'],
    (BuildScope.NIGHTLY) : [commit: 'interim/sw-main/master/2026/2026-09-22/a2-v1.1.0-rc1-25-g4984fc76c6'],
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

BuildScope getBuildScope() {
    if (currentBuild.getBuildCauses('hudson.triggers.TimerTrigger$TimerTriggerCause').isEmpty()) {
        // currentBuild was not triggered by a cron timer
        // => probably triggered by a change
        // => run sanity scope.
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
        gerritReview labels: [Verified: score], message: message
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

    def buildScope = getBuildScope()

    def pythonVersions = pythonVersionsForBuildScope[buildScope]
    def integrationTestA121RssVersions = integrationTestA121RssVersionsForBuildScope[buildScope]
    def integrationTestA111RssVersions = integrationTestA111RssVersionsForBuildScope[buildScope]
    def integrationTestA2RssVersions = integrationTestA2RssVersionsForBuildScope[buildScope]
    def modelTestA121RssVersion = modelTestA121RssVersionForBuildScope[buildScope]
    def modelTestA2RssVersion = modelTestA2RssVersionForBuildScope[buildScope]

    if (env.BRANCH_NAME =~ /[0-9]+\/[0-9]+\/[0-9]+/) {
        buildType = 'change'
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

    parallel_steps = [:]

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

                stage("Fetch A2 stashes (${integrationTestA2RssVersions})") {
                    integrationTestA2RssVersions.each { rssVersion ->
                        def rssVersionName = rssVersion.getValue()
                        def stashFolder = "stash/a2/${rssVersionName}"

                        sh "mkdir -p ${stashFolder}"

                        findBuildAndCopyArtifacts(
                            [
                                projectName: 'sw-main',
                                artifactNames: ['out/internal_stash_binaries_x86_64_a2r2.tgz'],
                                // e.g. (branch): 'master' or (tag): 'a2-vX.Y.Z'
                                (rssVersion.getKey()): rssVersion.getValue(),
                            ]
                        )
                        sh "tar -xzf out/internal_stash_binaries_x86_64_a2r2.tgz -C ${stashFolder}"
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
                            echo "a2_es_binaries=${a2_es_binaries}"
                            echo "a121_sensor_current_limits_matches=${a121_sensor_current_limits_matches}"
                            echo "a121_module_current_limits_matches=${a121_module_current_limits_matches}"
                            echo "a121_inter_sweep_idle_state_current_limits_matches=${a121_inter_sweep_idle_state_current_limits_matches}"
                            echo "a121_memory_usage_yaml_matches=${a121_memory_usage_yaml_matches}"

                            echo "a2_sensor_current_limits_matches=${a2_sensor_current_limits_matches}"
                            echo "a2_timing_limits_matches=${a2_timing_limits_matches}"
                            echo "a2_computation_limits_matches=${a2_computation_limits_matches}"
                            echo "a2_memory_usage_yaml_matches=${a2_memory_usage_yaml_matches}"

                            // The A2 reference yamls are passed as --option=value: pytest
                            // parses the arguments before the conftest that defines the
                            // options, so a separate value is taken for a test path and
                            // collects the RSS repo's own conftest next to the yaml.
                            hatchWrap """test ${versionSelection} --parallel --cover tests/ src/ \
                                --a121-exploration-server-paths ${a121_es_binaries.join(' ')} \
                                --a111-exploration-server-paths ${a111_es_binaries.join(' ')} \
                                --a2-exploration-server-paths ${a2_es_binaries.join(' ')} \
                                --sensor-current-limits-path ${a121_sensor_current_limits_matches[0]} \
                                --module-current-limits-path ${a121_module_current_limits_matches[0]} \
                                --inter-sweep-idle-state-current-limits-path \
                                    ${a121_inter_sweep_idle_state_current_limits_matches[0]} \
                                --memory-usage-path ${a121_memory_usage_yaml_matches[0]} \
                                --a2-sensor-current-limits-path=${a2_sensor_current_limits_matches[0]} \
                                --a2-timing-limits-path=${a2_timing_limits_matches[0]} \
                                --a2-computation-time-limits-path=${a2_computation_limits_matches[0]} \
                                --a2-memory-usage-path=${a2_memory_usage_yaml_matches[0]} \
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

    parallel_steps['failFast'] = true

    parallel parallel_steps

    // Only matches version on the form "vX.Y.Z" where X, Y, Z are integers
    version_regex = /v\d+\.\d+\.\d+/

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

    boolean updateReleaseBranches = buildScope == BuildScope.NIGHTLY
    boolean pushReleaseBranch = (buildScope == BuildScope.SANITY && isJenkinsMerge
                                 && currentBuild.currentResult == 'SUCCESS')

    if (updateReleaseBranches || pushReleaseBranch) {
        manageReleaseBranches(updateReleaseBranches)
    }
} catch (exception) {
    currentBuild.result = 'FAILURE'
}

finishBuild(messageOnFailure)
