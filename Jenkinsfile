gerritReview labels: [Verified: 0], message: "Test started: ${env.BUILD_URL}"
@Library('sw-jenkins-library@4cab7c41c21e8a30612b3bf50a8db50fa7f56a4d') _

pipeline {
    agent none

    stages {
        stage('Offline tests') {
            agent {
                dockerfile {
                    label 'exploration_tool'
                }
            }
            steps {
                sh 'python3 internal/check_permissions.py'
                sh 'python3 internal/check_whitespace.py'
                sh 'flake8'
                sh 'isort --check-only -vb'
                sh 'python3 -m pip install -U --user .'
                sh 'pytest -v tests/unit'
                sh 'sphinx-build -QW -b html docs docs/_build'
            }
        }
        stage('XM112 integration tests') {
            options {
                lock resource: '${env.NODE_NAME}-xm112'
            }
            stages {
                stage('Flash') {
                    agent {
                        label 'exploration_tool'
                    }
                    steps {
                        findBuildAndCopyArtifacts(projectName: 'sw-main', revision: "master", artifactName: "internal_stash_scripts_embedded.zip")
                        findBuildAndCopyArtifacts(projectName: 'sw-main', revision: "master", artifactName: "internal_stash_xm112.zip")
                        sh 'rm -rf stash'
                        sh 'unzip -q internal_stash_scripts_embedded.zip -d stash'
                        sh 'unzip -q internal_stash_xm112.zip -d stash'
                        sh '(cd stash && PYTHONPATH=$PYTHONPATH:./scripts/integrator/embedded/ python3 scripts/integrator/module_server/flash.py)'
                    }
                }
                stage('Integration tests') {
                    agent {
                        dockerfile {
                            label 'exploration_tool'
                            args '--net=host --privileged'
                        }
                    }
                    steps {
                        sh 'python3 -m pip install -q -U --user .'
                        sh 'pytest -v tests/integration --mock --uart --spi'
                    }
                }
            }
        }
        stage('GUI tests') {
            agent {
                dockerfile {
                    label 'exploration_tool'
                }
            }
            steps {
                sh 'python3 -m pip install -U --user .'
                sh 'pytest -v --timeout=60 --timeout_method=thread tests/gui'
            }
        }
    }

    post {
        success { gerritReview labels: [Verified: 1], message: "Success: ${env.BUILD_URL}" }
        failure { gerritReview labels: [Verified: -1], message: "Failed: ${env.BUILD_URL}" }
        aborted { gerritReview labels: [Verified: -1], message: "Aborted: ${env.BUILD_URL}" }
    }
}
