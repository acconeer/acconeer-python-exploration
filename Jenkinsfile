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
                sh 'python3 -m pip install -U --user .'
                sh 'pytest -v tests/unit'
                sh 'pytest -v tests/integration --mock'
                // sh 'pytest -v --timeout=60 --timeout_method=thread tests/gui'
                // sh 'sphinx-build -QW -b html docs docs/_build'
            }
        }
    }

    post {
        success { gerritReview labels: [Verified: 1], message: "Success: ${env.BUILD_URL}" }
        failure { gerritReview labels: [Verified: -1], message: "Failed: ${env.BUILD_URL}" }
        aborted { gerritReview labels: [Verified: -1], message: "Aborted: ${env.BUILD_URL}" }
    }
}
