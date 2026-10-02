# lambda/basic

웹 앱 하나를 Lambda 컨테이너 이미지로 올리고, 함수 URL(https)로 공개합니다. VPC와 로드밸런서는 쓰지 않습니다.
템플릿 이름은 폴더 경로 `lambda/basic`입니다.

파이프라인이 빌드할 때 사용자 이미지에 [AWS Lambda Web Adapter](https://github.com/awslabs/aws-lambda-web-adapter)를 넣습니다.
그래서 `ecs-fargate/basic`과 같은 Dockerfile(일반 HTTP 서버)이 코드 수정 없이 Lambda에서 돕니다.
어댑터가 앱을 띄우고 `health_check_path`가 응답할 때까지 기다린 뒤, 요청마다 Lambda 이벤트를 HTTP 요청으로 바꿔 앱에 넘깁니다.

## 맞는 앱, 안 맞는 앱

| 맞음 | 안 맞음 |
|---|---|
| 요청이 띄엄띄엄 오는 API, 작은 웹 서비스 | 요청 하나가 15분(900초)을 넘는 작업 |
| 상태를 메모리에 두지 않는 앱 | WebSocket, 메모리에 세션을 두는 앱 |
| | 1024 미만 포트(80 등)로 뜨는 앱. Lambda는 root가 아니라 낮은 포트를 못 엽니다 |

첫 요청은 앱 시작 시간(콜드 스타트)만큼 늦습니다.

## 만드는 자원

| 자원 | 이름 | 트리 분류(예시) |
|---|---|---|
| Lambda 함수 (이미지) | `sbh-workload-demo-fn-<application_id>` | 서버 |
| 함수 URL (인증 없음) | 함수에 붙음 | 서버 |
| 실행 역할 | `sbh-workload-demo-role-fn-<application_id>` | 기타 |
| 로그 그룹 (7일) | `/aws/lambda/sbh-workload-demo-fn-<application_id>` | 기타 |
| 공개 호출 권한 2개 | 함수에 붙음 | 서버 |

## 입력 속성

### AI가 채울 값 (지금은 기본값으로 배포)

| 속성 | 타입 | 기본값 | 허용 범위 | 역할 |
|---|---|---|---|---|
| `container_port` | number | `8080` | 1~65535 정수 (실제로는 1024 이상) | 앱이 듣는 포트. 어댑터가 이 포트로 요청을 넘기고, `PORT` 환경변수로도 넣는다. 구성안에 없으면 Dockerfile의 첫 `EXPOSE` 포트를 쓴다 |
| `memory` | number | `512` | 128~10240 정수 | 메모리(MiB). CPU도 메모리에 비례해 커진다 |
| `timeout` | number | `30` | 1~900 정수 | 요청 하나의 최대 시간(초) |
| `health_check_path` | string | `/` | `/`로 시작, URL 경로 문자만 | 어댑터가 첫 요청 전에 확인하는 경로. 배포 뒤 워크플로도 이 경로를 확인한다. 2xx·3xx면 정상 |

### 파이프라인이 넣는 값

| 속성 | 타입 | 기본값 | 역할 |
|---|---|---|---|
| `application_id` | string | 필수 | 앱 Space ID, 24자 이하 |
| `deployment_id` | string | 필수 | 배포 ID (함수 태그) |
| `infra_id` | string | 필수 | 인프라 Space ID (태그) |
| `image` | string | 필수 | `<저장소>@sha256:<digest>`, 어댑터가 들어간 이미지 (태그 `<app>-<sha>-lambda`) |
| `region` | string | `ap-northeast-2` | 리전 |

인프라 Space 값(VPC, 서브넷)은 받지 않습니다. 구성안에 있어도 파이프라인이 빼고 넘깁니다.

## 출력 속성

| 속성 | 역할 |
|---|---|
| `app_url` | 앱 주소 (함수 URL, 끝 `/` 없음). 최종 콜백의 `url`로 보냄 |
| `function_name` | 함수 이름 |
| `health_check_path` | 배포 뒤 워크플로가 확인하는 경로 |

## 검사

`terraform init -backend=false && terraform validate && terraform test` (mock provider, AWS 접속 없음). GitHub Actions `Validate` 워크플로가 같은 검사를 돌립니다.
