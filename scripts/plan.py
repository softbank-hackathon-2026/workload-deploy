"""Build the Terraform variables for one deployment (ADR-009 step 3, API spec 8-1).

Values come from the backend: GET /api/plans/{plan_id}, signed like the callbacks (HMAC of the plan_id string).
Before the backend is connected, a manual run can pass the same response shape as TEST_PLAN (JSON) instead.

The pipeline's own values (application_id, deployment_id, infra_id, image) are always set by the workflow,
so plan values with those names are dropped and cannot override them.

Usage:
  plan.py <tfvars.json>      # writes the variables file, prints the template name (e.g. ecs-fargate/basic)
  plan.py --self-test
"""
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from callback import sign  # noqa: E402

DEFAULT_TEMPLATES = {"ecs-fargate": "ecs-fargate/basic", "lambda": "lambda/basic", "ec2": "ec2/basic"}
# Computes that run inside the Space VPC, with the public subnets each needs (the ALB spans two AZs, EC2 uses one).
# Lambda is public through its function URL and needs no network values.
MIN_SUBNETS = {"ecs-fargate": 2, "ec2": 1}
RESERVED = {"application_id", "deployment_id", "infra_id", "image", "region"}
TEMPLATE_PATTERN = re.compile(r"^[a-z0-9-]+/[a-z0-9-]+$")


def fetch_plan(api_base, plan_id, secret):
    req = urllib.request.Request(
        f"{api_base}/plans/{plan_id}",
        headers={"X-Hub-Signature-256": sign(secret, plan_id.encode())},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def build(plan, compute, templates_dir, pipeline, exposed_port=None):
    """plan: {"template", "values", "infra": {"vpc_id", "public_subnet_ids"}} -> {"template", "vars"}.

    pipeline: the workflow's own values (application_id, deployment_id, infra_id, image), applied last.
    exposed_port: the port from the app's Dockerfile EXPOSE, used only when the plan has no container_port.
    """
    template = plan.get("template") or DEFAULT_TEMPLATES[compute]
    # The template name becomes a path, so only a plain <compute>/<name> under templates/ is allowed.
    if not TEMPLATE_PATTERN.match(template) or not template.startswith(compute + "/"):
        raise ValueError(f"템플릿 이름이 올바르지 않습니다: {template}")
    if not (Path(templates_dir) / template).is_dir():
        raise ValueError(f"없는 템플릿입니다: {template}")

    network = {}
    if compute in MIN_SUBNETS:
        infra = plan.get("infra") or {}
        need = MIN_SUBNETS[compute]
        if not infra.get("vpc_id") or len(infra.get("public_subnet_ids") or []) < need:
            raise ValueError(f"인프라 값(VPC, 퍼블릭 서브넷 {need}개)이 없습니다.")
        network = {"vpc_id": infra["vpc_id"], "public_subnet_ids": infra["public_subnet_ids"]}

    values = {k: v for k, v in (plan.get("values") or {}).items() if k not in RESERVED}
    if "container_port" not in values and exposed_port:
        values["container_port"] = exposed_port
    return {
        "template": template,
        "vars": {**values, **network, **pipeline},
    }


def self_test():
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        Path(d, "ecs-fargate", "basic").mkdir(parents=True)
        infra = {"vpc_id": "vpc-1", "public_subnet_ids": ["subnet-a", "subnet-c"]}
        pipeline = {"application_id": "app-1", "image": "repo@sha256:abc"}

        out = build({"template": "ecs-fargate/basic", "values": {"container_port": 3000, "image": "evil"}, "infra": infra},
                    "ecs-fargate", d, pipeline)
        assert out == {"template": "ecs-fargate/basic",
                       "vars": {"container_port": 3000, "vpc_id": "vpc-1", "public_subnet_ids": ["subnet-a", "subnet-c"],
                                "application_id": "app-1", "image": "repo@sha256:abc"}}, out

        # No plan (manual test): default template and only Space values.
        assert build({"infra": infra}, "ecs-fargate", d, pipeline)["template"] == "ecs-fargate/basic"

        # Dockerfile EXPOSE fills container_port only when the plan does not set it.
        assert build({"infra": infra}, "ecs-fargate", d, pipeline, 3000)["vars"]["container_port"] == 3000
        assert build({"values": {"container_port": 8080}, "infra": infra}, "ecs-fargate", d, pipeline, 3000)["vars"]["container_port"] == 8080
        assert "container_port" not in build({"infra": infra}, "ecs-fargate", d, pipeline)["vars"]

        # Lambda takes no network values, even when the Space sends them.
        Path(d, "lambda", "basic").mkdir(parents=True)
        out = build({"values": {"memory": 1024}, "infra": infra}, "lambda", d, pipeline, 3000)
        assert out == {"template": "lambda/basic",
                       "vars": {"memory": 1024, "container_port": 3000, "application_id": "app-1", "image": "repo@sha256:abc"}}, out

        # EC2 needs the VPC and one public subnet; ecs-fargate needs two.
        Path(d, "ec2", "basic").mkdir(parents=True)
        one = {"vpc_id": "vpc-1", "public_subnet_ids": ["subnet-a"]}
        assert build({"infra": one}, "ec2", d, pipeline)["vars"]["public_subnet_ids"] == ["subnet-a"]

        for bad in ("../../etc", "lambda/basic", "ecs-fargate/missing", "ecs-fargate/basic/.."):
            try:
                build({"template": bad, "infra": infra}, "ecs-fargate", d, pipeline)
            except ValueError:
                continue
            raise AssertionError(f"template {bad} must be rejected")

        try:
            build({"infra": {"vpc_id": "vpc-1", "public_subnet_ids": ["subnet-a"]}}, "ecs-fargate", d, pipeline)
        except ValueError:
            pass
        else:
            raise AssertionError("one subnet must be rejected")

    print("self-test ok")


def main():
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    pipeline = {
        "application_id": os.environ["APPLICATION_ID"],
        "deployment_id": os.environ["DEPLOYMENT_ID"],
        "infra_id": os.environ["INFRA_ID"],
        "image": os.environ["IMAGE"],
    }
    plan_id = os.environ.get("PLAN_ID", "")
    try:
        if plan_id:
            try:
                plan = fetch_plan(os.environ["API_BASE"], plan_id, os.environ.get("DEPLOY_CALLBACK_SECRET", ""))
            except OSError as e:
                raise ValueError(f"백엔드에서 구성안({plan_id})을 받지 못했습니다: {e}") from e
        else:
            try:
                plan = json.loads(os.environ.get("TEST_PLAN") or "{}")
            except json.JSONDecodeError as e:
                raise ValueError("test_plan이 올바른 JSON이 아닙니다.") from e
            if not isinstance(plan, dict):
                raise ValueError("test_plan은 JSON 객체여야 합니다.")
        exposed = os.environ.get("EXPOSED_PORT", "")
        exposed_port = int(exposed) if exposed.isdigit() and 1 <= int(exposed) <= 65535 else None
        out = build(plan, os.environ["COMPUTE"], os.environ.get("TEMPLATES_DIR", "templates"), pipeline, exposed_port)
    except ValueError as e:
        print(f"::error::{e}", file=sys.stderr)
        if os.environ.get("REASON_FILE"):
            Path(os.environ["REASON_FILE"]).write_text(str(e), encoding="utf-8")
        sys.exit(1)
    Path(sys.argv[1]).write_text(json.dumps(out["vars"]), encoding="utf-8")
    print(out["template"])


if __name__ == "__main__":
    main()
