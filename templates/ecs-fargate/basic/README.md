# ecs-fargate/basic

퍼블릭 Space(VPC + 퍼블릭 서브넷)에 앱 하나를 Fargate로 올리고, 앱 전용 ALB로 공개합니다.
템플릿 이름은 폴더 경로 `ecs-fargate/basic`입니다.

## 만드는 자원

| 자원 | 이름 | 트리 분류(예시) |
|---|---|---|
| ECS 클러스터 | `sbh-workload-demo-ecs-<application_id>` | 서버 |
| ECS 서비스 (Task 1개, 공인 IP) | `sbh-workload-demo-svc-<application_id>` | 서버 |
| Task Definition | `sbh-workload-demo-task-<application_id>` | 서버 |
| 실행 역할 | `sbh-workload-demo-role-exec-<application_id>` | 서버 |
| 로그 그룹 (7일) | `/ecs/sbh-workload-demo-<application_id>` | 서버 |
| ALB (HTTP 80) | `sbh-<application_id>-alb` | 연결 |
| Target Group | `sbh-<application_id>-tg` | 연결 |
| 보안 그룹 2개 (ALB, Task) | `sbh-workload-demo-sg-{alb,task}-<application_id>` | 연결 |

ALB와 Target Group은 이름이 32자로 제한돼서 짧은 형식을 씁니다. 그래서 `application_id`는 24자 이하여야 합니다.

## 입력 속성

### AI가 채울 값 (지금은 기본값으로 배포)

| 속성 | 타입 | 기본값 | 허용 범위 | 역할 |
|---|---|---|---|---|
| `container_port` | number | `80` | 1~65535 정수 | 앱이 컨테이너 안에서 듣는 포트. 컨테이너에 `PORT` 환경변수로도 넣어서, `PORT`를 읽는 앱은 이 포트로 뜬다. 구성안에 없으면 Dockerfile의 첫 `EXPOSE` 포트를 쓴다 |
| `cpu` | number | `256` | 256, 512, 1024 | Fargate CPU |
| `memory` | number | `512` | cpu 256: 512·1024·2048 / 512: 1024~4096 / 1024: 2048~8192 (1024 단위) | Fargate 메모리(MiB) |
| `health_check_path` | string | `/` | `/`로 시작, URL 경로 문자만 | ALB가 확인하는 경로. 2xx·3xx면 정상 |

### 파이프라인이 넣는 값

| 속성 | 타입 | 기본값 | 역할 |
|---|---|---|---|
| `application_id` | string | 필수 | 앱 Space ID, 24자 이하 |
| `deployment_id` | string | 필수 | 배포 ID (Task Definition·서비스 태그) |
| `infra_id` | string | 필수 | 인프라 Space ID (태그) |
| `image` | string | 필수 | `<저장소>@sha256:<digest>` |
| `region` | string | `ap-northeast-2` | 리전 |

### 인프라 Space가 주는 값 (백엔드 `GET /api/plans/{plan_id}`의 `infra`)

| 속성 | 타입 | 기본값 | 역할 |
|---|---|---|---|
| `vpc_id` | string | 필수 | Space VPC |
| `public_subnet_ids` | list(string) | 필수 | 퍼블릭 서브넷 2개 이상 (2a, 2c) |

## 출력 속성

| 속성 | 역할 |
|---|---|
| `app_url` | 앱 주소 (`http://<ALB 주소>`). 최종 콜백의 `url`로 보냄 |
| `cluster_name` | ECS 클러스터 이름 |
| `service_name` | ECS 서비스 이름 |
| `health_check_path` | 배포 뒤 워크플로가 확인하는 경로 (Target Group 헬스체크와 같음) |
| `task_definition_arn` | 이번 배포로 등록한 revision. 서비스가 이 revision으로 돌고 있는지(자동 롤백되지 않았는지) 확인할 때 씀 |

## 검사

`terraform init -backend=false && terraform validate && terraform test` (mock provider, AWS 접속 없음). GitHub Actions `Validate` 워크플로가 같은 검사를 돌립니다.
