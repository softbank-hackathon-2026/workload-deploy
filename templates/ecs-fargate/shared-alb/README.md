# ecs-fargate/shared-alb

Multi-AZ Space의 **공용 ALB**(`demo.howon.me`) 뒤에 앱 하나를 Fargate로 붙입니다. ALB, HTTPS 리스너, 인증서는 Space에 이미 있어서
앱마다 로드밸런서를 만들지 않습니다. 그래서 `ecs-fargate/basic`보다 배포가 빠릅니다.
템플릿 이름은 폴더 경로 `ecs-fargate/shared-alb`이고, compute는 `ecs-fargate` 그대로입니다.

```
손님 → https://demo.howon.me (공용 ALB, 443)
        ├─ /api/*  (규칙 번호 작게) → shop-api
        └─ /*      (규칙 번호 크게) → sample-shop
```

## 기존 basic과 다른 점

| | `ecs-fargate/basic` | `ecs-fargate/shared-alb` |
|---|---|---|
| 앱 위치 | 퍼블릭 서브넷, 공인 IP | **프라이빗(app) 서브넷, 공인 IP 없음** |
| 입구 | 앱마다 ALB를 새로 만듦 | **Space의 공용 ALB에 경로 규칙만 추가** |
| 주소 | `http://<앱 ALB 주소>` | `https://demo.howon.me` (경로로 나눔) |
| 이미지 받기 | 공인 IP로 | **Space의 NAT로** (NAT가 켜져 있어야 함) |

## 만드는 자원 (9개)

| 자원 | 이름 | 트리 분류(예시) |
|---|---|---|
| ECS 클러스터 | `sbh-workload-demo-ecs-<application_id>` | 서버 |
| ECS 서비스 (Task 2개, 가용 영역마다 1개, 공인 IP 없음) | `sbh-workload-demo-svc-<application_id>` | 서버 |
| Task Definition | `sbh-workload-demo-task-<application_id>` | 서버 |
| 실행 역할, 정책 연결 | `sbh-workload-demo-role-exec-<application_id>` | 기타 |
| 로그 그룹 (7일) | `/ecs/sbh-workload-demo-<application_id>` | 기타 |
| Target Group | `sbh-<application_id>-tg` | 연결 |
| 리스너 규칙 (경로) | 공용 리스너에 추가 | 연결 |
| 보안 그룹 (ALB에서만 허용) | `sbh-workload-demo-sg-task-<application_id>` | 연결 |

내리면 이 9개만 지워지고 공용 ALB, 리스너, 인증서는 남습니다.

## 입력 속성

### AI가 채울 값 (`ecs-fargate/basic`과 같음)

`container_port`, `cpu`, `memory`, `health_check_path`. 범위는 basic README와 같습니다.
단, **`health_check_path`는 `path_pattern` 아래 경로여야** 합니다. 배포 뒤 워크플로가 `https://demo.howon.me<health_check_path>`로
확인하는데, 다른 경로면 그 요청이 다른 앱으로 가기 때문입니다. 예: `/api/*`면 `/api/health`.

### 백엔드가 정할 값 (AI가 아님, 구성안 `values`에 넣음)

| 속성 | 타입 | 기본값 | 역할 |
|---|---|---|---|
| `path_pattern` | string | `/*` | 공용 주소에서 이 앱이 맡는 경로. `/`로 시작하고 `*`로 끝날 수 있음. 예: `/api/*`, `/*` |
| `rule_priority` | number | 필수 | 리스너 규칙 번호(1~50000). ALB는 **작은 번호부터** 확인하므로 좁은 경로(`/api/*`)가 넓은 경로(`/*`)보다 작아야 함. 같은 리스너에서 앱끼리 겹치면 안 됨 |

### 템플릿이 정하는 값 (Space 성격, AI가 아님)

| 속성 | 타입 | 기본값 | 역할 |
|---|---|---|---|
| `desired_count` | number | `2` | Task 수(1~4). Multi-AZ Space는 고가용성용이라 기본 2개로 app 서브넷 2a·2c에 하나씩 띄웁니다. 한쪽 가용 영역에 장애가 나도 다른 쪽이 계속 응답합니다 |

### 인프라 Space가 주는 값 (구성안 `infra`)

| 속성 | 타입 | 역할 |
|---|---|---|
| `vpc_id` | string | Space VPC |
| `private_subnet_ids` | list(string) | app 서브넷 2개 이상 (2a, 2c) |
| `alb_listener_arn` | string | 공용 ALB의 **443 리스너** ARN |
| `alb_security_group_id` | string | 공용 ALB 보안 그룹. Task는 이 보안 그룹에서 오는 요청만 받음 |
| `alb_base_url` | string | 공용 주소, 끝 `/` 없이. 예: `https://demo.howon.me` |

### 파이프라인이 넣는 값

`application_id`(24자 이하), `deployment_id`, `infra_id`, `image`, `region`. basic과 같습니다.

## 출력 속성

`app_url`(= `alb_base_url`), `cluster_name`, `service_name`, `health_check_path`, `task_definition_arn`. basic과 이름이 같아서 워크플로를 고치지 않습니다.

## 전제 조건

- Space에 NAT가 켜져 있어야 Task가 이미지를 받습니다. 없으면 Task가 뜨지 못하고 10분 뒤 배포가 실패합니다.
- 공용 ALB 보안 그룹이 VPC 안으로 나가는 것을 허용해야 합니다(지금 `10.11.0.0/16` 허용, 2026-10-03 확인).

## 검사

`terraform init -backend=false && terraform validate && terraform test` (mock provider, AWS 접속 없음). GitHub Actions `Validate` 워크플로가 같은 검사를 돌립니다.
