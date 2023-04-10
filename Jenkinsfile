node {
    checkout scm 
    /* .. snip .. */
}

pipeline {
    agent any

    stages {
        stage('Build') {
            steps {
                sh "cd docker/development; docker compose build"

            }
        }
    }
}
