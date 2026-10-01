# workload-deploy

사용자 앱을 Workload 계정의 인프라 Space에 배포하는 워크플로입니다 (ADR-009).
플랫폼 백엔드가 `workflow_dispatch`로 실행하고, 단계마다 백엔드 콜백으로 진행 상황을 보냅니다.

## 흐름

| job | 하는 일 | 비밀값 |
|---|---|---|
| prepare | 입력값 검사, `prepare`(실행 ID)·`build` 콜백 | 서명 키 |
| build | 사용자 레포를 커밋 SHA로 받아 Docker 이미지 빌드 | 없음 (사용자 코드가 실행되는 곳) |
| deploy | 이미지를 Workload ECR에 올리고 템플릿으로 plan·apply, 자원별 콜백, 사이트 확인(`verify`) | 서명 키, Workload 키 |
| report | 최종 결과 콜백 (실패·취소 포함) | 서명 키 |

deploy job 순서: State 버킷·ECR 준비(처음 한 번 자동 생성) → 이미지 업로드(같은 앱·커밋이면 재사용) → 구성 값 준비(`scripts/plan.py`) → `terraform plan` → 자원 목록 콜백 → `terraform apply` → 서비스가 이번 revision으로 도는지 확인 → 앱 주소가 HTTP 200을 줄 때까지 확인.

| Workload 자원 | 이름 |
|---|---|
| State 버킷 | `sbh-workload-demo-s3-tfstate-921810471078`, 앱별 키 `apps/<application_id>/terraform.tfstate` |
| 이미지 저장소 | `sbh-workload-demo-ecr-apps`, 태그 `<application_id>-<commit_sha>` (덮어쓰기 금지) |

## 입력값

`deployment_id`, `application_id`(24자 이하), `repo`(owner/name, public), `commit_sha`(40자), `infra_id`, `compute`(지금은 `ecs-fargate`만), `plan_id`(백엔드 구성안), `test_plan`(시험용), `callback_url`(비우면 콜백 생략).

- `plan_id`가 있으면 백엔드 `GET /api/plans/{plan_id}`(plan_id 문자열을 서명)에서 템플릿 이름·값·인프라 값을 받습니다.
- 백엔드 연결 전 시험할 때는 `plan_id`를 비우고 `test_plan`에 백엔드 응답과 같은 모양을 넣습니다. 예: `{"values": {"container_port": 8000}, "infra": {"vpc_id": "...", "public_subnet_ids": ["...", "..."]}}`. 템플릿을 적지 않으면 `ecs-fargate/basic`입니다.

## 앱 삭제

Actions → **Destroy** → `application_id`를 두 번 입력. 그 앱의 Terraform State에 있는 자원을 모두 지웁니다(ALB 비용이 계속 나가므로 시험 후 실행). Deploy와 같은 그룹이라 배포 중에는 기다렸다가 실행됩니다.

## 콜백

`POST https://sbh.howon.me/api/deployments/{deployment_id}/callback`, 헤더 `X-Hub-Signature-256: sha256=<본문 HMAC-SHA256>`.
본문은 `status`, `step`, `message`와 `run_id`(첫 콜백), `url`(성공), `reason`(실패). 형식은 백엔드 API 명세 9-3, 9-4절을 따릅니다.

### 자원별 콜백 (트리용, 백엔드와 형식 협의 중)

deploy 단계에서 `status=deploying`, `step=deploy`와 함께 `resources` 배열을 보냅니다.

1. apply 전에 한 번: `terraform show -json`의 모든 자원 (`state`는 `pending`, 바뀌지 않는 자원은 `done`)
2. apply 중에 자원마다: 시작하면 `in_progress`, 끝나면 `done`, 실패하면 `failed` + `reason`

```json
{"status": "deploying", "step": "deploy", "message": "aws_lb.app 완료",
 "resources": [{"address": "aws_lb.app", "type": "aws_lb", "action": "create", "state": "done"}]}
```

`action`은 `create`, `update`, `replace`, `delete`, `no-op` 중 하나입니다. 화면은 `type`으로 서버·저장소·연결 같은 분류를 묶으면 됩니다.

## 시크릿

| 이름 | 용도 | 상태 |
|---|---|---|
| `DEPLOY_CALLBACK_SECRET` | 콜백 서명 키. 플랫폼 Parameter Store `/sbh/platform/demo/backend/DEPLOY_CALLBACK_SECRET`와 같은 값 | 미등록 (없으면 콜백 생략) |
| `WORKLOAD_AWS_ACCESS_KEY_ID`, `WORKLOAD_AWS_SECRET_ACCESS_KEY` | Workload 계정 키(정호원님 발급). deploy·destroy에서만 사용, 계정 `921810471078`이 아니면 멈춤 | 미등록 |

## 진행 상황

- [x] 1단계: 입력값, build job, 콜백
- [x] 2단계: `templates/ecs-fargate/basic/` Terraform 양식
- [x] 자원별 콜백 (deploy job에 연결)
- [ ] 3단계: Workload 연결 (코드 작성 완료, Workload 키 등록 후 첫 실행)
- [ ] 4단계: 백엔드 연결
- [ ] 5단계: 검증

스크립트 확인: `python scripts/callback.py --self-test`, `python scripts/plan.py --self-test`
