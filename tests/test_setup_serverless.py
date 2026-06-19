import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from src import setup_serverless
from src.setup_serverless import (
    build_github_webhook_payload,
    build_lambda_zip,
    build_stack_parameters,
    configure_github_webhook,
    ensure_github_webhook,
    load_template,
    save_serverless_state,
    stack_exists,
)


class LambdaPackageTests(unittest.TestCase):
    def test_build_lambda_zip_contains_handler_module(self):
        archive = build_lambda_zip(
            Path("lambda/codebuddy_orchestrator.py")
        )

        with ZipFile(BytesIO(archive)) as zip_file:
            self.assertEqual(
                zip_file.namelist(),
                ["codebuddy_orchestrator.py"],
            )

    def test_build_deployment_artifacts_packages_both_lambdas(self):
        self.assertTrue(
            hasattr(setup_serverless, "build_deployment_artifacts")
        )
        artifacts = setup_serverless.build_deployment_artifacts()

        self.assertEqual(
            set(artifacts),
            {"orchestrator", "review-worker"},
        )
        with ZipFile(BytesIO(artifacts["orchestrator"])) as zip_file:
            self.assertEqual(
                zip_file.namelist(),
                ["codebuddy_orchestrator.py"],
            )
        with ZipFile(BytesIO(artifacts["review-worker"])) as zip_file:
            self.assertEqual(
                zip_file.namelist(),
                ["codebuddy_review_worker.py"],
            )


class TemplateTests(unittest.TestCase):
    def test_template_defines_review_api_and_two_lambdas(self):
        template = load_template()
        resources = template["Resources"]

        self.assertIn("ReviewApi", resources)
        self.assertIn("ReviewResource", resources)
        self.assertIn("ReviewPostMethod", resources)
        self.assertIn("ReviewOptionsMethod", resources)
        self.assertIn("OrchestratorFunction", resources)
        self.assertIn("ReviewWorkerFunction", resources)
        self.assertIn("ReviewApiKey", resources)
        self.assertIn("ReviewUsagePlan", resources)
        self.assertIn("WebhookSecret", resources)
        self.assertIn("WebhookResource", resources)
        self.assertIn("GitHubWebhookResource", resources)
        self.assertIn("GitHubWebhookPostMethod", resources)

    def test_template_outputs_review_url(self):
        template = load_template()

        self.assertIn("ReviewApiUrl", template["Outputs"])
        self.assertIn("ApiKeyId", template["Outputs"])
        self.assertIn("GitHubWebhookUrl", template["Outputs"])
        self.assertIn("WebhookSecretArn", template["Outputs"])

    def test_worker_role_can_only_invoke_configured_agent_alias(self):
        template = load_template()
        statement = template["Resources"]["WorkerRole"]["Properties"][
            "Policies"
        ][0]["PolicyDocument"]["Statement"][0]

        self.assertEqual(statement["Action"], ["bedrock:InvokeAgent"])
        self.assertEqual(
            statement["Resource"]["Fn::Sub"],
            (
                "arn:${AWS::Partition}:bedrock:${AWS::Region}:"
                "${AWS::AccountId}:agent-alias/${AgentId}/${AliasId}"
            ),
        )

    def test_review_post_requires_api_key_and_options_does_not(self):
        resources = load_template()["Resources"]

        self.assertTrue(
            resources["ReviewPostMethod"]["Properties"]["ApiKeyRequired"]
        )
        self.assertFalse(
            resources["ReviewOptionsMethod"]["Properties"]["ApiKeyRequired"]
        )
        self.assertIn("GitHubWebhookPostMethod", resources)
        self.assertFalse(
            resources.get(
                "GitHubWebhookPostMethod",
                {"Properties": {"ApiKeyRequired": True}},
            )["Properties"][
                "ApiKeyRequired"
            ]
        )

    def test_orchestrator_can_read_only_generated_webhook_secret(self):
        template = load_template()
        policies = template["Resources"]["OrchestratorRole"]["Properties"][
            "Policies"
        ]
        secret_policies = [
            policy
            for policy in policies
            if policy["PolicyName"] == "ReadGitHubWebhookSecret"
        ]
        self.assertEqual(len(secret_policies), 1)
        secret_policy = secret_policies[0]
        statement = secret_policy["PolicyDocument"]["Statement"][0]

        self.assertEqual(
            statement["Action"],
            ["secretsmanager:GetSecretValue"],
        )
        self.assertEqual(
            statement["Resource"],
            {"Ref": "WebhookSecret"},
        )

    def test_api_deployment_depends_on_webhook_method(self):
        deployment = load_template()["Resources"]["ReviewDeployment"]

        self.assertIn(
            "GitHubWebhookPostMethod",
            deployment["DependsOn"],
        )

    def test_stage_and_usage_plan_apply_throttling(self):
        resources = load_template()["Resources"]
        method_settings = resources["ReviewStage"]["Properties"][
            "MethodSettings"
        ]
        method_setting = method_settings[0]
        usage_plan = resources["ReviewUsagePlan"]["Properties"]

        self.assertEqual(method_setting["ThrottlingBurstLimit"], 10)
        self.assertEqual(method_setting["ThrottlingRateLimit"], 5)
        self.assertEqual(usage_plan["Throttle"]["BurstLimit"], 5)
        self.assertEqual(usage_plan["Throttle"]["RateLimit"], 2)
        self.assertEqual(usage_plan["Quota"]["Limit"], 1000)

        webhook_setting = next(
            (
                setting
                for setting in method_settings
                if setting["ResourcePath"] == "/~1webhook~1github"
                and setting["HttpMethod"] == "POST"
            ),
            None,
        )
        self.assertIsNotNone(webhook_setting)
        self.assertEqual(webhook_setting["ThrottlingBurstLimit"], 5)
        self.assertEqual(webhook_setting["ThrottlingRateLimit"], 2)

    def test_worker_timeout_leaves_margin_after_agent_read_timeout(self):
        worker = load_template()["Resources"]["ReviewWorkerFunction"]

        self.assertEqual(worker["Properties"]["Timeout"], 360)

    def test_orchestrator_uses_explicit_non_wildcard_cors_origin(self):
        template = load_template()
        self.assertIn("AllowedOrigin", template["Parameters"])
        allowed_origin = template["Parameters"].get(
            "AllowedOrigin",
            {"Default": "*"},
        )
        environment = template["Resources"]["OrchestratorFunction"][
            "Properties"
        ]["Environment"]["Variables"]

        self.assertNotEqual(allowed_origin["Default"], "*")
        self.assertEqual(
            environment["ALLOWED_ORIGIN"],
            {"Ref": "AllowedOrigin"},
        )


class ParameterTests(unittest.TestCase):
    def test_build_stack_parameters_maps_artifacts_and_agent(self):
        parameters = build_stack_parameters(
            artifact_bucket="bucket",
            orchestrator_key="orchestrator.zip",
            worker_key="worker.zip",
            agent_id="AGENT1",
            alias_id="ALIAS1",
        )

        self.assertEqual(
            parameters,
            [
                {"ParameterKey": "ArtifactBucket", "ParameterValue": "bucket"},
                {
                    "ParameterKey": "OrchestratorCodeKey",
                    "ParameterValue": "orchestrator.zip",
                },
                {
                    "ParameterKey": "WorkerCodeKey",
                    "ParameterValue": "worker.zip",
                },
                {"ParameterKey": "AgentId", "ParameterValue": "AGENT1"},
                {"ParameterKey": "AliasId", "ParameterValue": "ALIAS1"},
            ],
        )


class StateTests(unittest.TestCase):
    def test_save_serverless_state_writes_outputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "state.json"

            save_serverless_state(
                path,
                {
                    "ReviewApiUrl": "https://example.com/review",
                    "ApiKeyId": "key-1",
                    "GitHubWebhookUrl": "https://example.com/webhook/github",
                    "WebhookSecretArn": "arn:aws:secretsmanager:secret-1",
                    "api_key_value": "must-not-be-written",
                },
            )

            self.assertEqual(
                json.loads(path.read_text()),
                {
                    "review_api_url": "https://example.com/review",
                    "api_key_id": "key-1",
                    "github_webhook_url": (
                        "https://example.com/webhook/github"
                    ),
                    "webhook_secret_arn": (
                        "arn:aws:secretsmanager:secret-1"
                    ),
                },
            )


class StackStateTests(unittest.TestCase):
    def test_stack_exists_rejects_failed_stack_state(self):
        class CloudFormationClient:
            def describe_stacks(self, **kwargs):
                return {
                    "Stacks": [
                        {"StackStatus": "UPDATE_ROLLBACK_FAILED"}
                    ]
                }

        with self.assertRaisesRegex(RuntimeError, "ROLLBACK_FAILED"):
            stack_exists(CloudFormationClient(), "CodeBuddyServerless")


class GitHubWebhookConfigurationTests(unittest.TestCase):
    def test_build_github_webhook_payload_uses_hmac_secret(self):
        payload = build_github_webhook_payload(
            "https://example.com/prod/webhook/github",
            "webhook-secret",
        )

        self.assertEqual(payload["events"], ["pull_request"])
        self.assertTrue(payload["active"])
        self.assertEqual(payload["config"]["content_type"], "json")
        self.assertEqual(
            payload["config"]["url"],
            "https://example.com/prod/webhook/github",
        )
        self.assertEqual(
            payload["config"]["secret"],
            "webhook-secret",
        )

    def test_ensure_github_webhook_creates_missing_hook(self):
        calls = []

        def request_json(method, path, payload=None):
            calls.append((method, path, payload))
            return [] if method == "GET" else {"id": 7}

        hook_id = ensure_github_webhook(
            request_json,
            "hjh6709",
            "codebuddy-project",
            "https://example.com/prod/webhook/github",
            "webhook-secret",
        )

        self.assertEqual(hook_id, 7)
        self.assertEqual(calls[1][0], "POST")
        self.assertEqual(
            calls[1][1],
            "/repos/hjh6709/codebuddy-project/hooks",
        )

    def test_ensure_github_webhook_updates_matching_hook(self):
        calls = []

        def request_json(method, path, payload=None):
            calls.append((method, path, payload))
            if method == "GET":
                return [
                    {
                        "id": 9,
                        "config": {
                            "url": (
                                "https://example.com/prod/webhook/github"
                            )
                        },
                    }
                ]
            return {"id": 9}

        hook_id = ensure_github_webhook(
            request_json,
            "hjh6709",
            "codebuddy-project",
            "https://example.com/prod/webhook/github",
            "rotated-secret",
        )

        self.assertEqual(hook_id, 9)
        self.assertEqual(calls[1][0], "PATCH")
        self.assertEqual(
            calls[1][1],
            "/repos/hjh6709/codebuddy-project/hooks/9",
        )

    def test_configure_github_webhook_reads_secret_without_returning_it(self):
        class SecretsClient:
            def get_secret_value(self, **kwargs):
                self.request = kwargs
                return {"SecretString": "webhook-secret"}

        secrets_client = SecretsClient()
        calls = []

        def request_json(method, path, payload=None):
            calls.append((method, path, payload))
            return [] if method == "GET" else {"id": 11}

        hook_id = configure_github_webhook(
            secrets_client,
            request_json,
            "hjh6709/codebuddy-project",
            {
                "GitHubWebhookUrl": (
                    "https://example.com/prod/webhook/github"
                ),
                "WebhookSecretArn": "arn:secret",
            },
        )

        self.assertEqual(hook_id, 11)
        self.assertEqual(
            secrets_client.request,
            {"SecretId": "arn:secret"},
        )
        self.assertNotEqual(hook_id, "webhook-secret")
        self.assertEqual(
            calls[1][2]["config"]["secret"],
            "webhook-secret",
        )

    def test_configure_github_webhook_rejects_invalid_repository(self):
        with self.assertRaisesRegex(ValueError, "owner/repository"):
            configure_github_webhook(
                object(),
                lambda *args: None,
                "invalid-repository",
                {
                    "GitHubWebhookUrl": "https://example.com/webhook",
                    "WebhookSecretArn": "arn:secret",
                },
            )


if __name__ == "__main__":
    unittest.main()
