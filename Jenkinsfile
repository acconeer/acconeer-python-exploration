gerritReview labels: [Verified: 0], message: "Test started: ${env.BUILD_URL}"
@Library('sw-jenkins-library@b303b82fe823acd2ef8d0f77498e87a4773aa8ea') _

pipeline {
    agent {
        label 'exploration_tool'
    }

    stages {
        stage('Setup') {
            steps {
                sh 'git clean -xdf'
                findBuildAndCopyArtifacts(
                    projectName: 'sw-main',
                    revision: "master",
                    artifactNames: [
                        "internal_stash_python_libs.tgz",
                        "internal_stash_binaries_xm112.tgz",
                        "internal_stash_binaries_sanitizer_a111.tgz"
                    ]
                )
                sh 'mkdir stash'
                sh 'tar -xzf internal_stash_python_libs.tgz -C stash'
                sh 'tar -xzf internal_stash_binaries_xm112.tgz -C stash'
                sh 'tar -xzf internal_stash_binaries_sanitizer_a111.tgz -C stash'
            }
        }
        stage('Offline tests') {
            agent {
                dockerfile {
                    reuseNode true
                    args '--mount type=volume,src=cachepip-${EXECUTOR_NUMBER},dst=/home/jenkins/.cache/pip'
                }
            }
            steps {
                sh 'tox'
            }
        }
        stage('Integration tests') {
            options {
                lock resource: '${env.NODE_NAME}-xm112'
            }
            stages {
                stage('Flash XM112') {
                    steps {
                        sh '(cd stash && python3 python_libs/test_utils/flash.py)'
                    }
                }
                stage('Run integration tests') {
                    agent {
                        dockerfile {
                            reuseNode true
                            args '--net=host --privileged --mount type=volume,src=cachepip-${EXECUTOR_NUMBER},dst=/home/jenkins/.cache/pip'
                        }
                    }
                    options {
                        lock resource: '${env.NODE_NAME}-localhost'
                    }
                    steps {
                        sh 'python3 -m pip install -q -U --user ".[test]"'
                        sh 'tests/run-integration-tests.sh'
                    }
                }
            }
        }
        stage('GUI tests') {
            agent {
                dockerfile {
                    reuseNode true
                    args '--mount type=volume,src=cachepip-${EXECUTOR_NUMBER},dst=/home/jenkins/.cache/pip'
                }
            }
            steps {
                sh 'python3 -m pip install -U --user ".[test,app]"'
                sh 'python3 -m pytest -v --timeout=60 --timeout_method=thread tests/gui'
            }
        }
    }

    post {
        success { gerritReview labels: [Verified: 1], message: "Success: ${env.BUILD_URL}" }
        failure { gerritReview labels: [Verified: -1], message: "Failed: ${env.BUILD_URL}" }
        aborted { gerritReview labels: [Verified: -1], message: "Aborted: ${env.BUILD_URL}" }
    }
}
