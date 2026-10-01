"""Send a deployment status callback to the platform backend (ADR-009, API spec 9-4).

The JSON body is signed with HMAC-SHA256 in X-Hub-Signature-256, the same scheme as GitHub webhooks.
Skips when CALLBACK_URL or DEPLOY_CALLBACK_SECRET is empty, so the workflow runs before the backend
endpoint exists. A failed callback never fails the deployment: the backend falls back to polling Actions.

Usage:
  callback.py <step> <message> [--run-id ID] [--url URL] [--reason TEXT]
  callback.py final                 # reads job results from env, sends success or failed
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
        body["run_id"] = run_id
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
        if result == "cancelled":
            reason = "배포가 취소되었습니다."
        elif reason_file.is_file():
            reason = reason_file.read_text(encoding="utf-8").strip()
        else:
            reason = DEFAULT_REASONS[job]
        return make_body(job, f"{job} 단계에서 멈췄습니다.", reason=reason)
    return make_body("done", "배포가 완료되었습니다.", url=app_url)


def send(body):
    url = os.environ.get("CALLBACK_URL", "")
    secret = os.environ.get("DEPLOY_CALLBACK_SECRET", "")
    if not url or not secret:
        print(f"callback skipped (no url or secret): {json.dumps(body, ensure_ascii=False)}")
        return
    # Only ever call the platform's own callback path for this deployment.
    expected = os.environ["CALLBACK_BASE"] + os.environ["DEPLOYMENT_ID"] + "/callback"
    if url != expected:
        print(f"::warning::callback skipped: unexpected callback_url {url}")
        return

    data = json.dumps(body, ensure_ascii=False).encode()
    headers = {"Content-Type": "application/json", "X-Hub-Signature-256": sign(secret, data)}
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data, headers, method="POST"), timeout=10) as r:
                print(f"callback {body['step']}/{body['status']}: HTTP {r.status}")
                return
        except urllib.error.HTTPError as e:
            if e.code < 500:
                # 409 = finished or stale deployment; the backend ignores it on purpose. Other 4xx will not fix themselves.
                level = "" if e.code == 409 else "::warning::"
                print(f"{level}callback {body['step']}/{body['status']}: HTTP {e.code}")
                return
            error = f"HTTP {e.code}"
        except (OSError, http.client.HTTPException) as e:
            # URLError, timeouts, resets and RemoteDisconnected. Retried, never raised.
            error = str(e) or type(e).__name__
        print(f"callback attempt {attempt} failed: {error}")
        time.sleep(2 * attempt)
    print(f"::warning::callback {body['step']} gave up after 3 attempts")


def self_test():
    # RFC 4231-style known vector for HMAC-SHA256.
    assert sign("key", b"The quick brown fox jumps over the lazy dog") == (
        "sha256=f7bc83f430538424b13298e6aa6fb143ef4d59a14946175997479dbc2d1a3cd8"
    )
    assert make_body("prepare", "m", run_id="1") == {"status": "pending", "step": "prepare", "message": "m", "run_id": "1"}
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
    print("self-test ok")


def main():
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
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
