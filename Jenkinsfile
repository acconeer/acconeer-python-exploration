import groovy.transform.Field
@Library('sw-jenkins-library@5b8b388ad04b20e2c23de08b17885401fa8dbce4') _

enum BuildScope {
    SANITY, HOURLY, NIGHTLY
}

@Field
def pythonVersionsForBuildScope = [
    (BuildScope.SANITY)  : ["3.9", "3.13"],
    (BuildScope.HOURLY)  : ["3.10", "3.11", "3.12"],
    (BuildScope.NIGHTLY) : ["3.9", "3.10", "3.11", "3.12", "3.13"],
]

@Field
def integrationTestA121RssVersionsForBuildScope = [
    (BuildScope.SANITY)  : [branch: "master"],
    (BuildScope.HOURLY)  : [tag: "a121-v1.8.1"],
    (BuildScope.NIGHTLY) : [branch: "master", tag: "a121-v1.8.1"],
]

@Field
def integrationTestA111RssVersionsForBuildScope = [
    (BuildScope.SANITY)  : [branch: "master"],
    (BuildScope.HOURLY)  : [],
    (BuildScope.NIGHTLY) : [branch: "master", tag: "a111-v2.15.4"],
]

@Field
def modelTestA121RssVersionForBuildScope = [
    (BuildScope.SANITY)  : [tag: "a121-v1.8.1"],
    (BuildScope.HOURLY)  : [],
    (BuildScope.NIGHTLY) : [],
]

String dockerArgs(env_map) {
  return "--hostname ${env_map.NODE_NAME}" +
         " --mount type=volume,src=cachepip-${env_map.EXECUTOR_NUMBER},dst=/home/jenkins/.cache/pip" +
         " --mount type=volume,src=cacheuv,dst=/home/jenkins/.cache/uv"
}

def messageOnFailure = true

def getCronTriggers(String branchName) {
    def triggers = []

    if (branchName == 'master') {
        // Hourly: every hour between 9:00 & 17:00, Monday through Friday
        // Nightly: every day at 23:00
        triggers << cron("0 9-17 * * 1-5\n0 23 * * *")
    }

    return pipelineTriggers(triggers)
}

def hatchWrap (command) {
    // Ensure the presence of '_version.py'
    // (See https://github.com/ofek/hatch-vcs?tab=readme-ov-file#write-version-to-file)
    sh 'hatch build --hooks-only'
    // Run a hatch command
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
    } else {
        return BuildScope.NIGHTLY
    }
}

def finishBuild(messageOnFailure) {
    stage('Report to gerrit') {
        int score = currentBuild.currentResult == 'SUCCESS' ? 1 : -1
        String success = currentBuild.currentResult == 'SUCCESS' ? "success" : "failure"
        String message = "${currentBuild.currentResult}: ${env.BUILD_URL}, Duration: ${currentBuild.durationString - ' and counting'}"
        gerritReview labels: [Verified: score], message: message
    }

    if (messageOnFailure && (currentBuild.currentResult == 'FAILURE')) {
        withCredentials([string(credentialsId: 'teams-robot', variable: 'TEAMS_API_TOKEN')]) {
            office365ConnectorSend webhookUrl: TEAMS_API_TOKEN
        }
    }
}

try {
    // Ensure cron triggers are setup (for periodic jobs)
    properties([getCronTriggers(env.BRANCH_NAME)])

    def buildScope = getBuildScope()

    def pythonVersions = pythonVersionsForBuildScope[buildScope]
    def integrationTestA121RssVersions = integrationTestA121RssVersionsForBuildScope[buildScope]
    def integrationTestA111RssVersions = integrationTestA111RssVersionsForBuildScope[buildScope]
    def modelTestA121RssVersion = modelTestA121RssVersionForBuildScope[buildScope]

    if (env.BRANCH_NAME =~ /[0-9]+\/[0-9]+\/[0-9]+/) {
        buildType = "change"
        messageOnFailure = false
    }

    stage('Report start to Gerrit') {
        gerritReview labels: [Verified: 0], message: "Test started:: ${env.BUILD_URL}, Scope: ${buildScope}"
    }

    // Meant to catch common (and fast to detect) errors.
    stage('Lint') {
        node('docker') {
            ws('workspace/exptool') {
                printNodeInfo()
                checkoutAndCleanup()

                buildDocker(path: 'docker').inside(dockerArgs(env)) {
                    sh 'python3 -V'
                    hatchWrap 'fmt --check'
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

                    buildDocker(path: 'docker').inside(dockerArgs(env)) {
                        sh 'python3 -V'
                        hatchWrap 'build'
                        hatchWrap 'run docs:build'
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
                    buildDocker(path: 'docker').inside(dockerArgs(env)) {
                        hatchWrap 'run mypy:check --no-incremental'
                    }
                }
            }
        }
    }

    parallel_steps["Test (py=${pythonVersions}, rss_a121=${integrationTestA121RssVersions}, rss_a111=${integrationTestA111RssVersions})"] = {
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
                                artifactNames: ["out/internal_stash_binaries_sanitizer_a111.tgz"],
                            ] << rssVersion // e.g. [branch: 'master'] or [tag: 'a111-vX.Y.Z']
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
                                artifactNames: ["out/internal_stash_binaries_sanitizer_a121.tgz"],
                            ] << rssVersion // e.g. [branch: 'master'] or [tag: 'a121-vX.Y.Z']
                        )
                        sh "tar -xzf out/internal_stash_binaries_sanitizer_a121.tgz -C ${stashFolder}"
                    }
                }

                stage("Fetch A121 model regression stashes ${modelTestA121RssVersion}") {
                    modelTestA121RssVersion.each { rssVersion ->
                        def rssVersionName = rssVersion.getValue()
                        def stashFolder = "stash/model_a121/${rssVersionName}"

                        sh "mkdir -p ${stashFolder}"

                        findBuildAndCopyArtifacts(
                            [
                                projectName: 'sw-main',
                                artifactNames: ["out/internal_stash_python_libs.tgz"],
                            ] << rssVersion // e.g. [branch: 'master'] or [tag: 'a121-vX.Y.Z']
                        )
                        sh "tar -xzf out/internal_stash_python_libs.tgz -C ${stashFolder}"
                    }
                }

                stage("Run tests (${pythonVersions})") {
                    buildDocker(path: 'docker').inside(dockerArgs(env)) {
                        String versionSelection = "-py=" + pythonVersions.join(",")

                        def a121_es_binaries = findFiles glob: 'stash/a121/*/out/customer/a121/internal_sanitizer_x86_64/out/acc_exploration_server_a121'
                        def a111_es_binaries = findFiles glob: 'stash/a111/*/out/customer/a111/internal_sanitizer_x86_64/out/acc_exploration_server_a111'

                        def a121_sensor_current_limits_matches = findFiles glob: "stash/model_a121/**/python_libs/**/sensor_current_limits.yaml"
                        def a121_module_current_limits_matches = findFiles glob: "stash/model_a121/**/python_libs/**/module_current_limits.yaml"
                        def a121_inter_sweep_idle_state_current_limits_matches = findFiles glob: "stash/model_a121/**/python_libs/**/inter_sweep_idle_states_limits.yaml"
                        def a121_memory_usage_yaml_matches = findFiles glob: "stash/model_a121/**/python_libs/**/memory_usage.yaml"

                        hatchWrap """test ${versionSelection} --parallel tests/ src/ \
                            --a121-exploration-server-paths ${a121_es_binaries.join(" ")} \
                            --a111-exploration-server-paths ${a111_es_binaries.join(" ")} \
                            --sensor-current-limits-path ${a121_sensor_current_limits_matches[0]} \
                            --module-current-limits-path ${a121_module_current_limits_matches[0]} \
                            --inter-sweep-idle-state-current-limits-path ${a121_inter_sweep_idle_state_current_limits_matches[0]} \
                            --memory-usage-path ${a121_memory_usage_yaml_matches[0]}
                        """
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

                buildDocker(path: 'docker').inside(dockerArgs(env)) {
                    env.TWINE_NON_INTERACTIVE = '1'
                    stage('Retrieve binaries from build step') {
                        unstash 'dist'
                    }
                    stage('Publish to Test PyPI') {
                        withCredentials([usernamePassword(credentialsId: 'testpypi', passwordVariable: 'TWINE_PASSWORD', usernameVariable: 'TWINE_USERNAME')]) {
                            sh 'python3 -m twine upload -r testpypi dist/*'
                        }
                    }
                    stage('Publish to PyPI') {
                        withCredentials([usernamePassword(credentialsId: 'pypi', passwordVariable: 'TWINE_PASSWORD', usernameVariable: 'TWINE_USERNAME')]) {
                            sh 'python3 -m twine upload dist/*'
                        }
                    }
                }
            }
        }
    }

    stage('Manage release branches') {
        node('docker') {
            ws('workspace/exptool') {
                printNodeInfo()
                checkoutAndCleanup()

                buildDocker(path: 'docker').inside(dockerArgs(env)) {
                    withCredentials([gitUsernamePassword(credentialsId: '1bef2b16-6cd9-4836-a014-421199e7fb0f'),
                                     string(variable: 'RELEASE_BRANCHES', credentialsId: 'et_update_release_branches')]) {
                        if (buildScope == BuildScope.NIGHTLY) {
                            sh "git config user.name 'Jenkins Builder'"
                            sh "git config user.email 'ai@acconeer.com'"
                            sh "tests/release_branch/release_branch_update.sh -b ${env.BRANCH_NAME} -p ${RELEASE_BRANCHES}"
                        } else if (buildScope == BuildScope.SANITY && currentBuild.currentResult == 'SUCCESS') {
                            sh "tests/release_branch/release_branch_push.sh -b ${env.BRANCH_NAME} -p ${RELEASE_BRANCHES}"
                        }
                    }
                }
            }
        }
    }
} catch (exception) {
    currentBuild.result = 'FAILURE'
}

finishBuild(messageOnFailure)
