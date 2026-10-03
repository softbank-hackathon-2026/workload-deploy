"""Build the Terraform variables for one deployment (ADR-009 step 3, API spec 8-1).

Values come from the backend: GET /api/plans/{plan_id}, signed like the callbacks (HMAC of the plan_id string).
Before the backend is connected, a manual run can pass the same response shape as TEST_PLAN (JSON) instead.

The pipeline's own values (application_id, deployment_id, infra_id, image) are always set by the workflow,
so plan values with those names are dropped and cannot override them.

Usage:
  plan.py target <plan.json> # fetches the plan once, saves it, prints the target account as step outputs
  plan.py <tfvars.json>      # writes the variables file (from PLAN_FILE if set), prints the template name
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
# Infra Space values each template takes: a number is the minimum list length, 0 means one non-empty value.
# basic ALB spans two AZs, EC2 uses one subnet, Lambda needs no network, shared-alb joins the Space's own ALB.
INFRA_NEEDS = {
    "ecs-fargate/basic": {"vpc_id": 0, "public_subnet_ids": 2},
    "ecs-fargate/shared-alb": {"vpc_id": 0, "private_subnet_ids": 2, "alb_listener_arn": 0,
                               "alb_security_group_id": 0, "alb_base_url": 0},
    "lambda/basic": {},
    "ec2/basic": {"vpc_id": 0, "public_subnet_ids": 1},
}
# AWS accounts an app can be deployed to. The Infra Space names its account in infra.aws_account_id (default Workload);
# the workflow picks the matching keys (<secrets>_AWS_ACCESS_KEY_ID), state bucket and image repository from here.
ACCOUNTS = {
    "921810471078": {"name": "workload", "secrets": "WORKLOAD", "bucket": "sbh-workload-demo-s3-tfstate-921810471078",
                     "ecr": "sbh-workload-demo-ecr-apps"},
    "635738234799": {"name": "sandbox", "secrets": "SANDBOX", "bucket": "sbh-sandbox-s3-tfstate-635738234799",
                     "ecr": "sbh-sandbox-ecr-apps"},
}
DEFAULT_ACCOUNT = "921810471078"
RESERVED = {"application_id", "deployment_id", "infra_id", "image", "region"}
TEMPLATE_PATTERN = re.compile(r"^[a-z0-9-]+/[a-z0-9-]+$")


def fetch_plan(api_base, plan_id, secret):
    req = urllib.request.Request(
        f"{api_base}/plans/{plan_id}",
        headers={"X-Hub-Signature-256": sign(secret, plan_id.encode())},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def target(plan):
    """The account this plan deploys to, from infra.aws_account_id. Only accounts listed in ACCOUNTS are allowed."""
    infra = plan.get("infra") or {}
    # Default only when the field is absent; an empty or wrong value is refused rather than sent to Workload.
    account_id = infra["aws_account_id"] if "aws_account_id" in infra else DEFAULT_ACCOUNT
    if not isinstance(account_id, str) or account_id not in ACCOUNTS:
        raise ValueError(f"배포할 수 없는 AWS 계정입니다: {account_id}")
    return {"account_id": account_id, **ACCOUNTS[account_id]}


def build(plan, compute, templates_dir, pipeline, exposed_port=None):
    """plan: {"template", "values", "infra": {...}} -> {"template", "vars"}. INFRA_NEEDS lists the infra keys per template.

    pipeline: the workflow's own values (application_id, deployment_id, infra_id, image), applied last.
    exposed_port: the port from the app's Dockerfile EXPOSE, used only when the plan has no container_port.
    """
    template = plan.get("template") or DEFAULT_TEMPLATES[compute]
    # The template name becomes a path, so only a plain <compute>/<name> under templates/ is allowed.
    if not TEMPLATE_PATTERN.match(template) or not template.startswith(compute + "/"):
        raise ValueError(f"템플릿 이름이 올바르지 않습니다: {template}")
    if not (Path(templates_dir) / template).is_dir():
        raise ValueError(f"없는 템플릿입니다: {template}")

    if template not in INFRA_NEEDS:
        raise ValueError(f"인프라 값 목록이 정해지지 않은 템플릿입니다: {template}")
    infra = plan.get("infra") or {}
    missing = [k for k, n in INFRA_NEEDS[template].items()
               if not infra.get(k) or (n and len(infra[k]) < n)]
    if missing:
        raise ValueError(f"인프라 값이 없습니다: {', '.join(missing)}")
    network = {k: infra[k] for k in INFRA_NEEDS[template]}

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

        # shared-alb takes the private subnets and the Space's ALB, not the public subnets.
        Path(d, "ecs-fargate", "shared-alb").mkdir(parents=True)
        multiaz = {**infra, "private_subnet_ids": ["subnet-pa", "subnet-pc"], "alb_listener_arn": "arn:listener",
                   "alb_security_group_id": "sg-alb", "alb_base_url": "https://demo.howon.me"}
        out = build({"template": "ecs-fargate/shared-alb", "values": {"path_pattern": "/api/*", "rule_priority": 10},
                     "infra": multiaz}, "ecs-fargate", d, pipeline)["vars"]
        assert "public_subnet_ids" not in out and out["private_subnet_ids"] == ["subnet-pa", "subnet-pc"], out
        assert (out["alb_listener_arn"], out["path_pattern"], out["rule_priority"]) == ("arn:listener", "/api/*", 10), out
        try:
            build({"template": "ecs-fargate/shared-alb", "infra": infra}, "ecs-fargate", d, pipeline)
        except ValueError as e:
            assert "alb_listener_arn" in str(e), e
        else:
            raise AssertionError("shared-alb without ALB values must be rejected")

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

    # Target account: Workload by default, Sandbox when the Space says so, anything else refused.
    assert target({})["name"] == "workload"
    sandbox = target({"infra": {"aws_account_id": "635738234799"}})
    assert (sandbox["secrets"], sandbox["bucket"]) == ("SANDBOX", "sbh-sandbox-s3-tfstate-635738234799"), sandbox
    for bad in ("123456789012", "", 0, None, 635738234799):
        try:
            target({"infra": {"aws_account_id": bad}})
        except ValueError:
            continue
        raise AssertionError(f"account {bad!r} must be rejected")

    print("self-test ok")


def load_plan():
    """The backend plan (PLAN_ID), or TEST_PLAN for a manual run."""
    plan_id = os.environ.get("PLAN_ID", "")
    if plan_id:
        try:
            return fetch_plan(os.environ["API_BASE"], plan_id, os.environ.get("DEPLOY_CALLBACK_SECRET", ""))
        except OSError as e:
            raise ValueError(f"백엔드에서 구성안({plan_id})을 받지 못했습니다: {e}") from e
    try:
        plan = json.loads(os.environ.get("TEST_PLAN") or "{}")
    except json.JSONDecodeError as e:
        raise ValueError("test_plan이 올바른 JSON이 아닙니다.") from e
    if not isinstance(plan, dict):
        raise ValueError("test_plan은 JSON 객체여야 합니다.")
    return plan


def fail(e):
    print(f"::error::{e}", file=sys.stderr)
    if os.environ.get("REASON_FILE"):
        Path(os.environ["REASON_FILE"]).write_text(str(e), encoding="utf-8")
    sys.exit(1)


def main():
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    # target <plan.json>: fetch the plan once, save it, print the target account as GitHub step outputs.
    # account <name>: the same step outputs for a known account name, for Destroy (it has no plan).
    if sys.argv[1:2] == ["account"]:
        account_id = next(k for k, v in ACCOUNTS.items() if v["name"] == sys.argv[2])
        print("\n".join(f"{k}={v}" for k, v in {"account_id": account_id, **ACCOUNTS[account_id]}.items()))
        return
    if sys.argv[1:2] == ["target"]:
        try:
            plan = load_plan()
            t = target(plan)
        except ValueError as e:
            fail(e)
        Path(sys.argv[2]).write_text(json.dumps(plan), encoding="utf-8")
        print("\n".join(f"{k}={v}" for k, v in t.items()))
        return
    pipeline = {
        "application_id": os.environ["APPLICATION_ID"],
        "deployment_id": os.environ["DEPLOYMENT_ID"],
        "infra_id": os.environ["INFRA_ID"],
        "image": os.environ["IMAGE"],
    }
    try:
        plan = json.loads(Path(os.environ["PLAN_FILE"]).read_text(encoding="utf-8")) if os.environ.get("PLAN_FILE") else load_plan()
        exposed = os.environ.get("EXPOSED_PORT", "")
        exposed_port = int(exposed) if exposed.isdigit() and 1 <= int(exposed) <= 65535 else None
        out = build(plan, os.environ["COMPUTE"], os.environ.get("TEMPLATES_DIR", "templates"), pipeline, exposed_port)
    except ValueError as e:
        fail(e)
    Path(sys.argv[1]).write_text(json.dumps(out["vars"]), encoding="utf-8")
    print(out["template"])


if __name__ == "__main__":
    main()
