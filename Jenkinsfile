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


try {
    // Ensure cron triggers are setup (for periodic jobs)
    properties([getCronTriggers(env.BRANCH_NAME)])

    def buildScope = getBuildScope()

    def isolatedTestPythonVersions = isolatedTestPythonVersionsForBuildScope[buildScope]
    def integrationTestPythonVersions = integrationTestPythonVersionsForBuildScope[buildScope]

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

    parallel_steps["Mock test (${integrationTestPythonVersions})"] = {
        node('docker') {
            ws('workspace/exptool') {
                stage('Setup') {
                    printNodeInfo()
                    checkoutAndCleanup()

                    findBuildAndCopyArtifacts(
                        projectName: 'sw-main',
                        branch: "master",
                        artifactNames: [
                            "out/internal_stash_binaries_sanitizer_a111.tgz",
                            "out/internal_stash_binaries_sanitizer_a121.tgz"
                        ]
                    )
                    sh 'mkdir stash'
                    sh 'tar -xzf out/internal_stash_binaries_sanitizer_a111.tgz -C stash'
                    sh 'tar -xzf out/internal_stash_binaries_sanitizer_a121.tgz -C stash'
                }
                stage("Run integration tests (${integrationTestPythonVersions})") {
                    buildDocker(path: 'docker').inside(dockerArgs(env)) {
                        integrationTestPythonVersions.each { v -> sh "python${v} -V" }
                        List<String> doitTasksA111 = integrationTestPythonVersions
                                                        .collect { v -> "integration_test:${v}-a111" }
                        List<String> doitTasksA121 = integrationTestPythonVersions
                                                        .collect { v -> "integration_test:${v}-a121" }
                        // A111 & A121 needs to run sequentially since they use the same python verions
                        // installing the same package simultaneously on 2 processes is flaky
                        sh "doit -f dodo.py -n ${doitTasksA111.size()} " + doitTasksA111.join(' ')
                        sh "doit -f dodo.py -n ${doitTasksA121.size()} " + doitTasksA121.join(' ')
                    }
                }
            }
        }
    }

    parallel_steps["XM112 test (${integrationTestPythonVersions})"] = {
        node('exploration_tool') {
            ws('workspace/exptool') {
                def dockerImg = null

                stage('Setup') {
                    printNodeInfo()
                    checkoutAndCleanup()

                    findBuildAndCopyArtifacts(
                        projectName: 'sw-main',
                        branch: "master",
                        artifactNames: [
                            "out/internal_stash_python_libs.tgz",
                            "out/internal_stash_binaries_xm112.tgz",
                        ]
                    )
                    sh 'mkdir stash'
                    sh 'tar -xzf out/internal_stash_python_libs.tgz -C stash'
                    sh 'tar -xzf out/internal_stash_binaries_xm112.tgz -C stash'
                    dockerImg = buildDocker(path: 'docker')
                }
                lock("${env.NODE_NAME}-xm112") {
                    stage ('Flash') {
                        sh '(cd stash && python3 python_libs/test_utils/flash.py)'
                    }
                    dockerImg.inside(dockerArgs(env) + " --net=host --privileged") {
                        integrationTestPythonVersions.each { v ->
                            stage("Run integration tests (${v})") {
                                sh "tests/run-a111-xm112-integration-tests.sh ${v}"
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
    stage('Report result to gerrit') {
        echo "Reporting Fail to Gerrit"
        gerritReview labels: [Verified: -1], message: "Failed: ${env.BUILD_URL}, Duration: ${currentBuild.durationString - ' and counting'}"
    }
    throw exception
}
