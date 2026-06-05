pipeline {
  agent any

  parameters {
    // latest 제거, 설명 업데이트
    string(name: 'IMAGE_TAG', defaultValue: '', description: '앱 레포 Git SHA 40자리 (예: a1b2c3d4...)')
    booleanParam(name: 'DEPLOY_BACKEND', defaultValue: false, description: 'backend까지 함께 재배포할지 여부')
  }

  environment {
    ECR_REGISTRY      = credentials('ECR_REGISTRY')
    SLACK_WEBHOOK_URL = credentials('SLACK_WEBHOOK_URL')
    IAM_ROLE_ARN      = credentials('IAM_ROLE_ARN')
    AWS_REGION        = 'ap-northeast-2'
    EKS_CLUSTER_NAME  = 'patrasche-news'
  }

  stages {

   
    stage('Gitleaks 보안 스캔') {
      steps {
        sh 'gitleaks detect --source . --exit-code 1'
      }
    }

    stage('Trivy 보안 스캔') {
      steps {
        sh '''
          mkdir -p /tmp/trivy-temp
          trivy fs . \
            --severity HIGH,CRITICAL \
            --exit-code 1 \
            --cache-dir /tmp/trivy-temp
        '''
      }
    }

    stage('린트 검사') {
      steps {
        sh '''
          set -e
          rm -rf .venv
          python3 -m venv .venv
          . .venv/bin/activate
          pip install --upgrade pip
          pip install flake8
          flake8 backend/mail-service \
            --max-line-length=130 \
            --exclude=backend/mail-service/alembic
          flake8 backend/news-fetcher-service \
            --max-line-length=130 \
            --exclude=backend/news-fetcher-service/alembic
          flake8 backend/news-summarizer-service \
            --max-line-length=130 \
            --exclude=backend/news-summarizer-service/alembic
          flake8 backend/user-service \
            --max-line-length=130 \
            --exclude=backend/user-service/alembic
          deactivate
          rm -rf .venv
        '''
      }
    }

    stage('테스트') {
      environment {
        DB_URL           = credentials('DB_URL')
        SMTP_HOST        = credentials('SMTP_HOST')
        SMTP_PORT        = credentials('SMTP_PORT')
        SMTP_USER        = credentials('SMTP_USER')
        SMTP_PASS        = credentials('SMTP_PASS')
        ENABLE_SCHEDULER = 'false'
      }
      steps {
        sh '''
          set -e
          rm -rf .venv
          python3 -m venv .venv
          . .venv/bin/activate
          which python
          which pip
          python -c "import sys; print(sys.executable)"
          pip install --upgrade pip setuptools wheel
          pip install pytest "anyio[trio]"
          pip install -r backend/mail-service/requirements.txt
          pip install --upgrade pyOpenSSL cryptography
          cd backend/mail-service && pytest tests/ -v && cd ../..
          pip install -r backend/news-fetcher-service/requirements.txt
          cd backend/news-fetcher-service && pytest tests/ -v && cd ../..
          pip install -r backend/news-summarizer-service/requirements.txt
          cd backend/news-summarizer-service && pytest tests/ -v && cd ../..
          pip install -r backend/user-service/requirements.txt
          cd backend/user-service && pytest tests/ -v && cd ../..
          deactivate
          rm -rf .venv
        '''
      }
    }

    stage('AWS Assume Role') {
      steps {
        script {
          assumeAwsRole('jenkins-app-deploy-session')
        }
      }
    }
 // IMAGE_TAG 검증 (40자리 Git SHA만 허용)
   stage('IMAGE_TAG 검증') {
    steps {
      script {
        if (!(params.IMAGE_TAG ==~ /^[0-9a-f]{40}$/)) {
          error('IMAGE_TAG는 40자리 앱 레포 Git SHA여야 합니다.')
        }
        echo "IMAGE_TAG 검증 완료: ${params.IMAGE_TAG}"

        // [수정] withCredentials 제거 → Assume Role 환경변수 그대로 사용
        sh """
          aws ecr describe-images \
            --repository-name patrasche-webserving \
            --image-ids imageTag=${params.IMAGE_TAG} \
            --region ${env.AWS_REGION} > /dev/null 2>&1 || \
            (echo "ERROR: webserving 이미지가 ECR에 없습니다. TAG: ${params.IMAGE_TAG}" && exit 1)
        """

        if (params.DEPLOY_BACKEND) {
          sh """
            for repo in patrasche-backend patrasche-crawler patrasche-analyzer patrasche-notifier; do
              aws ecr describe-images \
                --repository-name \$repo \
                --image-ids imageTag=${params.IMAGE_TAG} \
                --region ${env.AWS_REGION} > /dev/null 2>&1 || \
                (echo "ERROR: \$repo 이미지가 ECR에 없습니다. TAG: ${params.IMAGE_TAG}" && exit 1)
            done
          """
        }
      }
    }
  }
    stage('Ansible 배포') {
      steps {
        sh '''
          aws eks update-kubeconfig --name $EKS_CLUSTER_NAME --region $AWS_REGION

          ansible-playbook \
            -i ansible/inventory.ini \
            ansible/deploy.yml \
            --extra-vars "image_tag=$IMAGE_TAG ecr_registry=$ECR_REGISTRY deploy_backend=$DEPLOY_BACKEND"
        '''
      }
    }
  }

  post {
    success {
      sh '''
        curl -X POST "$SLACK_WEBHOOK_URL" \
        -H 'Content-type: application/json' \
        -d '{"text":"✅ *[patrasche-app]* 배포 완료!"}'
      '''
    }
    failure {
      sh '''
        curl -X POST "$SLACK_WEBHOOK_URL" \
        -H 'Content-type: application/json' \
        -d '{"text":"❌ *[patrasche-app]* 배포 실패!\n확인 필요"}'
      '''
    }
  }
}

def assumeAwsRole(String sessionName) {
  withCredentials([
    string(credentialsId: 'AWS_ACCESS_KEY_ID', variable: 'BASE_KEY'),
    string(credentialsId: 'AWS_SECRET_ACCESS_KEY', variable: 'BASE_SECRET')
  ]) {
    def credsStr = sh(script: """
      AWS_ACCESS_KEY_ID=\$BASE_KEY \
      AWS_SECRET_ACCESS_KEY=\$BASE_SECRET \
      AWS_SESSION_TOKEN="" \
      aws sts assume-role \
        --role-arn "${env.IAM_ROLE_ARN}" \
        --role-session-name "${sessionName}" \
        --query 'Credentials.[AccessKeyId,SecretAccessKey,SessionToken]' \
        --output text
    """, returnStdout: true).trim()

    def credsList = credsStr.tokenize()

    if (credsList.size() < 3) {
      error "AssumeRole failed: STS credentials were not returned"
    }

    env.AWS_ACCESS_KEY_ID     = credsList[0]
    env.AWS_SECRET_ACCESS_KEY = credsList[1]
    env.AWS_SESSION_TOKEN     = credsList[2]

    echo "AWS_ACCESS_KEY_ID exists? ${env.AWS_ACCESS_KEY_ID ? 'YES' : 'NO'}"
    echo "AWS_SESSION_TOKEN exists? ${env.AWS_SESSION_TOKEN ? 'YES' : 'NO'}"

    sh '''
      set -eu
      IDENTITY_ARN=$(aws sts get-caller-identity --query Arn --output text)
      echo "Current AWS Identity: $IDENTITY_ARN"
      case "$IDENTITY_ARN" in
        *":assumed-role/jenkins-onprem-deploy-role/"*)
          echo "OK: assumed deploy role"
          ;;
        *)
          echo "ERROR: not using deploy role. Current identity: $IDENTITY_ARN"
          exit 1
          ;;
      esac
    '''
  }
}