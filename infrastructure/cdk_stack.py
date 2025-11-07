"""
AWS CDK Infrastructure Stack for CME Analysis Platform
Deploys all required AWS resources for the Florida happy-path implementation
"""

from aws_cdk import (
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
    RemovalPolicy,
)
from constructs import Construct

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

        # Grant Transcribe access
        lambda_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "transcribe:StartMedicalTranscriptionJob",
                "transcribe:GetMedicalTranscriptionJob"
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

        # Main API Lambda
        api_lambda = lambda_.Function(
            self, "CMEAPIHandler",
            function_name="cme-api-handler",
            runtime=lambda_.Runtime.PYTHON_3_12,
            code=lambda_.Code.from_asset("../backend/lambda_functions"),
            handler="cme_handler.handler",
            timeout=Duration.seconds(30),
            memory_size=512,
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

        # NLP Processor Lambda
        nlp_lambda = lambda_.Function(
            self, "CMENLPProcessor",
            function_name="cme-nlp-processor",
            runtime=lambda_.Runtime.PYTHON_3_12,
            code=lambda_.Code.from_asset("../backend/lambda_functions"),
            handler="cme_nlp_processor.process_transcript_for_cme_analysis",
            timeout=Duration.minutes(5),
            memory_size=2048,
            role=lambda_role,
            environment={
                "CME_SESSIONS_TABLE": sessions_table.table_name,
                "CME_STEPS_TABLE": steps_table.table_name,
                "CME_DEMEANOR_TABLE": demeanor_table.table_name
            }
        )

        # Video Processor Lambda
        video_lambda = lambda_.Function(
            self, "CMEVideoProcessor",
            function_name="cme-video-processor",
            runtime=lambda_.Runtime.PYTHON_3_12,
            code=lambda_.Code.from_asset("../backend/lambda_functions"),
            handler="cme_video_processor.process_video_for_cme_test",
            timeout=Duration.minutes(15),
            memory_size=3008,
            ephemeral_storage_size=lambda_.Size.gibibytes(10),  # For video processing
            role=lambda_role,
            environment={
                "S3_BUCKET": cme_bucket.bucket_name,
                "CME_ACTIONS_TABLE": actions_table.table_name
            }
        )

        # Report Generator Lambda
        report_lambda = lambda_.Function(
            self, "CMEReportGenerator",
            function_name="cme-report-generator",
            runtime=lambda_.Runtime.PYTHON_3_12,
            code=lambda_.Code.from_asset("../backend/lambda_functions"),
            handler="cme_report_generator.generate_report",
            timeout=Duration.minutes(5),
            memory_size=1024,
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
                data_trace_enabled=True
            )
        )

        # API Integration
        api_integration = apigateway.LambdaIntegration(api_lambda)

        # API Resources
        cme = api.root.add_resource("cme")
        sessions = cme.add_resource("sessions")
        sessions.add_method("POST", api_integration)
        sessions.add_method("GET", api_integration)

        session_detail = sessions.add_resource("{session_id}")
        session_detail.add_method("GET", api_integration)

        report = session_detail.add_resource("report")
        report.add_method("GET", api_integration)

        consent = cme.add_resource("consent")
        consent.add_method("POST", api_integration)

        upload = cme.add_resource("upload")
        upload.add_method("POST", api_integration)

        process = cme.add_resource("process")
        process.add_method("POST", api_integration)

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

        # ========== Outputs ==========
        self.api_url = api.url
        self.user_pool_id = user_pool.user_pool_id
        self.user_pool_client_id = user_pool_client.user_pool_client_id
        self.bucket_name = cme_bucket.bucket_name


