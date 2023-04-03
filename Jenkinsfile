import groovy.transform.Field
@Library('sw-jenkins-library@1c4f7b55ac3559620ccbc54a847f5bb46c172619') _

enum BuildScope {
    SANITY, HOURLY, NIGHTLY
}

@Field
def isolatedTestPythonVersionsForBuildScope = [
    (BuildScope.SANITY)  : ["3.7", "3.9"],
    (BuildScope.HOURLY)  : ["3.8", "3.10", "3.11"],
    (BuildScope.NIGHTLY) : ["3.7", "3.8", "3.9", "3.10", "3.11"],
]

@Field
def integrationTestPythonVersionsForBuildScope = [
    (BuildScope.SANITY)  : ["3.7"],
    (BuildScope.HOURLY)  : ["3.9"],
    (BuildScope.NIGHTLY) : ["3.7", "3.8", "3.9", "3.10", "3.11"],
]

@Field
def integrationTestA121RssVersionsForBuildScope = [
    (BuildScope.SANITY)  : [branch: "master"],
    (BuildScope.HOURLY)  : [tag: "a121-v1.0.0"],
    (BuildScope.NIGHTLY) : [branch: "master", tag: "a121-v1.0.0"],
]

@Field
def integrationTestA111RssVersionsForBuildScope = [
    (BuildScope.SANITY)  : [branch: "master"],
    (BuildScope.HOURLY)  : [],
    (BuildScope.NIGHTLY) : [branch: "master", tag: "a111-v2.14.2"],
]


String dockerArgs(env_map) {
  return "--hostname ${env_map.NODE_NAME}" +
         " --mount type=volume,src=cachepip-${env_map.EXECUTOR_NUMBER},dst=/home/jenkins/.cache/pip"
}

def getCronTriggers(String branchName) {
    def triggers = []

    if (branchName == 'master') {
        // Hourly: every hour between 9:00 & 17:00, Monday through Friday
        // Nightly: every day at 23:00
        triggers << cron("0 9-17 * * 1-5\n0 23 * * *")
    }

    return pipelineTriggers(triggers)
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

def finishBuild() {
    stage('Report to gerrit') {
        int score = currentBuild.currentResult == 'SUCCESS' ? 1 : -1
        String success = currentBuild.currentResult == 'SUCCESS' ? "success" : "failure"
        String message = "${currentBuild.currentResult}: ${env.BUILD_URL}, Duration: ${currentBuild.durationString - ' and counting'}"
        gerritReview labels: [Verified: score], message: message
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
                    sh 'nox -s lint'
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
                        sh 'python3 -m build'
                        sh 'nox -s docs -- --docs-builders html latexpdf rediraffecheckdiff'
                    }
                    archiveArtifacts artifacts: 'dist/*', allowEmptyArchive: true
                    archiveArtifacts artifacts: 'docs/_build/latex/*.pdf', allowEmptyArchive: true
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
                        sh '''nox -s "mypy(python='3.7')"'''
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
                        List<String> doitTasks = isolatedTestPythonVersions
                                                    .collect { v -> "test:${v}" }

                        sh "doit -f dodo.py -n ${doitTasks.size()} " + doitTasks.join(' ')
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
                            ] << rssVersion // e.g. [branch: 'master'] or [tag: 'a121-v1.0.0']
                        )
                        sh 'mkdir stash'
                        sh 'tar -xzf out/internal_stash_binaries_sanitizer_a121.tgz -C stash'
                    }
                    stage("Run integration tests (py=${integrationTestPythonVersions}, rss=${rssVersionName})") {
                        buildDocker(path: 'docker').inside(dockerArgs(env)) {
                            integrationTestPythonVersions.each { v -> sh "python${v} -V" }

                            List<String> doitTasks = integrationTestPythonVersions
                                                            .collect { v -> "integration_test:${v}-a121" }

                            sh "doit -f dodo.py port_strategy=unique -n ${doitTasks.size()} " + doitTasks.join(' ')
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
                            ] << rssVersion // e.g. [branch: 'master'] or [tag: 'a111-v2.14.2']
                        )
                        sh 'mkdir stash'
                        sh 'tar -xzf out/internal_stash_binaries_sanitizer_a111.tgz -C stash'
                    }
                    stage("Run integration tests (py=${integrationTestPythonVersions}, rss=${rssVersionName})") {
                        buildDocker(path: 'docker').inside(dockerArgs(env)) {
                            integrationTestPythonVersions.each { v -> sh "python${v} -V" }

                            List<String> doitTasks = integrationTestPythonVersions
                                                            .collect { v -> "integration_test:${v}-a111" }

                            sh "doit -f dodo.py port_strategy=unique -n ${doitTasks.size()} " + doitTasks.join(' ')
                        }
                    }
                }
            }
        }
    }

    parallel_steps["XM112 test (py=${integrationTestPythonVersions}, rss=${integrationTestA111RssVersions})"] = {
        node('exploration_tool') {
            ws('workspace/exptool') {
                integrationTestA111RssVersions.each { rssVersion ->
                    def rssVersionName = rssVersion.getValue()

                    def dockerImg = null
                    stage("Setup (rss=${rssVersionName})") {
                        printNodeInfo()
                        checkoutAndCleanup()

                        findBuildAndCopyArtifacts(
                            [
                                projectName: 'sw-main',
                                artifactNames: [
                                    "out/internal_stash_python_libs.tgz",
                                    "out/internal_stash_binaries_xm112.tgz",
                                ]
                            ] << rssVersion // e.g. [branch: 'master'] or [tag: 'a111-v2.14.2']
                        )
                        sh 'mkdir stash'
                        sh 'tar -xzf out/internal_stash_python_libs.tgz -C stash'
                        sh 'tar -xzf out/internal_stash_binaries_xm112.tgz -C stash'
                        dockerImg = buildDocker(path: 'docker')
                    }
                    lock("${env.NODE_NAME}-xm112") {
                        stage ("Flash (rss=${rssVersionName})") {
                            sh '(cd stash && python3 python_libs/test_utils/flash.py)'
                        }
                        dockerImg.inside(dockerArgs(env) + " --net=host --privileged") {
                            integrationTestPythonVersions.each { pythonVersion ->
                                stage("Run integration tests (py=${pythonVersion}, rss=${rssVersionName})") {
                                    sh "tests/run-a111-xm112-integration-tests.sh ${pythonVersion}"
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    parallel_steps['failFast'] = true

    parallel parallel_steps

    if (env.TAG_NAME ==~ /v.*/) {
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
                checkoutAndCleanup(lfs: false)

                buildDocker(path: 'docker').inside(dockerArgs(env)) {
                    withCredentials([gitUsernamePassword(credentialsId: '1bef2b16-6cd9-4836-a014-421199e7fb0f')]) {
                        if (buildScope == BuildScope.NIGHTLY) {
                            sh '''#!/bin/bash

                                git config user.name "Jenkins Builder"
                                git config user.email "ai@acconeer.com"

                                tests/release_branch/release_branch_update.sh -p
                            '''
                        } else if (buildScope == BuildScope.SANITY && currentBuild.currentResult == 'SUCCESS') {
                            sh 'tests/release_branch/release_branch_push.sh'
                        }
                    }
                }
            }
        }
    }

    stage('Report to gerrit') {
        if (currentBuild.currentResult == 'SUCCESS') {
            echo "Reporting OK to Gerrit"
            gerritReview labels: [Verified: 1], message: "Success: ${env.BUILD_URL}, Duration: ${currentBuild.durationString - ' and counting'}"
        } else {
            echo "Reporting Fail to Gerrit"
            gerritReview labels: [Verified: -1], message: "Failed: ${env.BUILD_URL}, Duration: ${currentBuild.durationString - ' and counting'}"
        }
    }
} catch (exception) {
    currentBuild.result = 'FAILURE'
}

finishBuild()
