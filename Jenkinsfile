node {
    checkout scm 
}

pipeline {
    agent any

    stages {
        stage('Build') {
            steps {
                sh "make build-test"
            }
        }
        stage('Test') {
            steps {
                sh "make test"
            }
        }
    }
}
