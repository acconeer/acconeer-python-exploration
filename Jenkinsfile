import groovy.transform.Field
@Library('sw-jenkins-library@f8abd2e69ceef2d37e8ab7f1fbc294e34ac04670') _


String dockerArgs(env_map) {
  return "--hostname ${env_map.NODE_NAME}" +
         " --mount type=volume,src=cachepip-${env_map.EXECUTOR_NUMBER},dst=/home/jenkins/.cache/pip"
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
                    checkoutAndCleanup(lfs: false)

                    buildDocker(path: 'docker').inside(dockerArgs(env)) {
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
    }, "Mock test": {
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
                stage('Run integration tests') {
                    buildDocker(path: 'docker').inside(dockerArgs(env)) {
                        sh 'tests/run-a111-mock-integration-tests.sh'
                        sh 'tests/run-a121-mock-integration-tests.sh'
                    }
                }
            }
        }
    }, "XM112 test": {
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
                            sh 'tests/run-a111-xm112-integration-tests.sh'
                        }
                    }
                }
            }
        }
    }, failFast: true

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
