import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from src import setup_serverless
from src.setup_serverless import (
    build_lambda_zip,
    build_stack_parameters,
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

    def test_template_outputs_review_url(self):
        template = load_template()

        self.assertIn("ReviewApiUrl", template["Outputs"])
        self.assertIn("ApiKeyId", template["Outputs"])

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

    def test_stage_and_usage_plan_apply_throttling(self):
        resources = load_template()["Resources"]
        method_setting = resources["ReviewStage"]["Properties"][
            "MethodSettings"
        ][0]
        usage_plan = resources["ReviewUsagePlan"]["Properties"]

        self.assertEqual(method_setting["ThrottlingBurstLimit"], 5)
        self.assertEqual(method_setting["ThrottlingRateLimit"], 2)
        self.assertEqual(usage_plan["Throttle"]["BurstLimit"], 5)
        self.assertEqual(usage_plan["Throttle"]["RateLimit"], 2)
        self.assertEqual(usage_plan["Quota"]["Limit"], 1000)

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
                    "api_key_value": "must-not-be-written",
                },
            )

            self.assertEqual(
                json.loads(path.read_text()),
                {
                    "review_api_url": "https://example.com/review",
                    "api_key_id": "key-1",
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


if __name__ == "__main__":
    unittest.main()
