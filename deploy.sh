#!/bin/bash

# 🚀 CME Platform - One-Click Deployment Script
# This script deploys the entire infrastructure to AWS

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   CME Analysis Platform - Deployment Script      ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════╝${NC}"
echo ""

# Check prerequisites
echo -e "${YELLOW}📋 Checking prerequisites...${NC}"

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    echo -e "${RED}❌ AWS CLI not found. Please install it first.${NC}"
    exit 1
fi
echo -e "${GREEN}✅ AWS CLI installed${NC}"

# Check AWS credentials
if ! aws sts get-caller-identity &> /dev/null; then
    echo -e "${RED}❌ AWS credentials not configured. Run: aws configure${NC}"
    exit 1
fi
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo -e "${GREEN}✅ AWS credentials configured (Account: $ACCOUNT_ID)${NC}"

# Check CDK
if ! command -v cdk &> /dev/null; then
    echo -e "${RED}❌ AWS CDK not found. Installing...${NC}"
    npm install -g aws-cdk
fi
echo -e "${GREEN}✅ AWS CDK installed${NC}"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 not found. Please install it first.${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Python 3 installed${NC}"

echo ""
echo -e "${YELLOW}🔧 Setting up infrastructure...${NC}"

# Navigate to infrastructure directory
cd infrastructure

# Install Python dependencies
echo -e "${BLUE}Installing Python dependencies...${NC}"
pip3 install -r requirements.txt -q

# Bootstrap CDK (if not already done)
echo -e "${BLUE}Bootstrapping CDK...${NC}"
cdk bootstrap aws://$ACCOUNT_ID/us-east-1 2>/dev/null || echo "CDK already bootstrapped"

# Synthesize CloudFormation template
echo -e "${BLUE}Generating CloudFormation template...${NC}"
cdk synth > /dev/null

echo ""
echo -e "${YELLOW}🚀 Ready to deploy!${NC}"
echo ""
echo -e "${BLUE}This will create:${NC}"
echo "  • 8 DynamoDB tables"
echo "  • 1 S3 bucket"
echo "  • 5 Lambda functions"
echo "  • 1 API Gateway"
echo "  • 1 Cognito User Pool"
echo "  • 1 Step Functions workflow"
echo "  • IAM roles and policies"
echo ""
echo -e "${YELLOW}Estimated cost: $3-5/month idle, ~$2-3 per video processed${NC}"
echo ""

read -p "Deploy infrastructure now? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Deployment cancelled.${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}🚀 Deploying infrastructure... (this will take 10-15 minutes)${NC}"
echo ""

# Deploy
cdk deploy --require-approval never

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   🎉 DEPLOYMENT SUCCESSFUL!                       ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════╝${NC}"
echo ""

# Get outputs
echo -e "${BLUE}📊 Deployment Outputs:${NC}"
echo ""

API_URL=$(aws cloudformation describe-stacks \
  --stack-name CMEAnalysisPlatformStack \
  --query "Stacks[0].Outputs[?OutputKey=='APIURL'].OutputValue" \
  --output text 2>/dev/null || echo "Not found")

USER_POOL_ID=$(aws cloudformation describe-stacks \
  --stack-name CMEAnalysisPlatformStack \
  --query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" \
  --output text 2>/dev/null || echo "Not found")

BUCKET_NAME=$(aws cloudformation describe-stacks \
  --stack-name CMEAnalysisPlatformStack \
  --query "Stacks[0].Outputs[?OutputKey=='BucketName'].OutputValue" \
  --output text 2>/dev/null || echo "Not found")

echo "API URL: $API_URL"
echo "User Pool ID: $USER_POOL_ID"
echo "Bucket Name: $BUCKET_NAME"

# Save to .env file
cd ..
cat > .env.production <<EOF
# CME Platform - Production Environment
# Generated: $(date)

AWS_REGION=us-east-1
AWS_ACCOUNT_ID=$ACCOUNT_ID

API_URL=$API_URL
USER_POOL_ID=$USER_POOL_ID
BUCKET_NAME=$BUCKET_NAME

CME_SESSIONS_TABLE=cme-sessions
CME_STEPS_TABLE=cme-declared-steps
CME_ACTIONS_TABLE=cme-observed-actions
CME_DEMEANOR_TABLE=cme-demeanor-flags
CME_CONSENT_TABLE=cme-consents
CME_COMMANDS_TABLE=cme-doctor-commands
CME_CONFUSION_TABLE=cme-patient-confusion
CME_DISTRESS_TABLE=cme-patient-distress
EOF

echo ""
echo -e "${GREEN}✅ Environment file saved: .env.production${NC}"
echo ""

echo -e "${BLUE}📝 Next Steps:${NC}"
echo "1. Run: ./test-infrastructure.sh (to verify deployment)"
echo "2. Create test user: see DEPLOYMENT_GUIDE.md"
echo "3. Test with sample video"
echo "4. Launch beta program!"
echo ""
echo -e "${GREEN}🎯 You're ready to start processing CME videos!${NC}"
