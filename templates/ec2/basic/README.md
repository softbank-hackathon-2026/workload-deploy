# ec2/basic

퍼블릭 Space(VPC + 퍼블릭 서브넷)에 EC2 서버 1대를 만들고, 그 위에서 Docker로 앱 이미지를 실행합니다.
공인 IP의 80번 포트로 공개하고 로드밸런서는 쓰지 않습니다. 템플릿 이름은 폴더 경로 `ec2/basic`입니다.

`ecs-fargate/basic`과 같은 이미지(ECR, digest 고정)를 씁니다. 서버는 Amazon Linux 2023 최신 AMI로 뜨고, 시작할 때(user_data) Docker를 설치하고 이미지를 받아 실행합니다.

## 맞는 앱, 안 맞는 앱

| 맞음 | 안 맞음 |
|---|---|
| 서버 1대로 충분한 웹 앱, 오래 도는 작업 | 무중단 배포가 필요한 앱 |
| 서버를 직접 들여다봐야 하는 경우 (Session Manager로 접속) | 고정 주소가 필요한 앱 |

재배포하면 새 이미지로 서버를 **새로 만들어** 바꿉니다. 그래서 주소(공인 DNS)가 바뀌고, 새 서버가 뜨는 동안(1~2분) 앱이 멈춥니다.

## 만드는 자원

| 자원 | 이름 | 트리 분류(예시) |
|---|---|---|
| EC2 인스턴스 (공인 IP, IMDSv2) | `sbh-workload-demo-ec2-<application_id>` | 서버 |
| 보안 그룹 (HTTP 80) | `sbh-workload-demo-sg-ec2-<application_id>` | 연결 |
| 인스턴스 역할 (ECR 읽기, Session Manager) | `sbh-workload-demo-role-ec2-<application_id>` | 기타 |
| 인스턴스 프로필 | `sbh-workload-demo-profile-ec2-<application_id>` | 기타 |

SSH 키는 만들지 않습니다. 서버를 봐야 하면 AWS 콘솔의 Session Manager로 접속합니다.

## 입력 속성

### AI가 채울 값 (지금은 기본값으로 배포)

| 속성 | 타입 | 기본값 | 허용 범위 | 역할 |
|---|---|---|---|---|
| `container_port` | number | `80` | 1~65535 정수 | 앱이 컨테이너 안에서 듣는 포트. 서버 80번 포트로 연결하고 `PORT` 환경변수로도 넣는다. 구성안에 없으면 Dockerfile의 첫 `EXPOSE` 포트를 쓴다 |
| `instance_type` | string | `t3.micro` | `t3.micro`, `t3.small`, `t3.medium` | 서버 크기. 예산 때문에 작은 타입만 허용 |
| `health_check_path` | string | `/` | `/`로 시작, URL 경로 문자만 | 배포 뒤 워크플로가 확인하는 경로. 2xx·3xx면 정상 |

### 파이프라인이 넣는 값

| 속성 | 타입 | 기본값 | 역할 |
|---|---|---|---|
| `application_id` | string | 필수 | 앱 Space ID, 24자 이하 |
| `deployment_id` | string | 필수 | 배포 ID (인스턴스 태그) |
| `infra_id` | string | 필수 | 인프라 Space ID (태그) |
| `image` | string | 필수 | `<ECR 주소>/<저장소>@sha256:<digest>`. ECR 이미지만 허용 |
| `region` | string | `ap-northeast-2` | 리전 |

### 인프라 Space가 주는 값 (백엔드 `GET /api/plans/{plan_id}`의 `infra`)

| 속성 | 타입 | 기본값 | 역할 |
|---|---|---|---|
| `vpc_id` | string | 필수 | Space VPC |
| `public_subnet_ids` | list(string) | 필수 | 퍼블릭 서브넷. 첫 번째 서브넷에 서버를 둔다 |

## 출력 속성

| 속성 | 역할 |
|---|---|
| `app_url` | 앱 주소 (`http://<공인 DNS>`). 최종 콜백의 `url`로 보냄. 재배포하면 바뀜 |
| `instance_id` | 인스턴스 ID |
| `health_check_path` | 배포 뒤 워크플로가 확인하는 경로 |

## 검사

`terraform init -backend=false && terraform validate && terraform test` (mock provider, AWS 접속 없음). GitHub Actions `Validate` 워크플로가 같은 검사를 돌립니다.
