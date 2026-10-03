"""Check the on-prem plan values (values.yaml) and write the Ansible Runner inputs for one VM deploy.

The plan comes from the backend the same way as for AWS (plan.py load_plan: signed GET /api/plans/{plan_id},
or TEST_PLAN for a manual run). Its values are checked here, since build_command and start_command run on the VM.

Usage:
  vm_plan.py prepare <private_data_dir>  # deploy: writes env/extravars and inventory/hosts, prints step outputs
  vm_plan.py remove <private_data_dir>   # destroy: same files for an app ID and a VM host from the inputs
  vm_plan.py --self-test

Env: APPLICATION_ID, DEPLOYMENT_ID, APP_ARCHIVE (deploy), VM_HOST (remove), SSH_USER,
     VM_LOCAL=true to run on the Actions runner itself (test only, no VM).
"""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from plan import RESERVED, fail, load_plan  # noqa: E402

RUNTIMES = {"python", "node", "java"}
JAVA_VERSIONS = {"17", "21"}
TOMCAT_VERSIONS = {"10"}  # the version Ubuntu 24.04 ships as a package
DEFAULTS = {
    "runtime_version": "21",
    "app_port": 8080,
    "health_check_path": "/",
    "build_command": "",
    "start_command": "",
    "java_server": "none",
    "tomcat_version": "10",
    "war_file": "target/*.war",
    "env": {},
}
PATH_RE = re.compile(r"^/[A-Za-z0-9._~/-]{0,254}$")
ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]{0,63}$")
HOST_RE = re.compile(r"^[A-Za-z0-9.-]{1,253}$")
# Cloudflare Access in front of the VM's SSH (assumed until the on-prem owner confirms the connection method).
PROXY = "-o ProxyCommand='cloudflared access ssh --hostname %h' -o StrictHostKeyChecking=accept-new"


def one_line(name, value):
    if not isinstance(value, str) or "\n" in value or len(value) > 500:
        raise ValueError(f"{name}는 500자 이하 한 줄 문자열이어야 합니다.")
    return value


def check_values(raw):
    """values.yaml -> Ansible variables. Refuses anything the playbook cannot run safely."""
    v = {**DEFAULTS, **{k: x for k, x in (raw or {}).items() if k not in RESERVED}}
    if v.get("runtime") not in RUNTIMES:
        raise ValueError(f"runtime은 {', '.join(sorted(RUNTIMES))} 중 하나여야 합니다.")
    port = v["app_port"]
    if not (isinstance(port, int) and not isinstance(port, bool) and 1024 <= port <= 65535):
        raise ValueError("app_port는 1024~65535 정수여야 합니다(앱은 일반 사용자로 실행됩니다).")
    if not (isinstance(v["health_check_path"], str) and PATH_RE.match(v["health_check_path"])):
        raise ValueError("health_check_path는 /로 시작하는 URL 경로여야 합니다.")
    for name in ("build_command", "start_command", "war_file"):
        one_line(name, v[name])
    v["runtime_version"] = str(v["runtime_version"])
    v["tomcat_version"] = str(v["tomcat_version"])
    tomcat = v["runtime"] == "java" and v["java_server"] == "tomcat"
    if v["runtime"] == "java":
        if v["runtime_version"] not in JAVA_VERSIONS:
            raise ValueError(f"java runtime_version은 {', '.join(sorted(JAVA_VERSIONS))} 중 하나여야 합니다.")
        if v["java_server"] not in ("none", "tomcat"):
            raise ValueError("java_server는 none 또는 tomcat이어야 합니다.")
        if tomcat and v["tomcat_version"] not in TOMCAT_VERSIONS:
            raise ValueError(f"tomcat_version은 {', '.join(sorted(TOMCAT_VERSIONS))}만 됩니다.")
    if not tomcat and not v["start_command"]:
        raise ValueError("start_command가 필요합니다(Tomcat에 올리는 WAR만 생략할 수 있습니다).")
    env = v.pop("env")
    if not isinstance(env, dict) or not all(
        ENV_NAME_RE.match(str(k)) and isinstance(x, str) and "\n" not in x and '"' not in x for k, x in env.items()
    ):
        raise ValueError("env는 대문자 이름과 한 줄 문자열 값이어야 합니다(따옴표 불가).")
    v["app_env"] = env
    return v


def inventory(host, user, local):
    if local:
        target = {"ansible_connection": "local", "ansible_python_interpreter": "/usr/bin/python3"}
    else:
        if not (isinstance(host, str) and HOST_RE.match(host)):
            raise ValueError("대상 VM 주소(vm_host)가 없거나 형식이 틀렸습니다.")
        if not user:
            raise ValueError("VM 접속 사용자(ONPREM_SSH_USER)가 없습니다.")
        target = {"ansible_host": host, "ansible_user": user, "ansible_ssh_common_args": PROXY}
    return {"all": {"hosts": {"target": target}}}


def write(pdd, extravars, inv):
    for sub in ("env", "inventory"):
        Path(pdd, sub).mkdir(parents=True, exist_ok=True)
    Path(pdd, "env", "extravars").write_text(json.dumps(extravars), encoding="utf-8")
    Path(pdd, "inventory", "hosts").write_text(json.dumps(inv), encoding="utf-8")


def self_test():
    py = check_values({"runtime": "python", "start_command": "python3 app.py", "env": {"APP_ENV": "demo"},
                       "application_id": "evil"})
    assert (py["app_port"], py["app_env"], "application_id" in py) == (8080, {"APP_ENV": "demo"}, False), py
    war = check_values({"runtime": "java", "java_server": "tomcat", "runtime_version": 21})
    assert (war["runtime_version"], war["start_command"]) == ("21", ""), war
    bad = [
        {"runtime": "ruby", "start_command": "x"},
        {"runtime": "python"},                                           # no start command
        {"runtime": "python", "start_command": "x", "app_port": 80},     # privileged port
        {"runtime": "python", "start_command": "a\nb"},
        {"runtime": "python", "start_command": "x", "env": {"bad-name": "v"}},
        {"runtime": "python", "start_command": "x", "env": {"A": 'x" y'}},
        {"runtime": "java", "runtime_version": "11", "start_command": "x"},
        {"runtime": "python", "start_command": "x", "health_check_path": "health"},
    ]
    for values in bad:
        try:
            check_values(values)
        except ValueError:
            continue
        raise AssertionError(f"{values} must be rejected")
    assert inventory(None, None, True)["all"]["hosts"]["target"]["ansible_connection"] == "local"
    remote = inventory("app-vm.example.com", "deploy", False)["all"]["hosts"]["target"]
    assert (remote["ansible_host"], remote["ansible_user"]) == ("app-vm.example.com", "deploy")
    for host, user in (("bad host", "deploy"), (None, "deploy"), ("vm.example.com", "")):
        try:
            inventory(host, user, False)
        except ValueError:
            continue
        raise AssertionError(f"{host!r}/{user!r} must be rejected")
    print("self-test ok")


def main():
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    mode, pdd = sys.argv[1], sys.argv[2]
    local = os.environ.get("VM_LOCAL") == "true"
    user = os.environ.get("SSH_USER", "")
    app_id = os.environ["APPLICATION_ID"]
    try:
        if mode == "prepare":
            plan = load_plan()
            values = check_values(plan.get("values"))
            host = "127.0.0.1" if local else (plan.get("infra") or {}).get("vm_host")
            inv = inventory(host, user, local)
            extravars = {**values, "application_id": app_id, "deployment_id": os.environ["DEPLOYMENT_ID"],
                         "app_archive": os.environ["APP_ARCHIVE"]}
            port = 8080 if values["runtime"] == "java" and values["java_server"] == "tomcat" else values["app_port"]
            write(pdd, extravars, inv)
            print(f"app_url=http://{host}:{port}")
        elif mode == "remove":
            write(pdd, {"application_id": app_id}, inventory(os.environ.get("VM_HOST"), user, local))
        else:
            raise ValueError(f"unknown mode {mode}")
    except ValueError as e:
        fail(e)


if __name__ == "__main__":
    main()
