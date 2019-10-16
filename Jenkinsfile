gerritReview labels: [Verified: 0], message: "Test started: ${env.BUILD_URL}"

pipeline {
    agent {
        dockerfile {
            label 'ai-31'
            args '--net=host'
        }
    }

    stages {
        stage('Test') {
            steps {
                sh 'flake8'
                sh 'python3 setup.py -q install --user'
                timeout(time: 2, unit: 'MINUTES') {
                    sh 'pytest'
                }
                sh 'sphinx-build -QW -b html docs docs/_build'
            }
        }
    }

    post {
        success { gerritReview labels: [Verified: 1], message: "Success: ${env.BUILD_URL}" }
        failure { gerritReview labels: [Verified: -1], message: "Failed: ${env.BUILD_URL}" }
        aborted { gerritReview labels: [Verified: -1], message: "Aborted: ${env.BUILD_URL}" }
    }
}
