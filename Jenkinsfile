pipeline {
  agent any

  parameters {
    string(name: 'IMAGE_TAG', defaultValue: 'latest', description: '이미 ECR에 올라간 앱 이미지 태그')
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

    //코드에 비밀번호/API키 등 민감정보 노출 여부 검사
    stage('Gitleaks 보안 스캔') {
      steps {
        sh 'gitleaks detect --source . --exit-code 1'
      }
    }
    //코드/패키지의 HIGH, CRITICAL 보안 취약점 검사
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
    //백엔드 Python 코드 스타일/품질 검사
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
        '''
      }
    }
    //백엔드 서비스별 단위 테스트 실행(mail, fetcher, summarizer, user 서비스)
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
          cd backend/mail-service
          pytest tests/ -v
          cd ../..

          pip install -r backend/news-fetcher-service/requirements.txt
          cd backend/news-fetcher-service
          pytest tests/ -v
          cd ../..

          pip install -r backend/news-summarizer-service/requirements.txt
          cd backend/news-summarizer-service
          pytest tests/ -v
          cd ../..

          pip install -r backend/user-service/requirements.txt
          cd backend/user-service
          pytest tests/ -v
          cd ../..
        '''
      }
    }

    // 도커 빌드 & ECR 푸시는 인프라 레포 Jenkinsfile에서 전담합니다.
    // 이 파이프라인은 이미 ECR에 올라간 IMAGE_TAG를 EKS에 재배포합니다.

    // ──────────────────────────────────────────────────────────
    // Ansible 배포 전 Assume Role 
    // ──────────────────────────────────────────────────────────
    
    //Jenkins IAM User → deploy role 임시 자격증명 발급
    //kubectl 실행에 필요한 AWS 권한 획득
    stage('AWS Assume Role') {
      steps {
        script {
          assumeAwsRole('jenkins-app-deploy-session')
        }
      }
    }
    // EKS kubeconfig 업데이트
    // ECR에 올라간 이미지를 EKS에 재배포
    // DEPLOY_BACKEND=false → 프론트만 재배포
    // DEPLOY_BACKEND=true  → 프론트 + 백엔드 재배포
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

// ──────────────────────────────────────────────────────────
// 공통 함수: AWS Assume Role
// ──────────────────────────────────────────────────────────
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
