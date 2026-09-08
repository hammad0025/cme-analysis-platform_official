"""
AWS CDK Infrastructure Stack for CME Analysis Platform
Deploys all required AWS resources for the Florida happy-path implementation
"""

import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import jsii
from aws_cdk import (
    BundlingOptions,
    ILocalBundling,
    Size,
    Stack,
    Duration,
    aws_lambda as lambda_,
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
    aws_apigateway as apigateway,
    aws_iam as iam,
    aws_sqs as sqs,
    aws_s3_notifications as s3n,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    aws_cognito as cognito,
    aws_cloudwatch as cloudwatch,
    aws_logs as logs,
    RemovalPolicy,
)
from constructs import Construct


@jsii.implements(ILocalBundling)
class FFmpegLayerLocalBundling:
    """Build the Linux ARM FFmpeg layer without requiring a local Docker daemon."""

    IMAGEIO_FFMPEG_REQUIREMENT = "imageio-ffmpeg==0.6.0"
    IMAGEIO_FFMPEG_WHEEL_SHA256 = "1d47bebd83d2c5fc770720d211855f208af8a596c82d17730aa51e815cdee6dc"

    def try_bundle(self, output_dir: str, _options: BundlingOptions) -> bool:
        with tempfile.TemporaryDirectory(prefix="cme-ffmpeg-layer-") as temp_dir:
            temp_path = Path(temp_dir)
            requirements_path = temp_path / "requirements.txt"
            requirements_path.write_text(
                f"{self.IMAGEIO_FFMPEG_REQUIREMENT} \\\n"
                f"    --hash=sha256:{self.IMAGEIO_FFMPEG_WHEEL_SHA256}\n",
                encoding="utf-8",
            )
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "download",
                    "--disable-pip-version-check",
                    "--no-deps",
                    "--only-binary=:all:",
                    "--require-hashes",
                    "--platform",
                    "manylinux2014_aarch64",
                    "--python-version",
                    "3.11",
                    "--implementation",
                    "cp",
                    "--abi",
                    "cp311",
                    "--dest",
                    temp_dir,
                    "--requirement",
                    str(requirements_path),
                ],
                check=True,
            )
            wheel = next(temp_path.glob("imageio_ffmpeg-*.whl"), None)
            if wheel is None:
                raise RuntimeError("FFmpeg layer wheel download produced no package")

            extracted_dir = temp_path / "wheel"
            with zipfile.ZipFile(wheel) as archive:
                archive.extractall(extracted_dir)
            binary = next(
                extracted_dir.glob("imageio_ffmpeg/binaries/ffmpeg-linux-aarch64-*"),
                None,
            )
            if binary is None:
                raise RuntimeError("FFmpeg layer wheel did not contain a Linux ARM binary")

            target = Path(output_dir) / "bin" / "ffmpeg"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(binary, target)
            target.chmod(0o755)
        return True


class CMEAnalysisPlatformStack(Stack):
    """Complete infrastructure stack for CME Analysis Platform"""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ========== S3 Buckets ==========
        # Main storage bucket for CME recordings and processed data
        cme_bucket = s3.Bucket(
            self, "CMERecordingsBucket",
            bucket_name=f"cme-analysis-recordings-{self.account}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN,  # Protect recordings
            cors=[
                s3.CorsRule(
                    allowed_origins=[
                        "https://cme-analysis-platform-official.vercel.app",
                        "http://localhost:3000",
                        "http://localhost:3001"
                    ],
                    allowed_methods=[s3.HttpMethods.GET, s3.HttpMethods.PUT, s3.HttpMethods.POST, s3.HttpMethods.HEAD],
                    allowed_headers=["*"],
                    exposed_headers=["ETag"],
                    max_age=3000
                )
            ],
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="TransitionToIA",
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                            transition_after=Duration.days(90)
                        )
                    ]
                )
            ]
        )

        # ========== DynamoDB Tables ==========
        # CME Sessions table
        sessions_table = dynamodb.Table(
            self, "CMESessionsTable",
            table_name="cme-sessions",
            partition_key=dynamodb.Attribute(
                name="session_id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
            point_in_time_recovery=True,
            stream=dynamodb.StreamViewType.NEW_AND_OLD_IMAGES
        )

        # Declared Steps table
        steps_table = dynamodb.Table(
            self, "CMEDeclaredStepsTable",
            table_name="cme-declared-steps",
            partition_key=dynamodb.Attribute(
                name="declared_step_id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN
        )

        # Add GSI for querying by session_id
        steps_table.add_global_secondary_index(
            index_name="session-index",
            partition_key=dynamodb.Attribute(
                name="session_id",
                type=dynamodb.AttributeType.STRING
            )
        )

        # Observed Actions table
        actions_table = dynamodb.Table(
            self, "CMEObservedActionsTable",
            table_name="cme-observed-actions",
            partition_key=dynamodb.Attribute(
                name="observed_action_id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN
        )

        # Demeanor Flags table
        demeanor_table = dynamodb.Table(
            self, "CMEDemeanorFlagsTable",
            table_name="cme-demeanor-flags",
            partition_key=dynamodb.Attribute(
                name="flag_id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN
        )

        # Consent Records table
        consent_table = dynamodb.Table(
            self, "CMEConsentRecordsTable",
            table_name="cme-consents",
            partition_key=dynamodb.Attribute(
                name="consent_id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN
        )

        # ========== Cognito User Pool ==========
        user_pool = cognito.UserPool(
            self, "CMEUserPool",
            user_pool_name="cme-analysis-users",
            self_sign_up_enabled=False,  # Admin creates accounts
            sign_in_aliases=cognito.SignInAliases(email=True, username=True),
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=True, mutable=True),
                given_name=cognito.StandardAttribute(required=True, mutable=True),
                family_name=cognito.StandardAttribute(required=True, mutable=True)
            ),
            password_policy=cognito.PasswordPolicy(
                min_length=12,
                require_uppercase=True,
                require_lowercase=True,
                require_digits=True,
                require_symbols=True
            ),
            removal_policy=RemovalPolicy.RETAIN
        )

        user_pool_client = user_pool.add_client(
            "CMEUserPoolClient",
            auth_flows=cognito.AuthFlow(user_password=True, user_srp=True),
            generate_secret=False
        )

        # ========== Lambda Functions ==========
        # Common Lambda execution role with required permissions
        lambda_role = iam.Role(
            self, "CMELambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"),
                iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchLogsFullAccess")
            ]
        )

        # Grant permissions
        cme_bucket.grant_read_write(lambda_role)
        sessions_table.grant_read_write_data(lambda_role)
        steps_table.grant_read_write_data(lambda_role)
        actions_table.grant_read_write_data(lambda_role)
        demeanor_table.grant_read_write_data(lambda_role)
        consent_table.grant_read_write_data(lambda_role)

        # Grant Bedrock access
        lambda_role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel"],
            resources=["*"]
        ))

        # Grant Transcribe access (both Medical and Regular for MPEG support)
        lambda_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "transcribe:StartMedicalTranscriptionJob",
                "transcribe:GetMedicalTranscriptionJob",
                "transcribe:ListMedicalTranscriptionJobs",
                "transcribe:StartTranscriptionJob",  # For MPEG/MPG files
                "transcribe:GetTranscriptionJob",     # For MPEG/MPG files
                "transcribe:ListTranscriptionJobs"    # For MPEG/MPG files
            ],
            resources=["*"]
        ))

        # Grant Rekognition access
        lambda_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "rekognition:StartLabelDetection",
                "rekognition:GetLabelDetection",
                "rekognition:StartPersonTracking",
                "rekognition:GetPersonTracking"
            ],
            resources=["*"]
        ))
        
        # Grant Comprehend access
        lambda_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "comprehend:DetectSentiment",
                "comprehend:DetectEntities"
            ],
            resources=["*"]
        ))

        # Grant Step Functions and cross-Lambda invoke for pipeline orchestration
        lambda_role.add_to_policy(iam.PolicyStatement(
            actions=["states:StartExecution"],
            resources=["*"]
        ))
        lambda_role.add_to_policy(iam.PolicyStatement(
            actions=["lambda:InvokeFunction"],
            resources=["*"]
        ))

        # Main API Lambda
        api_lambda = lambda_.Function(
            self, "CMEAPIHandler",
            function_name="cme-api-handler",
            runtime=lambda_.Runtime.PYTHON_3_11,
            code=lambda_.Code.from_asset("../backend/lambda_functions"),
            handler="cme_handler.handler",
            timeout=Duration.seconds(30),
            memory_size=512,
            log_retention=logs.RetentionDays.THREE_MONTHS,
            role=lambda_role,
            environment={
                "S3_BUCKET": cme_bucket.bucket_name,
                "CME_SESSIONS_TABLE": sessions_table.table_name,
                "CME_STEPS_TABLE": steps_table.table_name,
                "CME_ACTIONS_TABLE": actions_table.table_name,
                "CME_DEMEANOR_TABLE": demeanor_table.table_name,
                "CME_CONSENT_TABLE": consent_table.table_name,
                "USER_POOL_ID": user_pool.user_pool_id,
                "USER_POOL_CLIENT_ID": user_pool_client.user_pool_client_id
            }
        )

        # Transcription Waiter Lambda (for Step Functions)
        transcription_waiter_lambda = lambda_.Function(
            self, "TranscriptionWaiter",
            function_name="cme-transcription-waiter",
            runtime=lambda_.Runtime.PYTHON_3_11,
            code=lambda_.Code.from_asset("../backend/lambda_functions"),
            handler="transcription_waiter.handler",
            timeout=Duration.seconds(30),
            memory_size=256,
            log_retention=logs.RetentionDays.THREE_MONTHS,
            role=lambda_role,
            environment={
                "CME_SESSIONS_TABLE": sessions_table.table_name
            }
        )
        
        # NLP Processor Lambda
        nlp_lambda = lambda_.Function(
            self, "CMENLPProcessor",
            function_name="cme-nlp-processor",
            runtime=lambda_.Runtime.PYTHON_3_11,
            code=lambda_.Code.from_asset("../backend/lambda_functions"),
            handler="cme_nlp_processor.handler",
            timeout=Duration.minutes(5),
            memory_size=2048,
            log_retention=logs.RetentionDays.THREE_MONTHS,
            role=lambda_role,
            environment={
                "CME_SESSIONS_TABLE": sessions_table.table_name,
                "CME_STEPS_TABLE": steps_table.table_name,
                "CME_DEMEANOR_TABLE": demeanor_table.table_name,
                "CME_NLP_MODEL_ID": "amazon.nova-lite-v1:0"
            }
        )

        ffmpeg_layer = lambda_.LayerVersion(
            self,
            "CMEFFmpegLayer",
            description="FFmpeg 7.0.2 for deterministic CME visual-evidence extraction",
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_11],
            compatible_architectures=[lambda_.Architecture.ARM_64],
            code=lambda_.Code.from_asset(
                "../backend/lambda_layers/ffmpeg",
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_11.bundling_image,
                    local=FFmpegLayerLocalBundling(),
                ),
            ),
        )

        # Video Processor Lambda
        video_lambda = lambda_.Function(
            self, "CMEVideoProcessor",
            function_name="cme-video-processor",
            runtime=lambda_.Runtime.PYTHON_3_11,
            architecture=lambda_.Architecture.ARM_64,
            code=lambda_.Code.from_asset("../backend/lambda_functions"),
            handler="cme_video_processor.handler",
            timeout=Duration.minutes(15),
            memory_size=3008,
            ephemeral_storage_size=Size.gibibytes(10),
            layers=[ffmpeg_layer],
            log_retention=logs.RetentionDays.THREE_MONTHS,
            role=lambda_role,
            environment={
                "S3_BUCKET": cme_bucket.bucket_name,
                "CME_ACTIONS_TABLE": actions_table.table_name,
                "CME_BEDROCK_MODEL_ID": "amazon.nova-lite-v1:0"
            }
        )

        # Report Generator Lambda
        report_lambda = lambda_.Function(
            self, "CMEReportGenerator",
            function_name="cme-report-generator",
            runtime=lambda_.Runtime.PYTHON_3_11,
            code=lambda_.Code.from_asset("../backend/lambda_functions"),
            handler="cme_report_generator.generate_report",
            timeout=Duration.minutes(5),
            memory_size=1024,
            log_retention=logs.RetentionDays.THREE_MONTHS,
            role=lambda_role,
            environment={
                "S3_BUCKET": cme_bucket.bucket_name,
                "CME_SESSIONS_TABLE": sessions_table.table_name,
                "CME_STEPS_TABLE": steps_table.table_name,
                "CME_ACTIONS_TABLE": actions_table.table_name,
                "CME_DEMEANOR_TABLE": demeanor_table.table_name,
                "CME_CONSENT_TABLE": consent_table.table_name
            }
        )

        # ========== API Gateway ==========
        api = apigateway.RestApi(
            self, "CMEAPI",
            rest_api_name="CME Analysis API",
            description="API for CME Analysis Platform",
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=apigateway.Cors.ALL_ORIGINS,
                allow_methods=apigateway.Cors.ALL_METHODS,
                allow_headers=["*"]
            ),
            deploy_options=apigateway.StageOptions(
                stage_name="prod",
                throttling_rate_limit=1000,
                throttling_burst_limit=2000,
                logging_level=apigateway.MethodLoggingLevel.INFO,
                data_trace_enabled=False
            )
        )

        # API Integration
        api_integration = apigateway.LambdaIntegration(api_lambda)
        cognito_authorizer = apigateway.CognitoUserPoolsAuthorizer(
            self,
            "CMEApiCognitoAuthorizer",
            cognito_user_pools=[user_pool],
            authorizer_name="cme-cognito-authorizer-cdk",
        )
        protected_method_options = {
            "authorization_type": apigateway.AuthorizationType.COGNITO,
            "authorizer": cognito_authorizer,
        }

        # API Resources
        cme = api.root.add_resource("cme")
        sessions = cme.add_resource("sessions")
        sessions.add_method("POST", api_integration, **protected_method_options)
        sessions.add_method("GET", api_integration, **protected_method_options)

        session_detail = sessions.add_resource("{session_id}")
        session_detail.add_method("GET", api_integration, **protected_method_options)

        report = session_detail.add_resource("report")
        report.add_method("GET", api_integration, **protected_method_options)

        consent = cme.add_resource("consent")
        consent.add_method("POST", api_integration, **protected_method_options)

        upload = cme.add_resource("upload")
        upload.add_method("POST", api_integration, **protected_method_options)

        process = cme.add_resource("process")
        process.add_method("POST", api_integration, **protected_method_options)

        # ========== CloudWatch Dashboards ==========
        dashboard = cloudwatch.Dashboard(
            self, "CMEDashboard",
            dashboard_name="CME-Analysis-Platform"
        )

        # Add metrics to dashboard
        dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="API Requests",
                left=[api_lambda.metric_invocations()],
                width=12
            ),
            cloudwatch.GraphWidget(
                title="Processing Time",
                left=[nlp_lambda.metric_duration(), video_lambda.metric_duration()],
                width=12
            )
        )

        # ========== Step Functions Workflow ==========
        from step_function_workflow import create_cme_processing_workflow
        
        state_machine = create_cme_processing_workflow(
            self,
            transcription_waiter_lambda,
            nlp_lambda,
            video_lambda,
            report_lambda,
            sessions_table.table_name
        )
        
        # Grant Step Function permissions to invoke Lambdas
        transcription_waiter_lambda.grant_invoke(state_machine)
        nlp_lambda.grant_invoke(state_machine)
        video_lambda.grant_invoke(state_machine)
        report_lambda.grant_invoke(state_machine)
        
        # Grant Step Function DynamoDB access
        sessions_table.grant_read_write_data(state_machine)

        # Wire orchestration ARN into API handler (created above; token resolves at deploy)
        api_lambda.add_environment("STEP_FUNCTION_ARN", state_machine.state_machine_arn)
        
        # ========== Outputs ==========
        self.api_url = api.url
        self.user_pool_id = user_pool.user_pool_id
        self.user_pool_client_id = user_pool_client.user_pool_client_id
        self.bucket_name = cme_bucket.bucket_name
        self.state_machine_arn = state_machine.state_machine_arn
