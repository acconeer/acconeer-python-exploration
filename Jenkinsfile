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
                sh 'pytest'
            }
        }
    }

    post {
        success { gerritReview labels: [Verified: 1], message: "Success: ${env.BUILD_URL}" }
        failure { gerritReview labels: [Verified: -1], message: "Failed: ${env.BUILD_URL}" }
    }
}
