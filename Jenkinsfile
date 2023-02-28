import groovy.transform.Field
@Library('sw-jenkins-library@f8abd2e69ceef2d37e8ab7f1fbc294e34ac04670') _

@Field
def isolatedTestPythonVersions = ["3.8"]

@Field
def integrationTestPythonVersions = ["3.8"]


String dockerArgs(env_map) {
  return "--hostname ${env_map.NODE_NAME}" +
         " --mount type=volume,src=cachepip-${env_map.EXECUTOR_NUMBER},dst=/home/jenkins/.cache/pip"
}


try {
    stage('Report start to Gerrit') {
        gerritReview labels: [Verified: 0], message: "Test started:: ${env.BUILD_URL}"
    }

    // Meant to catch common (and fast to detect) errors.
    stage('Lint') {
        node('docker') {
            ws('workspace/exptool') {
                printNodeInfo()
                checkoutAndCleanup(lfs: false)

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
                    checkoutAndCleanup(lfs: false)

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
                    checkoutAndCleanup(lfs: false)
                    buildDocker(path: 'docker').inside(dockerArgs(env)) {
                        sh 'python3 -V'
                        sh 'nox -s mypy'
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
                    checkoutAndCleanup(lfs: false)

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
                    checkoutAndCleanup(lfs: false)

                    findBuildAndCopyArtifacts(
                        projectName: 'sw-main',
                        revision: "master",
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

    integrationTestPythonVersions.each { pythonVersion ->
        parallel_steps["XM112 test (${pythonVersion})"] = {
            node('exploration_tool') {
                ws('workspace/exptool') {
                    stage('Setup') {
                        printNodeInfo()
                        checkoutAndCleanup(lfs: false)

                        findBuildAndCopyArtifacts(
                            projectName: 'sw-main',
                            revision: "master",
                            artifactNames: [
                                "out/internal_stash_python_libs.tgz",
                                "out/internal_stash_binaries_xm112.tgz",
                            ]
                        )
                        sh 'mkdir stash'
                        sh 'tar -xzf out/internal_stash_python_libs.tgz -C stash'
                        sh 'tar -xzf out/internal_stash_binaries_xm112.tgz -C stash'
                    }
                    lock("${env.NODE_NAME}-xm112") {
                        stage ('Flash') {
                            sh '(cd stash && python3 python_libs/test_utils/flash.py)'
                        }
                        stage('Run integration tests') {
                            buildDocker(path: 'docker').inside(dockerArgs(env) + " --net=host --privileged") {
                                sh "tests/run-a111-xm112-integration-tests.sh ${pythonVersion}"
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
                checkoutAndCleanup(lfs: false)

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
