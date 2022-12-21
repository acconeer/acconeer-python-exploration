@Library('sw-jenkins-library@d4f738452cd3f82f845e4ba508970464a4cb156c') _

def printNodeInfo() {
    def (String workDir, String uname) = sh (script: 'pwd && uname -a', returnStdout: true).trim().readLines()
    echo "Running on ${env.NODE_NAME} in directory ${workDir}, uname: ${uname}"
}

try {
    stage('Report start to Gerrit') {
        gerritReview labels: [Verified: 0], message: "Test started:: ${env.BUILD_URL}"
    }

    parallel 'Build and run standalone tests' : {
        node('docker') {
            ws('workspace/exptool') {
                stage('Build and run standalone tests') {
                    printNodeInfo()
                    def scmVars = checkout scm
                    sh 'git clean -xdf'
                    echo "scmVars=${scmVars}"

                    String stageStart = getCurrentTime()
                    def image = buildDocker(path: 'docker')

                    image.inside("--hostname ${env.NODE_NAME}" +
                                " --mount type=volume,src=cachepip-${EXECUTOR_NUMBER},dst=/home/jenkins/.cache/pip") {
                        sh 'python3 -V'
                        sh 'python3 -m build'
                        sh 'nox --no-error-on-missing-interpreters -s lint docs test -- --test-groups unit integration --docs-builders html latexpdf rediraffecheckdiff'
                        sh 'nox -s mypy'
                    }
                    archiveArtifacts artifacts: 'dist/*', allowEmptyArchive: true
                    archiveArtifacts artifacts: 'docs/_build/latex/*.pdf', allowEmptyArchive: true
                    stash includes: 'dist/**', name: 'dist'
                }
            }
        }
    }, "Test on hardware": {
        node('exploration_tool') {
            ws('workspace/exptool') {
                stage('Setup') {
                    printNodeInfo()
                    def scmVars = checkout scm
                    sh 'git clean -xdf'

                    findBuildAndCopyArtifacts(
                        projectName: 'sw-main',
                        revision: "master",
                        artifactNames: [
                            "out/internal_stash_python_libs.tgz",
                            "out/internal_stash_binaries_xm112.tgz",
                            "out/internal_stash_binaries_sanitizer_a111.tgz",
                            "out/internal_stash_binaries_sanitizer_a121.tgz"
                        ]
                    )
                    sh 'mkdir stash'
                    sh 'tar -xzf out/internal_stash_python_libs.tgz -C stash'
                    sh 'tar -xzf out/internal_stash_binaries_xm112.tgz -C stash'
                    sh 'tar -xzf out/internal_stash_binaries_sanitizer_a111.tgz -C stash'
                    sh 'tar -xzf out/internal_stash_binaries_sanitizer_a121.tgz -C stash'
                }
                stage ('Flash') {
                    sh '(cd stash && python3 python_libs/test_utils/flash.py)'
                }
                stage('Run integration tests') {
                    def image = buildDocker(path: 'docker')
                    image.inside("--hostname ${env.NODE_NAME}" +
                                " --net=host --privileged" +
                                " --mount type=volume,src=cachepip-${EXECUTOR_NUMBER},dst=/home/jenkins/.cache/pip") {
                        lock("${env.NODE_NAME}-xm112") {
                                sh 'tests/run-integration-tests.sh'
                        }
                    }
                }
            }
        }
    }, failFast: true

    if (env.TAG_NAME ==~ /v.*/) {
        node('docker') {
            ws('workspace/exptool') {
                def scmVars = checkout scm
                sh 'git clean -xdf'
                def image = buildDocker(path: 'docker')
                image.inside("--hostname ${env.NODE_NAME}" +
                            " --mount type=volume,src=cachepip-${EXECUTOR_NUMBER},dst=/home/jenkins/.cache/pip") {
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
            gerritReview labels: [Verified: 1], message: "Success: ${env.BUILD_URL}"
        } else {
            echo "Reporting Fail to Gerrit"
            gerritReview labels: [Verified: -1], message: "Failed: ${env.BUILD_URL}"
        }
    }
} catch (exception) {
    stage('Report result to gerrit') {
        echo "Reporting Fail to Gerrit"
        gerritReview labels: [Verified: -1], message: "Failed: ${env.BUILD_URL}"
    }
    throw exception
}
