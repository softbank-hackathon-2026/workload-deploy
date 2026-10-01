# workload-deploy

사용자 앱을 Workload 계정의 인프라 Space에 배포하는 워크플로입니다 (ADR-009).
플랫폼 백엔드가 `workflow_dispatch`로 실행하고, 단계마다 백엔드 콜백으로 진행 상황을 보냅니다.

## 흐름

| job | 하는 일 | 비밀값 |
|---|---|---|
| prepare | 입력값 검사, `prepare`(실행 ID)·`build` 콜백 | 서명 키 |
| build | 사용자 레포를 커밋 SHA로 받아 Docker 이미지 빌드 | 없음 (사용자 코드가 실행되는 곳) |
| deploy | Workload에 배포, `deploy`·`verify` 콜백 | 서명 키, Workload 키 (3단계) |
| report | 최종 결과 콜백 (실패·취소 포함) | 서명 키 |

## 입력값

`deployment_id`, `application_id`, `repo`(owner/name, public), `commit_sha`(40자), `infra_id`, `compute`(지금은 `ecs-fargate`만), `callback_url`(비우면 콜백 생략).

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
| Workload 액세스 키 | deploy job에서만 사용 | 3단계 |

## 진행 상황

- [x] 1단계: 입력값, build job, 콜백
- [ ] 2단계: `templates/ecs-fargate/basic/` Terraform 양식
- [ ] 3단계: Workload 연결 (ECR 업로드, plan/apply, 동작 확인)
- [ ] 4단계: 백엔드 연결
- [ ] 5단계: 검증

콜백 스크립트 확인: `python scripts/callback.py --self-test`
