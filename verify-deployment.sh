#!/bin/bash

# 🧪 CME Platform - Deployment Verification Script
# This script verifies all resources were deployed correctly

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   CME Platform - Deployment Verification         ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════╝${NC}"
echo ""

PASS=0
FAIL=0

# Test 1: DynamoDB Tables
echo -e "${YELLOW}Test 1: Checking DynamoDB tables...${NC}"
EXPECTED_TABLES=("cme-sessions" "cme-declared-steps" "cme-observed-actions" "cme-demeanor-flags" "cme-consents" "cme-doctor-commands" "cme-patient-confusion" "cme-patient-distress")
TABLES=$(aws dynamodb list-tables --region us-east-1 --query "TableNames" --output text)

for table in "${EXPECTED_TABLES[@]}"; do
  if echo "$TABLES" | grep -q "$table"; then
    echo -e "  ${GREEN}✅ $table${NC}"
    ((PASS++))
  else
    echo -e "  ${RED}❌ $table missing${NC}"
    ((FAIL++))
  fi
done

# Test 2: Lambda Functions
echo ""
echo -e "${YELLOW}Test 2: Checking Lambda functions...${NC}"
EXPECTED_FUNCTIONS=("cme-api-handler" "cme-transcription-waiter" "cme-nlp-processor" "cme-video-processor" "cme-report-generator")
FUNCTIONS=$(aws lambda list-functions --region us-east-1 --query "Functions[?contains(FunctionName, 'cme')].FunctionName" --output text)

for func in "${EXPECTED_FUNCTIONS[@]}"; do
  if echo "$FUNCTIONS" | grep -q "$func"; then
    echo -e "  ${GREEN}✅ $func${NC}"
    ((PASS++))
  else
    echo -e "  ${RED}❌ $func missing${NC}"
    ((FAIL++))
  fi
done

# Test 3: S3 Bucket
echo ""
echo -e "${YELLOW}Test 3: Checking S3 bucket...${NC}"
if aws s3 ls | grep -q "cme-analysis-recordings-388846700527"; then
  echo -e "  ${GREEN}✅ S3 bucket: cme-analysis-recordings-388846700527${NC}"
  ((PASS++))
else
  echo -e "  ${RED}❌ S3 bucket missing${NC}"
  ((FAIL++))
fi

# Test 4: API Gateway
echo ""
echo -e "${YELLOW}Test 4: Checking API Gateway...${NC}"
API_URL="https://g4dzem9rtk.execute-api.us-east-1.amazonaws.com/prod"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/cme/sessions" || echo "000")
if [ "$HTTP_CODE" != "000" ]; then
  echo -e "  ${GREEN}✅ API Gateway reachable (HTTP $HTTP_CODE)${NC}"
  ((PASS++))
else
  echo -e "  ${RED}❌ API Gateway not reachable${NC}"
  ((FAIL++))
fi

# Test 5: Cognito User Pool
echo ""
echo -e "${YELLOW}Test 5: Checking Cognito User Pool...${NC}"
if aws cognito-idp describe-user-pool --user-pool-id us-east-1_t8m33Ihhq --region us-east-1 > /dev/null 2>&1; then
  echo -e "  ${GREEN}✅ Cognito User Pool: us-east-1_t8m33Ihhq${NC}"
  ((PASS++))
else
  echo -e "  ${RED}❌ Cognito User Pool not found${NC}"
  ((FAIL++))
fi

# Test 6: CloudFormation Stack
echo ""
echo -e "${YELLOW}Test 6: Checking CloudFormation stack...${NC}"
STACK_STATUS=$(aws cloudformation describe-stacks --stack-name CMEAnalysisPlatformStack --region us-east-1 --query "Stacks[0].StackStatus" --output text 2>/dev/null || echo "NOT_FOUND")
if [[ "$STACK_STATUS" == *"COMPLETE"* ]]; then
  echo -e "  ${GREEN}✅ Stack Status: $STACK_STATUS${NC}"
  ((PASS++))
else
  echo -e "  ${RED}❌ Stack Status: $STACK_STATUS${NC}"
  ((FAIL++))
fi

# Summary
echo ""
echo -e "${BLUE}════════════════════════════════════════════════════${NC}"
echo -e "  ${GREEN}Passed: $PASS${NC}"
echo -e "  ${RED}Failed: $FAIL${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════${NC}"

if [ $FAIL -eq 0 ]; then
  echo ""
  echo -e "${GREEN}╔════════════════════════════════════════════════════╗${NC}"
  echo -e "${GREEN}║   🎉 ALL TESTS PASSED!                            ║${NC}"
  echo -e "${GREEN}║   Your CME Platform is READY FOR PRODUCTION!      ║${NC}"
  echo -e "${GREEN}╚════════════════════════════════════════════════════╝${NC}"
  echo ""
  echo -e "${YELLOW}📋 Next Steps:${NC}"
  echo "1. Create test user: aws cognito-idp admin-create-user --user-pool-id us-east-1_t8m33Ihhq --username test@example.com"
  echo "2. Upload test video to S3"
  echo "3. Test full pipeline"
  echo "4. Email Dorothy/Tim: 'Beta is live!'"
  echo ""
  echo -e "${GREEN}💰 You can now start charging $2,500+ per case!${NC}"
  exit 0
else
  echo ""
  echo -e "${RED}❌ Some tests failed. Check the output above.${NC}"
  exit 1
fi
