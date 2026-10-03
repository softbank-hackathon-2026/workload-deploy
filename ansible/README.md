# 온프레미스 VM 배포 (Ansible)

온프레미스(Proxmox) 서비스 VM에 앱을 Ansible로 설치합니다. AWS 배포(`templates/`, Terraform)와 같은 방식으로
**틀(플레이북)은 이 레포에 고정**하고, **AI는 값(values.yaml)만** 채웁니다.

- 배포 워크플로: `.github/workflows/deploy-vm.yml` (두 컴퓨팅 공통, `compute` 입력으로 고름)
- 내리기 워크플로: `.github/workflows/destroy-vm.yml` (두 컴퓨팅 공통)

| 컴퓨팅 ID | 방식 | 플레이북 | AI가 추천할 때 |
|---|---|---|---|
| `vm` | 코드를 VM에 올려 VM에서 빌드하고 systemd 서비스로 실행. Docker 안 씀 | `playbooks/deploy.yml` | Dockerfile이 없는 Python·Node·Java 앱 |
| `vm-container` | 레포의 Dockerfile로 VM에서 이미지를 빌드하고 Docker 컨테이너로 실행 | `playbooks/deploy-container.yml` | Dockerfile이 있는 앱 (언어 무관) |

## 흐름

```
백엔드 (compute = vm 또는 vm-container)
  → deploy-vm.yml 실행 (deploy.yml과 같은 입력)
  → prepare: 입력 검사, 진행 알림
  → build:   사용자 코드를 묶기만 함 (키 없음)
  → deploy:  구성안 가져오기 → values 검사 (scripts/vm_plan.py)
             → cloudflared로 VM SSH 접속 → Ansible Runner로 컴퓨팅에 맞는 플레이북 실행
             → 작업마다 진행 콜백 (type: ansible_task)
  → report:  결과 콜백 (url: http://<vm_host>:<포트>)
```

## 파일

| 파일 | 역할 |
|---|---|
| `playbooks/deploy.yml` | `vm`: 언어 설치 → 앱 사용자 만들기 → 코드 복사 → 빌드 → systemd 서비스 등록·시작 → 헬스체크 |
| `playbooks/deploy-container.yml` | `vm-container`: Docker 설치(없을 때만) → 코드 복사 → 이미지 빌드 → 이전 컨테이너 교체 → 헬스체크 |
| `playbooks/remove.yml` | 두 컴퓨팅 공통. 서비스·컨테이너·이미지·앱 파일 삭제. 언어, Tomcat, Docker는 다른 앱을 위해 남김 |
| `playbooks/templates/app.service.j2` | 앱 systemd 서비스 (포트, 환경변수, 시작 명령) |
| `../scripts/vm_plan.py` | values.yaml 검사, Ansible 변수와 대상 VM 목록 작성 |

## 입력 속성

### AI가 채울 값: `vm-container`

| 속성 | 타입 | 필수 | 기본값 | 허용 범위 | 역할 |
|---|---|---|---|---|---|
| `container_port` | number | | `8080` | 1~65535 정수 | 컨테이너 안에서 앱이 듣는 포트 (Dockerfile `EXPOSE`). 컨테이너에 `PORT` 환경변수로도 넣음 |
| `app_port` | number | | `container_port` (1024 미만이면 `8080`) | 1024~65535 정수 | VM에서 여는 포트. `app_port` → `container_port`로 연결 |
| `health_check_path` | string | | `/` | `vm`과 같음 | 배포 끝에 VM 안에서 `app_port`로 불러 2xx·3xx면 성공 |
| `env` | object | | `{}` | `vm`과 같음 | 컨테이너 환경변수. **비밀값은 넣지 않음** |

- Dockerfile은 레포 맨 위에 있어야 합니다. 빌드 명령과 시작 명령은 Dockerfile이 정하므로 `build_command`, `start_command`, `runtime`은 쓰지 않습니다.
- ECS 템플릿의 `container_port`, `health_check_path`와 같은 이름이라 AI가 같은 방식으로 채우면 됩니다.

### AI가 채울 값: `vm` (구성안 `values`)

`scripts/vm_plan.py`가 이 기준으로 검사하고, 틀리면 VM에 닿기 전에 배포를 멈춥니다.

| 속성 | 타입 | 필수 | 기본값 | 허용 범위 | 역할 |
|---|---|---|---|---|---|
| `runtime` | string | ✅ | 없음 | `python`, `node`, `java` | 앱 언어 |
| `runtime_version` | string | | `21` | `java`일 때만 `17`, `21` | Java 버전. Python과 Node는 VM 운영체제에 있는 버전을 씀 |
| `app_port` | number | | `8080` | 1024~65535 정수 | 앱이 듣는 포트. 서비스에 `PORT` 환경변수로도 넣음. 앱은 일반 사용자로 실행돼서 1024 미만은 못 씀 |
| `health_check_path` | string | | `/` | `/`로 시작, URL 경로 문자만 | 배포 끝에 VM 안에서 이 경로를 불러 2xx·3xx면 성공 |
| `build_command` | string | | 빈 값 | 한 줄, 500자 이하 | 앱 폴더에서 앱 사용자로 실행. 비우면 건너뜀 |
| `start_command` | string | ✅ (Tomcat 제외) | 빈 값 | 한 줄, 500자 이하 | 서비스 시작 명령 (`/bin/sh -c`로 실행) |
| `java_server` | string | | `none` | `none`, `tomcat` | WAR를 Tomcat에 올리면 `tomcat` |
| `tomcat_version` | string | | `10` | `10` | Tomcat 버전 (Ubuntu 24.04 패키지) |
| `war_file` | string | | `target/*.war` | 한 줄 | Tomcat에 올릴 WAR 경로 (앱 폴더 기준, 처음 맞는 파일) |
| `env` | object | | `{}` | 이름: 대문자·숫자·밑줄 / 값: 한 줄, 큰따옴표 불가 | 앱 환경변수. **비밀값은 넣지 않음** |

`application_id`, `deployment_id`, `infra_id`, `image`, `region`은 파이프라인 값이라 values에 있어도 무시합니다.

#### AI가 값을 채울 때 주의할 것

- **Python은 venv를 씁니다.** VM(Ubuntu 계열)은 시스템 전체 `pip install`을 막습니다.
  `build_command: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`,
  `start_command: .venv/bin/python app.py`처럼 채웁니다.
- **Node는 의존성이 있으면 설치 명령이 필요합니다.** `package.json`에 dependencies가 있으면
  `build_command: npm ci --omit=dev` (lock 파일이 없으면 `npm install --omit=dev`).
- **Java JAR**는 `build_command`로 빌드하고 `start_command: java -jar target/app.jar`처럼 실행합니다.
- **Java WAR**는 `java_server: tomcat`으로 두고 `start_command`는 비웁니다. 앱은 Tomcat의 8080 포트 `/`에 올라갑니다.
- 지원 범위 밖(다른 언어, 여러 프로세스가 필요한 앱 등)은 부적합으로 판단합니다.

### 인프라 Space가 주는 값 (구성안 `infra`)

| 속성 | 타입 | 필수 | 역할 |
|---|---|---|---|
| `vm_host` | string | ✅ | cloudflared로 들어갈 서비스 VM 호스트 이름 (지금은 `vpn.howon.me`) |

### 파이프라인이 넣는 값

`application_id`, `deployment_id`, `app_archive`(묶은 코드 경로). AI나 백엔드가 덮어쓸 수 없습니다.

## 예시 values.yaml

vm-container (Dockerfile이 있는 앱, 예: sample-shop `EXPOSE 3000`)
```yaml
container_port: 3000
health_check_path: /health
```

vm, Node.js (실제 VM에서 확인한 값, shop-api)
```yaml
runtime: node
app_port: 8080
health_check_path: /api/health
start_command: node server.js
```

Python
```yaml
runtime: python
app_port: 8080
health_check_path: /health
build_command: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
start_command: .venv/bin/python app.py
env:
  APP_ENV: demo
```

Java JAR
```yaml
runtime: java
runtime_version: "21"
build_command: ./mvnw -q package -DskipTests
start_command: java -jar target/app.jar
health_check_path: /actuator/health
```

Java WAR (Tomcat)
```yaml
runtime: java
runtime_version: "21"
java_server: tomcat
tomcat_version: "10"
build_command: ./mvnw -q package -DskipTests
health_check_path: /
```

## VM에 생기는 것

| 무엇 | 이름 |
|---|---|
| 앱 사용자 | `sbh-app` (로그인 불가 시스템 사용자) |
| 앱 폴더 | `/opt/sbh-apps/<application_id>` (재배포 때 지우고 새로 만듦) |
| 서비스 | `sbh-app-<application_id>` (systemd, 자동 재시작) |
| Tomcat 기록 | `/var/lib/sbh-apps/<application_id>.tomcat` (WAR일 때만, 내리기 때 사용) |
| 컨테이너 (`vm-container`) | 이름 `sbh-app-<application_id>`, 이미지 `sbh-app-<application_id>:latest`, 꺼지면 자동 재시작 |
| 컨테이너 환경변수 파일 | `/opt/sbh-apps/<application_id>.env` (root만 읽기) |

화면 자원 트리에는 Ansible 작업이 `type: ansible_task`, `address: <작업 이름>`으로 나옵니다 (예: `Install Node.js runtime`, `Start app service`).

## 접속과 시크릿

GitHub Actions가 Cloudflare Access(서비스 토큰)를 거쳐 VM에 SSH로 들어갑니다. VM은 인터넷에 열지 않습니다.

| 시크릿 | 내용 |
|---|---|
| `ONPREM_SSH_PRIVATE_KEY` | VM 접속 개인키 |
| `ONPREM_SSH_USER` | VM 접속 사용자 (비밀번호 없이 sudo 가능해야 함) |
| `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET` | Cloudflare Access 서비스 토큰 (cloudflared에 `TUNNEL_SERVICE_TOKEN_ID/SECRET`로 전달) |

## 워크플로 입력

- `deploy-vm.yml`: `deployment_id`, `application_id`, `repo`, `commit_sha`, `infra_id`, `compute`(`vm` 또는 `vm-container`, 비우면 `vm`), `plan_id`, `callback_url` (deploy.yml과 같음). 시험용 `test_plan`, `test_local`.
- `destroy-vm.yml`: `application_id`, `confirm`, `vm_host`, `callback_url`. 시험용 `test_local`.

## 검사와 시험 기록

- `Validate` 워크플로의 `vm-playbook` job이 Actions 러너를 VM 대신 써서 Python·Node(`vm`)와 Dockerfile 앱(`vm-container`)을 배포 → 응답 → 삭제까지 확인합니다.
- 2026-10-03 실제 VM(`vpn.howon.me`): shop-api(Node) 배포 2분 20초 성공, 내리기 53초 성공.
- Java JAR와 Tomcat WAR는 플레이북에 있지만 실제 VM 시험은 아직입니다.
