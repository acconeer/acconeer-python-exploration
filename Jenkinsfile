import groovy.transform.Field
@Library('sw-jenkins-library@5b8b388ad04b20e2c23de08b17885401fa8dbce4') _

enum BuildScope {
    SANITY, HOURLY, NIGHTLY
}

@Field
def isolatedTestPythonVersionsForBuildScope = [
    (BuildScope.SANITY)  : ["3.8", "3.9"],
    (BuildScope.HOURLY)  : ["3.8", "3.10", "3.11"],
    (BuildScope.NIGHTLY) : ["3.8", "3.9", "3.10", "3.11", "3.12"],
]

@Field
def integrationTestPythonVersionsForBuildScope = [
    (BuildScope.SANITY)  : ["3.8"],
    (BuildScope.HOURLY)  : ["3.9"],
    (BuildScope.NIGHTLY) : ["3.8", "3.9", "3.10", "3.11", "3.12"],
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

    def isolatedTestPythonVersions = isolatedTestPythonVersionsForBuildScope[buildScope]
    def integrationTestPythonVersions = integrationTestPythonVersionsForBuildScope[buildScope]
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

    parallel_steps["Model Regression Tests (${modelTestA121RssVersion})"] = {
        node('docker') {
            ws('workspace/exptool') {
                modelTestA121RssVersion.each { rssVersion ->
                    stage('Setup') {
                        printNodeInfo()
                        checkoutAndCleanup()

                        findBuildAndCopyArtifacts(
                            [
                                projectName: 'sw-main',
                                artifactNames: ["out/internal_stash_python_libs.tgz"],
                            ] << rssVersion // e.g. [branch: 'master'] or [tag: 'a121-vX.Y.Z']
                        )
                        sh 'mkdir -p stash'
                        sh 'tar -xzf out/internal_stash_python_libs.tgz -C stash'
                    }
                    stage("Model Regression Tests (rss=${modelTestA121RssVersion})") {
                        buildDocker(path: 'docker').inside(dockerArgs(env)) {
                            hatchWrap 'test -py=3.8 tests/model'
                        }
                    }
                }
            }
        }
    }

    parallel_steps["Isolated tests (${isolatedTestPythonVersions})"] = {
        node('docker') {
            ws('workspace/exptool') {
                stage("Isolated tests (${isolatedTestPythonVersions})") {
                    printNodeInfo()
                    checkoutAndCleanup()

                    buildDocker(path: 'docker').inside(dockerArgs(env)) {
                        isolatedTestPythonVersions.each { v -> sh "python${v} -V" }
                        String versionSelection = "-py=" + isolatedTestPythonVersions.join(",")
                        hatchWrap "test ${versionSelection} --parallel tests/unit tests/processing tests/app src/acconeer/exptool tests/examples"
                    }
                }
            }
        }
    }

    parallel_steps["A121 Mock test (py=${integrationTestPythonVersions}, rss=${integrationTestA121RssVersions})"] = {
        node('docker') {
            ws('workspace/exptool') {
                integrationTestA121RssVersions.each { rssVersion ->
                    def rssVersionName = rssVersion.getValue()

                    stage("Setup (rss=${rssVersionName})") {
                        printNodeInfo()
                        checkoutAndCleanup()

                        findBuildAndCopyArtifacts(
                            [
                                projectName: 'sw-main',
                                artifactNames: ["out/internal_stash_binaries_sanitizer_a121.tgz"],
                            ] << rssVersion // e.g. [branch: 'master'] or [tag: 'a121-vX.Y.Z']
                        )
                        findBuildAndCopyArtifacts(
                            [
                                projectName: 'sw-main',
                                artifactNames: ["out/internal_stash_python_libs.tgz"],
                            ] << rssVersion // e.g. [branch: 'master'] or [tag: 'a121-vX.Y.Z']
                        )
                        sh 'mkdir stash'
                        sh 'tar -xzf out/internal_stash_binaries_sanitizer_a121.tgz -C stash'
                        sh 'tar -xzf out/internal_stash_python_libs.tgz -C stash'
                    }
                    stage("Run integration tests (py=${integrationTestPythonVersions}, rss=${rssVersionName})") {
                        buildDocker(path: 'docker').inside(dockerArgs(env)) {
                            String versionSelection = "-py=" + integrationTestPythonVersions.join(",")
                            hatchWrap "test ${versionSelection} tests/integration/a121"
                        }
                    }
                }
            }
        }
    }

    parallel_steps["A111 Mock test (py=${integrationTestPythonVersions}, rss=${integrationTestA111RssVersions})"] = {
        node('docker') {
            ws('workspace/exptool') {
                integrationTestA111RssVersions.each { rssVersion ->
                    def rssVersionName = rssVersion.getValue()

                    stage("Setup (rss=${rssVersionName})") {
                        printNodeInfo()
                        checkoutAndCleanup()

                        findBuildAndCopyArtifacts(
                            [
                                projectName: 'sw-main',
                                artifactNames: ["out/internal_stash_binaries_sanitizer_a111.tgz"],
                            ] << rssVersion // e.g. [branch: 'master'] or [tag: 'a111-vX.Y.Z']
                        )
                        sh 'mkdir stash'
                        sh 'tar -xzf out/internal_stash_binaries_sanitizer_a111.tgz -C stash'
                    }
                    stage("Run integration tests (py=${integrationTestPythonVersions}, rss=${rssVersionName})") {
                        buildDocker(path: 'docker').inside(dockerArgs(env)) {
                            integrationTestPythonVersions.each { v -> sh "python${v} -V" }
                            String versionSelection = "-py=" + integrationTestPythonVersions.join(",")
                            hatchWrap "test ${versionSelection} tests/integration/a111"
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
