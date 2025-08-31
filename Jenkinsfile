pipeline {
    agent any

    environment {
        PIP_CACHE_DIR = "${WORKSPACE}/.cache/pip"
        VENV_DIR = "${WORKSPACE}/venv"
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Set up Python') {
            steps {
                sh '''
                  python3 -m venv $VENV_DIR
                  . $VENV_DIR/bin/activate
                  pip install --upgrade pip
                '''
            }
        }

        stage('Install dependencies') {
            steps {
                sh '''
                  . $VENV_DIR/bin/activate
                  pip install -r requirements-dev.txt
                '''
            }
        }

        stage('Run Tests') {
            steps {
                sh '''
                  . $VENV_DIR/bin/activate
                  pytest -v
                '''
            }
        }

        stage('Build Package') {
            steps {
                sh '''
                  . $VENV_DIR/bin/activate
                  pip install build
                  python -m build
                '''
            }
            post {
                success {
                    archiveArtifacts artifacts: 'dist/*', fingerprint: true
                }
            }
        }

        stage('Publish to PyPI') {
            when {
                expression {
                    return env.GIT_TAG_NAME != null && env.GIT_TAG_NAME != ""
                }
            }
            steps {
                withCredentials([string(credentialsId: 'pypi-api-token', variable: 'PYPI_API_TOKEN')]) {
                    sh '''
                      . $VENV_DIR/bin/activate
                      pip install twine
                      twine upload dist/* -u __token__ -p $PYPI_API_TOKEN
                    '''
                }
            }
        }
    }

    post {
        always {
            junit 'pytest-report.xml'
        }
    }
}