pipeline {
    agent {
        dockerfile true
    }

    stages {
        stage('Test') {
            steps {
                sh 'flake8'
            }
        }
    }

    post {
        success { gerritReview labels: [Verified: 1], message: "Success: ${env.BUILD_URL}" }
        failure { gerritReview labels: [Verified: -1], message: "Failed: ${env.BUILD_URL}" }
    }
}
