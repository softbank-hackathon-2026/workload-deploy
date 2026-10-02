"""Send a deployment status callback to the platform backend (ADR-009, API spec 9-4).

The JSON body is signed with HMAC-SHA256 in X-Hub-Signature-256, the same scheme as GitHub webhooks.
Skips when CALLBACK_URL or DEPLOY_CALLBACK_SECRET is empty, so the workflow runs before the backend
endpoint exists. A failed callback never fails the deployment: the backend falls back to polling Actions.

Usage:
  callback.py <step> <message> [--run-id ID] [--url URL] [--reason TEXT]
  callback.py final                 # reads job results from env, sends success or failed
  callback.py teardown              # destroy result to /app-spaces/{id}/teardown/callback (JOB_STATUS from env)
  callback.py teardown              # destroy result to /app-spaces/{id}/teardown/callback (JOB_STATUS from env)
  terraform show -json tfplan | callback.py plan-resources      # every resource in the plan, for the tree
  terraform apply -json tfplan | callback.py apply-events       # per-resource start / done / failed
  callback.py --self-test
"""
import argparse
import hashlib
import hmac
import http.client
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

STATUS_BY_STEP = {"prepare": "pending", "build": "building", "deploy": "deploying", "verify": "deploying", "done": "success"}
JOBS = ("prepare", "build", "deploy")
DEFAULT_REASONS = {
    "prepare": "배포 요청 값이 올바르지 않습니다.",
    "build": "이미지 빌드에 실패했습니다.",
    "deploy": "Workload 배포에 실패했습니다.",
}


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def make_body(step, message, run_id=None, url=None, reason=None):
    body = {"status": "failed" if reason else STATUS_BY_STEP[step], "step": step, "message": message}
    if run_id:
        body["run_id"] = int(run_id)  # API spec 9-4 sends the Actions run ID as a number
    if url:
        body["url"] = url
    if reason:
        body["reason"] = reason
    return body


def final_body(results, reasons_dir, app_url=None):
    """results: {"prepare": "success", ...} from needs.<job>.result. The first non-success job is the failed step."""
    for job in JOBS:
        result = results.get(job, "skipped")
        if result == "success":
            continue
        reason_file = Path(reasons_dir) / f"{job}.txt"
        # A job can name the exact step that failed (e.g. verify inside the deploy job).
        step_file = Path(reasons_dir) / f"{job}.step"
        step = step_file.read_text(encoding="utf-8").strip() if step_file.is_file() else job
        if result == "cancelled":
            reason = "배포가 취소되었습니다."
        elif reason_file.is_file():
            reason = reason_file.read_text(encoding="utf-8").strip()
        else:
            reason = DEFAULT_REASONS[job]
        if step not in STATUS_BY_STEP or step == "done":
            step = job
        return make_body(step, f"{step} 단계에서 멈췄습니다.", reason=reason)
    return make_body("done", "배포가 완료되었습니다.", url=app_url)


# Per-resource progress for the tree view, read from Terraform's machine-readable output.
STATE_LABELS = {"pending": "대기", "in_progress": "진행 중", "done": "완료", "failed": "실패"}


def resource_body(resources, message):
    return {"status": "deploying", "step": "deploy", "message": message, "resources": resources}


def plan_resources(plan):
    """`terraform show -json tfplan` -> every managed resource in the plan. Unchanged ones are already done."""
    resources = []
    for rc in plan.get("resource_changes", []):
        if rc.get("mode") != "managed":
            continue
        actions = rc["change"]["actions"]
        action = "replace" if len(actions) == 2 else actions[0]
        resources.append({
            "address": rc["address"],
            "type": rc["type"],
            "action": action,
            "state": "done" if action == "no-op" else "pending",
        })
    return resources


def apply_events(lines):
    """`terraform apply -json` lines -> one resource update per start, completion or error.

    Terraform prints the error diagnostic after apply_errored, so a failure waits for its diagnostic (or the end).
    """
    failed = {}
    for line in lines:
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        kind = msg.get("type")
        if kind in ("apply_start", "apply_complete", "apply_errored"):
            hook = msg["hook"]
            r = {"address": hook["resource"]["addr"], "type": hook["resource"]["resource_type"], "action": hook["action"]}
            if kind == "apply_errored":
                failed[r["address"]] = r
                continue
            r["state"] = "in_progress" if kind == "apply_start" else "done"
            yield r
        elif kind == "diagnostic" and msg["diagnostic"].get("severity") == "error":
            d = msg["diagnostic"]
            r = failed.pop(d.get("address"), None)
            if r:
                yield {**r, "state": "failed", "reason": f"{d.get('summary', '')}: {d.get('detail', '')}".strip(": ")[:300]}
    for r in failed.values():
        yield {**r, "state": "failed", "reason": "자원을 만드는 중 오류가 났습니다."}


def echo_messages(lines):
    """Pass lines through while printing Terraform's human-readable message, so the Actions log stays readable."""
    for line in lines:
        try:
            print(json.loads(line).get("@message", ""), flush=True)
        except ValueError:
            print(line.rstrip(), flush=True)
        yield line


def teardown_body(reasons_dir, job_status):
    """Destroy result for the teardown callback (API spec 9-5). job_status is ${{ job.status }}."""
    if job_status == "success":
        return {"status": "success"}
    reason_file = Path(reasons_dir) / "destroy.txt"
    if job_status == "cancelled":
        reason = "내리기가 취소되었습니다."
    elif reason_file.is_file():
        reason = reason_file.read_text(encoding="utf-8").strip()
    else:
        reason = "내리기에 실패했습니다."
    return {"status": "failed", "reason": reason}


def send(body, attempts=3, timeout=10, expected=None):
    url = os.environ.get("CALLBACK_URL", "")
    secret = os.environ.get("DEPLOY_CALLBACK_SECRET", "")
    label = f"{body.get('step', 'teardown')}/{body['status']}"
    if not url or not secret:
        print(f"callback skipped (no url or secret): {json.dumps(body, ensure_ascii=False)}")
        return
    # Only ever call the platform's own callback path for this deployment (or this app's teardown).
    expected = expected or os.environ["CALLBACK_BASE"] + os.environ["DEPLOYMENT_ID"] + "/callback"
    if url != expected:
        print(f"::warning::callback skipped: unexpected callback_url {url}")
        return

    data = json.dumps(body, ensure_ascii=False).encode()
    headers = {"Content-Type": "application/json", "X-Hub-Signature-256": sign(secret, data)}
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data, headers, method="POST"), timeout=timeout) as r:
                print(f"callback {label}: HTTP {r.status}")
                return
        except urllib.error.HTTPError as e:
            if e.code < 500:
                # 409 = finished or stale deployment; the backend ignores it on purpose. Other 4xx will not fix themselves.
                level = "" if e.code == 409 else "::warning::"
                print(f"{level}callback {label}: HTTP {e.code}")
                return
            error = f"HTTP {e.code}"
        except (OSError, http.client.HTTPException) as e:
            # URLError, timeouts, resets and RemoteDisconnected. Retried, never raised.
            error = str(e) or type(e).__name__
        print(f"callback attempt {attempt} failed: {error}")
        time.sleep(2 * attempt)
    print(f"::warning::callback {label} gave up after {attempts} attempts")


def self_test():
    # RFC 4231-style known vector for HMAC-SHA256.
    assert sign("key", b"The quick brown fox jumps over the lazy dog") == (
        "sha256=f7bc83f430538424b13298e6aa6fb143ef4d59a14946175997479dbc2d1a3cd8"
    )
    assert make_body("prepare", "m", run_id="1") == {"status": "pending", "step": "prepare", "message": "m", "run_id": 1}
    assert make_body("verify", "m")["status"] == "deploying"
    assert make_body("build", "m", reason="x")["status"] == "failed"

    import tempfile

    with tempfile.TemporaryDirectory() as d:
        ok = final_body({"prepare": "success", "build": "success", "deploy": "success"}, d, "https://a.example")
        assert ok == {"status": "success", "step": "done", "message": ok["message"], "url": "https://a.example"}
        Path(d, "build.txt").write_text("Dockerfile이 없습니다.\n", encoding="utf-8")
        failed = final_body({"prepare": "success", "build": "failure", "deploy": "skipped"}, d)
        assert (failed["step"], failed["status"], failed["reason"]) == ("build", "failed", "Dockerfile이 없습니다.")
        assert final_body({"prepare": "failure"}, d)["reason"] == DEFAULT_REASONS["prepare"]
        assert final_body({"prepare": "success", "build": "cancelled"}, d)["reason"] == "배포가 취소되었습니다."
        Path(d, "deploy.txt").write_text("앱이 응답하지 않습니다.", encoding="utf-8")
        Path(d, "deploy.step").write_text("verify\n", encoding="utf-8")
        v = final_body({"prepare": "success", "build": "success", "deploy": "failure"}, d)
        assert (v["step"], v["status"], v["reason"]) == ("verify", "failed", "앱이 응답하지 않습니다."), v
        Path(d, "deploy.step").write_text("bogus", encoding="utf-8")
        assert final_body({"prepare": "success", "build": "success", "deploy": "failure"}, d)["step"] == "deploy"

    plan = {"resource_changes": [
        {"address": "aws_lb.app", "mode": "managed", "type": "aws_lb", "change": {"actions": ["create"]}},
        {"address": "aws_ecs_cluster.app", "mode": "managed", "type": "aws_ecs_cluster", "change": {"actions": ["no-op"]}},
        {"address": "aws_ecs_task_definition.app", "mode": "managed", "type": "aws_ecs_task_definition",
         "change": {"actions": ["delete", "create"]}},
        {"address": "data.aws_region.current", "mode": "data", "type": "aws_region", "change": {"actions": ["read"]}},
    ]}
    assert [(r["address"], r["action"], r["state"]) for r in plan_resources(plan)] == [
        ("aws_lb.app", "create", "pending"),
        ("aws_ecs_cluster.app", "no-op", "done"),
        ("aws_ecs_task_definition.app", "replace", "pending"),
    ]

    def hook(kind, addr, rtype, action="create"):
        return json.dumps({"type": kind, "hook": {"resource": {"addr": addr, "resource_type": rtype}, "action": action}})

    lines = [
        '{"type": "version", "terraform": "1.13.0"}',
        hook("apply_start", "aws_lb.app", "aws_lb"),
        hook("apply_progress", "aws_lb.app", "aws_lb"),
        hook("apply_complete", "aws_lb.app", "aws_lb"),
        hook("apply_start", "aws_ecs_service.app", "aws_ecs_service"),
        hook("apply_errored", "aws_ecs_service.app", "aws_ecs_service"),
        hook("apply_errored", "aws_iam_role.execution", "aws_iam_role"),
        json.dumps({"type": "diagnostic", "diagnostic": {
            "severity": "error", "summary": "creating ECS Service", "detail": "InvalidParameterException",
            "address": "aws_ecs_service.app"}}),
        "not json",
    ]
    events = [(e["address"], e["state"], e.get("reason")) for e in apply_events(lines)]
    assert events == [
        ("aws_lb.app", "in_progress", None),
        ("aws_lb.app", "done", None),
        ("aws_ecs_service.app", "in_progress", None),
        ("aws_ecs_service.app", "failed", "creating ECS Service: InvalidParameterException"),
        ("aws_iam_role.execution", "failed", "자원을 만드는 중 오류가 났습니다."),
    ], events
    assert resource_body([{"address": "a"}], "m")["status"] == "deploying"

    with tempfile.TemporaryDirectory() as d:
        assert teardown_body(d, "success") == {"status": "success"}
        assert teardown_body(d, "failure") == {"status": "failed", "reason": "내리기에 실패했습니다."}
        assert teardown_body(d, "cancelled")["reason"] == "내리기가 취소되었습니다."
        Path(d, "destroy.txt").write_text("terraform destroy 실패\n", encoding="utf-8")
        assert teardown_body(d, "failure") == {"status": "failed", "reason": "terraform destroy 실패"}

    with tempfile.TemporaryDirectory() as d:
        assert teardown_body(d, "success") == {"status": "success"}
        assert teardown_body(d, "failure") == {"status": "failed", "reason": "내리기에 실패했습니다."}
        assert teardown_body(d, "cancelled")["reason"] == "내리기가 취소되었습니다."
        Path(d, "destroy.txt").write_text("terraform destroy 실패\n", encoding="utf-8")
        assert teardown_body(d, "failure") == {"status": "failed", "reason": "terraform destroy 실패"}
    print("self-test ok")


def main():
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    if sys.argv[1:] == ["plan-resources"]:
        resources = plan_resources(json.load(sys.stdin))
        return send(resource_body(resources, f"만들 자원 {len(resources)}개를 확인했습니다."))
    if sys.argv[1:] == ["apply-events"]:
        # Must read stdin to the end, or terraform blocks on a full pipe. Short retries so apply is not held up.
        for r in apply_events(echo_messages(sys.stdin)):
            send(resource_body([r], f"{r['address']} {STATE_LABELS[r['state']]}"), attempts=2, timeout=5)
        return
    if sys.argv[1:] == ["teardown"]:
        expected = f"{os.environ['API_BASE']}/app-spaces/{os.environ['APPLICATION_ID']}/teardown/callback"
        return send(teardown_body(os.environ.get("REASONS_DIR", "reasons"), os.environ["JOB_STATUS"]), expected=expected)
    if sys.argv[1:] == ["teardown"]:
        expected = f"{os.environ['API_BASE']}/app-spaces/{os.environ['APPLICATION_ID']}/teardown/callback"
        return send(teardown_body(os.environ.get("REASONS_DIR", "reasons"), os.environ["JOB_STATUS"]), expected=expected)
    if sys.argv[1:] == ["final"]:
        results = {job: os.environ.get(f"{job.upper()}_RESULT", "skipped") for job in JOBS}
        return send(final_body(results, os.environ.get("REASONS_DIR", "reasons"), os.environ.get("APP_URL") or None))
    parser = argparse.ArgumentParser()
    parser.add_argument("step", choices=STATUS_BY_STEP)
    parser.add_argument("message")
    parser.add_argument("--run-id")
    parser.add_argument("--url")
    parser.add_argument("--reason")
    a = parser.parse_args()
    send(make_body(a.step, a.message, a.run_id, a.url, a.reason))


if __name__ == "__main__":
    main()
