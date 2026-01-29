"""
AWS Step Functions workflow for CME processing orchestration
This orchestrates the complete pipeline from upload to report generation
"""

from aws_cdk import (
    Duration,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    aws_lambda as lambda_,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
)
from constructs import Construct


def create_cme_processing_workflow(
    scope: Construct,
    transcribe_waiter_lambda: lambda_.Function,
    nlp_processor_lambda: lambda_.Function,
    video_processor_lambda: lambda_.Function,
    report_generator_lambda: lambda_.Function,
    sessions_table_name: str
) -> sfn.StateMachine:
    """
    Create Step Function workflow for CME processing
    
    Pipeline:
    1. Start Transcription Job
    2. Wait for Transcription to Complete
    3. Run NLP Analysis (test detection + demeanor)
    4. Map over each detected test → Extract video segment + Analyze
    5. Generate Report
    6. Update Session Status
    """
    
    # Step 1: Start Transcription Job (already done by API handler)
    # This workflow starts AFTER transcription job is initiated
    
    # Step 2: Wait for Transcription Job to Complete
    wait_for_transcription = tasks.LambdaInvoke(
        scope, "WaitForTranscription",
        lambda_function=transcribe_waiter_lambda,
        payload=sfn.TaskInput.from_object({
            "session_id.$": "$.session_id",
            "transcription_job_name.$": "$.transcription_job_name"
        }),
        result_path="$.transcription_result",
        retry_on_service_exceptions=True,
    )
    
    # Add retry logic for transcription polling
    wait_for_transcription.add_retry(
        errors=["TranscriptionInProgress"],
        interval=Duration.seconds(30),
        max_attempts=40,  # 20 minutes max
        backoff_rate=1.0
    )
    
    # Step 3: Run NLP Analysis
    run_nlp_analysis = tasks.LambdaInvoke(
        scope, "RunNLPAnalysis",
        lambda_function=nlp_processor_lambda,
        payload=sfn.TaskInput.from_object({
            "session_id.$": "$.session_id",
            "transcript_uri.$": "$.transcription_result.Payload.transcript_uri"
        }),
        result_path="$.nlp_result"
    )
    
    # Step 4: Process Each Detected Test (Map State)
    process_single_test = tasks.LambdaInvoke(
        scope, "ProcessSingleTest",
        lambda_function=video_processor_lambda,
        payload=sfn.TaskInput.from_object({
            "session_id.$": "$.session_id",
            "declared_test.$": "$.test",
            "video_s3_key.$": "$.video_s3_key"
        }),
        result_path="$.video_result"
    )
    
    # Map over all detected tests
    process_all_tests = sfn.Map(
        scope, "ProcessAllTests",
        items_path="$.nlp_result.Payload.declared_tests",
        parameters={
            "session_id.$": "$.session_id",
            "video_s3_key.$": "$.video_s3_key",
            "test.$": "$$.Map.Item.Value"
        },
        max_concurrency=3,  # Process up to 3 tests in parallel
        result_path="$.all_test_results"
    )
    
    process_all_tests.iterator(process_single_test)
    
    # Step 5: Generate Report
    generate_report = tasks.LambdaInvoke(
        scope, "GenerateReport",
        lambda_function=report_generator_lambda,
        payload=sfn.TaskInput.from_object({
            "session_id.$": "$.session_id",
            "format": "html"
        }),
        result_path="$.report_result"
    )
    
    # Step 6: Update Session Status to Completed
    update_status = tasks.DynamoUpdateItem(
        scope, "UpdateSessionStatus",
        table_name=sessions_table_name,
        key={
            "session_id": tasks.DynamoAttributeValue.from_string(
                sfn.JsonPath.string_at("$.session_id")
            )
        },
        update_expression="SET #status = :completed, processing_stage = :stage, updated_at = :timestamp",
        expression_attribute_names={
            "#status": "status"
        },
        expression_attribute_values={
            ":completed": tasks.DynamoAttributeValue.from_string("completed"),
            ":stage": tasks.DynamoAttributeValue.from_string("report_generated"),
            ":timestamp": tasks.DynamoAttributeValue.from_number(
                sfn.JsonPath.number_at("$$.State.EnteredTime")
            )
        },
        result_path="$.update_result"
    )
    
    # Error handling state
    handle_error = sfn.Pass(
        scope, "HandleError",
        parameters={
            "error": "Processing failed",
            "cause.$": "$.cause"
        }
    )
    
    # Update status to error on failure
    mark_as_failed = tasks.DynamoUpdateItem(
        scope, "MarkSessionFailed",
        table_name=sessions_table_name,
        key={
            "session_id": tasks.DynamoAttributeValue.from_string(
                sfn.JsonPath.string_at("$.session_id")
            )
        },
        update_expression="SET #status = :error, processing_stage = :stage",
        expression_attribute_names={
            "#status": "status"
        },
        expression_attribute_values={
            ":error": tasks.DynamoAttributeValue.from_string("error"),
            ":stage": tasks.DynamoAttributeValue.from_string("failed")
        }
    )
    
    # Build the workflow chain
    definition = (
        wait_for_transcription
        .next(run_nlp_analysis)
        .next(process_all_tests)
        .next(generate_report)
        .next(update_status)
    )
    
    # Add error handling
    definition.add_catch(
        handle_error.next(mark_as_failed),
        errors=["States.ALL"],
        result_path="$.error"
    )
    
    # Create the state machine
    state_machine = sfn.StateMachine(
        scope, "CMEProcessingStateMachine",
        state_machine_name="cme-processing-pipeline",
        definition=definition,
        timeout=Duration.hours(2),  # Max 2 hours for entire pipeline
    )
    
    return state_machine


def create_transcription_completion_rule(
    scope: Construct,
    state_machine: sfn.StateMachine
) -> events.Rule:
    """
    Create EventBridge rule to trigger workflow when Transcribe job completes
    """
    
    rule = events.Rule(
        scope, "TranscriptionCompleteRule",
        rule_name="cme-transcription-complete",
        description="Trigger CME processing when transcription completes",
        event_pattern=events.EventPattern(
            source=["aws.transcribe"],
            detail_type=["Transcribe Job State Change"],
            detail={
                "TranscriptionJobStatus": ["COMPLETED"]
            }
        )
    )
    
    # Add Step Function as target
    rule.add_target(
        targets.SfnStateMachine(
            state_machine,
            input=events.RuleTargetInput.from_event_path("$.detail")
        )
    )
    
    return rule


def create_s3_upload_trigger(
    scope: Construct,
    bucket,
    trigger_lambda: lambda_.Function
) -> None:
    """
    Trigger processing when video is uploaded to S3
    """
    from aws_cdk import aws_s3_notifications as s3n
    
    # Trigger Lambda when video uploaded to cme-recordings/ prefix
    bucket.add_event_notification(
        s3.EventType.OBJECT_CREATED,
        s3n.LambdaDestination(trigger_lambda),
        s3.NotificationKeyFilter(prefix="cme-recordings/")
    )



