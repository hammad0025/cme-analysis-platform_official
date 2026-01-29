# 🚀 CME PLATFORM - DEPLOYMENT GUIDE (WEEK 1)

## ✅ **GOAL: Deploy Infrastructure to AWS in 5-7 Days**

This guide will get your CME software **LIVE and SELLABLE**.

---

## 📋 **PRE-DEPLOYMENT CHECKLIST**

### **Step 1: Prerequisites** (30 minutes)

```bash
# 1. Check AWS CLI is installed
aws --version
# Should show: aws-cli/2.x.x

# 2. Check AWS credentials are configured
aws sts get-caller-identity
# Should show your AWS account ID

# 3. Check Python version
python3 --version
# Need: Python 3.11 or higher

# 4. Check Node.js (for CDK)
node --version
# Need: v18+ 

# 5. Install AWS CDK
npm install -g aws-cdk
cdk --version
# Should show: 2.x.x
```

**If anything is missing, install it first:**

```bash
# Install AWS CLI (Mac):
brew install awscli

# Install AWS CLI (Windows):
# Download from: https://aws.amazon.com/cli/

# Configure AWS credentials:
aws configure
# Enter:
#   AWS Access Key ID: [your key]
#   AWS Secret Access Key: [your secret]
#   Default region: us-east-1
#   Default output format: json

# Install CDK:
npm install -g aws-cdk

# Verify everything:
aws sts get-caller-identity
cdk --version
```

---

## 🎯 **DAY 1: CDK Bootstrap & Setup** (2-3 hours)

### **Step 1: Bootstrap CDK**

```bash
cd /Users/hammadhaque/Documents/cme-analysis-platform/infrastructure

# Bootstrap CDK (only needed once per AWS account)
cdk bootstrap aws://ACCOUNT-ID/us-east-1

# Replace ACCOUNT-ID with your actual account ID from:
aws sts get-caller-identity
```

### **Step 2: Install Python Dependencies**

```bash
# Install CDK dependencies
pip install -r requirements.txt

# Verify installation
python3 -c "import aws_cdk; print('CDK installed')"
```

### **Step 3: Synthesize CloudFormation Template** (TEST)

```bash
# This generates CloudFormation template without deploying
cdk synth

# Should output a YAML template
# If you see errors, fix them before deploying
```

**Common Errors:**
- Missing imports: `pip install aws-cdk-lib constructs`
- Wrong Python version: Use Python 3.11+
- AWS credentials: Run `aws configure`

---

## 🚀 **DAY 2: Deploy Infrastructure** (3-4 hours)

### **Step 1: Review What Will Be Created**

```bash
# See what resources will be created
cdk diff
```

This will create:
- ✅ 8 DynamoDB tables
- ✅ 1 S3 bucket
- ✅ 5 Lambda functions
- ✅ 1 API Gateway
- ✅ 1 Cognito User Pool
- ✅ 1 Step Functions workflow
- ✅ IAM roles and policies
- ✅ CloudWatch dashboard

**Estimated Cost:** $5-10/month with no usage, $2-3 per video processed

### **Step 2: DEPLOY!** 🎉

```bash
cd /Users/hammadhaque/Documents/cme-analysis-platform/infrastructure

# Deploy everything
cdk deploy

# Say 'y' when asked to approve IAM changes
# This will take 10-15 minutes
```

**What happens:**
1. Creates DynamoDB tables (2 min)
2. Creates S3 bucket (1 min)
3. Packages Lambda functions (3 min)
4. Creates Lambda functions (5 min)
5. Creates API Gateway (2 min)
6. Creates Cognito (1 min)
7. Creates Step Functions (1 min)

**Watch for:**
- Green text = success
- Yellow text = in progress
- Red text = error (read carefully!)

### **Step 3: Save Output Values** 🚨 **IMPORTANT**

After deployment, you'll see output like:

```
Outputs:
CMEAnalysisPlatformStack.APIURL = https://xxxxx.execute-api.us-east-1.amazonaws.com/prod/
CMEAnalysisPlatformStack.UserPoolId = us-east-1_xxxxxx
CMEAnalysisPlatformStack.UserPoolClientId = xxxxxxxxxxxxxx
CMEAnalysisPlatformStack.BucketName = cme-analysis-recordings-xxxxx
CMEAnalysisPlatformStack.StateMachineArn = arn:aws:states:us-east-1:xxx
```

**SAVE THESE!** Write them down or copy to a file.

---

## 🧪 **DAY 3: Verify Deployment** (2-3 hours)

### **Step 1: Check DynamoDB Tables**

```bash
# List all tables
aws dynamodb list-tables

# Should see:
# - cme-sessions
# - cme-declared-steps
# - cme-observed-actions
# - cme-demeanor-flags
# - cme-consents
# - cme-doctor-commands (NEW!)
# - cme-patient-confusion (NEW!)
# - cme-patient-distress (NEW!)
```

### **Step 2: Check S3 Bucket**

```bash
# List buckets
aws s3 ls | grep cme-analysis

# Should see: cme-analysis-recordings-[your-account-id]
```

### **Step 3: Check Lambda Functions**

```bash
# List functions
aws lambda list-functions --query "Functions[?contains(FunctionName, 'cme')].FunctionName"

# Should see:
# - cme-api-handler
# - cme-transcription-waiter
# - cme-nlp-processor
# - cme-video-processor
# - cme-report-generator
```

### **Step 4: Test API Gateway**

```bash
# Get API URL from deployment outputs
API_URL="https://xxxxx.execute-api.us-east-1.amazonaws.com/prod"

# Test health check (if you have one)
curl $API_URL/cme/sessions

# Should return something (even if auth error, means API is live!)
```

---

## 🎯 **DAY 4: Test Lambda Functions** (3-4 hours)

### **Step 1: Test API Handler**

```bash
# Create test event
cat > test-create-session.json <<EOF
{
  "httpMethod": "POST",
  "path": "/cme/sessions",
  "body": "{\"patient_name\":\"Test Patient\",\"doctor_name\":\"Test Doctor\",\"state\":\"FL\",\"exam_date\":\"2025-01-01\"}"
}
EOF

# Invoke Lambda
aws lambda invoke \
  --function-name cme-api-handler \
  --payload file://test-create-session.json \
  response.json

# Check response
cat response.json

# Should see: {"statusCode": 200, "session_id": "cme_xxxxx"}
```

### **Step 2: Test NLP Processor** (Manual for now)

We'll test this with a real video later. For now, verify it exists:

```bash
aws lambda get-function --function-name cme-nlp-processor
# Should show function configuration
```

### **Step 3: Verify All Functions Are Deployed**

```bash
# Check function sizes
aws lambda list-functions \
  --query "Functions[?contains(FunctionName, 'cme')].[FunctionName,CodeSize]" \
  --output table

# All should show CodeSize > 0
```

---

## 📦 **DAY 5: Prepare for Testing** (2-3 hours)

### **Step 1: Create Test User in Cognito**

```bash
# Get User Pool ID from deployment outputs
USER_POOL_ID="us-east-1_xxxxxx"

# Create admin user
aws cognito-idp admin-create-user \
  --user-pool-id $USER_POOL_ID \
  --username dorothy@example.com \
  --user-attributes Name=email,Value=dorothy@example.com \
                     Name=given_name,Value=Dorothy \
                     Name=family_name,Value=Sims \
  --temporary-password "TempPassword123!" \
  --message-action SUPPRESS

# Set permanent password
aws cognito-idp admin-set-user-password \
  --user-pool-id $USER_POOL_ID \
  --username dorothy@example.com \
  --password "YourSecurePassword123!" \
  --permanent
```

### **Step 2: Create Environment File for Testing**

```bash
cd /Users/hammadhaque/Documents/cme-analysis-platform

cat > .env.test <<EOF
# AWS Configuration
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# API Configuration
API_URL=https://xxxxx.execute-api.us-east-1.amazonaws.com/prod

# DynamoDB Tables
CME_SESSIONS_TABLE=cme-sessions
CME_STEPS_TABLE=cme-declared-steps
CME_ACTIONS_TABLE=cme-observed-actions
CME_DEMEANOR_TABLE=cme-demeanor-flags
CME_CONSENT_TABLE=cme-consents
CME_COMMANDS_TABLE=cme-doctor-commands
CME_CONFUSION_TABLE=cme-patient-confusion
CME_DISTRESS_TABLE=cme-patient-distress

# S3 Bucket
S3_BUCKET=cme-analysis-recordings-$(aws sts get-caller-identity --query Account --output text)

# Cognito
USER_POOL_ID=us-east-1_xxxxxx
USER_POOL_CLIENT_ID=xxxxxxxxxxxxxx

EOF

echo "✅ Environment file created: .env.test"
```

### **Step 3: Create Quick Test Script**

```bash
cat > test-infrastructure.sh <<'EOF'
#!/bin/bash

echo "🧪 Testing CME Infrastructure..."
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

# Test 1: DynamoDB Tables
echo "Test 1: Checking DynamoDB tables..."
TABLES=$(aws dynamodb list-tables --query "TableNames" --output text)
if echo "$TABLES" | grep -q "cme-sessions"; then
  echo -e "${GREEN}✅ DynamoDB tables exist${NC}"
else
  echo -e "${RED}❌ DynamoDB tables missing${NC}"
  exit 1
fi

# Test 2: S3 Bucket
echo ""
echo "Test 2: Checking S3 bucket..."
BUCKETS=$(aws s3 ls | grep cme-analysis)
if [ -n "$BUCKETS" ]; then
  echo -e "${GREEN}✅ S3 bucket exists${NC}"
else
  echo -e "${RED}❌ S3 bucket missing${NC}"
  exit 1
fi

# Test 3: Lambda Functions
echo ""
echo "Test 3: Checking Lambda functions..."
FUNCTIONS=$(aws lambda list-functions --query "Functions[?contains(FunctionName, 'cme')].FunctionName" --output text)
FUNCTION_COUNT=$(echo "$FUNCTIONS" | wc -w)
if [ "$FUNCTION_COUNT" -ge 5 ]; then
  echo -e "${GREEN}✅ All Lambda functions deployed ($FUNCTION_COUNT found)${NC}"
else
  echo -e "${RED}❌ Missing Lambda functions (found $FUNCTION_COUNT, need 5)${NC}"
  exit 1
fi

# Test 4: API Gateway
echo ""
echo "Test 4: Checking API Gateway..."
APIS=$(aws apigateway get-rest-apis --query "items[?name=='CME Analysis API'].id" --output text)
if [ -n "$APIS" ]; then
  echo -e "${GREEN}✅ API Gateway deployed${NC}"
else
  echo -e "${RED}❌ API Gateway missing${NC}"
  exit 1
fi

# Test 5: Cognito User Pool
echo ""
echo "Test 5: Checking Cognito User Pool..."
POOLS=$(aws cognito-idp list-user-pools --max-results 10 --query "UserPools[?Name=='cme-analysis-users'].Id" --output text)
if [ -n "$POOLS" ]; then
  echo -e "${GREEN}✅ Cognito User Pool exists${NC}"
else
  echo -e "${RED}❌ Cognito User Pool missing${NC}"
  exit 1
fi

echo ""
echo -e "${GREEN}🎉 All infrastructure tests passed!${NC}"
echo ""
echo "Next step: Test with a real CME video"

EOF

chmod +x test-infrastructure.sh
./test-infrastructure.sh
```

---

## 🎉 **DAY 6-7: FINAL TESTING** (4-6 hours)

### **Comprehensive Test with Sample Video**

We'll create a detailed testing guide after infrastructure is deployed.

**You'll test:**
1. Upload a sample video
2. Trigger transcription
3. Run NLP analysis
4. Run video analysis
5. Generate report
6. Download and review

---

## 🚨 **TROUBLESHOOTING**

### **Common Issues:**

#### **1. CDK Deploy Fails - IAM Permissions**
```bash
# Error: User not authorized to perform: iam:CreateRole

# Solution: Your AWS user needs admin permissions
# Ask AWS account owner to grant AdministratorAccess policy
```

#### **2. Lambda Function Too Large**
```bash
# Error: Unzipped size must be smaller than...

# Solution: Optimize dependencies
cd backend/lambda_functions
pip install --target ./package -r requirements.txt
# Remove unnecessary files from package
```

#### **3. API Gateway 502 Error**
```bash
# Check Lambda logs
aws logs tail /aws/lambda/cme-api-handler --follow

# Common cause: Environment variables not set
# Fix: Redeploy with correct env vars
```

#### **4. DynamoDB Access Denied**
```bash
# Check Lambda role has permissions
aws iam get-role-policy \
  --role-name CMEAnalysisPlatformStack-CMELambdaRole \
  --policy-name default

# Should show DynamoDB permissions
```

---

## ✅ **DEPLOYMENT COMPLETE CHECKLIST**

After completing Days 1-7, you should have:

```
□ CDK bootstrapped
□ Infrastructure deployed (15-20 min deploy time)
□ All 8 DynamoDB tables created
□ S3 bucket created
□ All 5 Lambda functions deployed
□ API Gateway created and accessible
□ Cognito User Pool created
□ Test user created
□ All infrastructure tests passing
□ Ready for end-to-end testing with real video
```

---

## 📊 **DEPLOYMENT STATUS DASHBOARD**

Keep track of your progress:

```
Day 1: □ Prerequisites installed
        □ CDK bootstrapped
        □ Dependencies installed
        
Day 2: □ Infrastructure deployed
        □ Output values saved
        
Day 3: □ DynamoDB verified
        □ S3 verified
        □ Lambda verified
        □ API verified
        
Day 4: □ Lambda functions tested
        □ API handler working
        
Day 5: □ Test user created
        □ Environment configured
        □ Test scripts created
        
Day 6-7: □ End-to-end test passed
         □ Sample report generated
```

---

## 🚀 **NEXT STEPS AFTER DEPLOYMENT:**

Once infrastructure is live:

**Week 2:**
1. Complete frontend integration
2. Test with 2-3 real CME videos
3. Fix any bugs found
4. Generate sample reports for Dorothy/Tim

**Week 3:**
5. Beta launch to 5-10 attorneys
6. Collect feedback
7. Iterate quickly

**Week 4:**
8. Full launch
9. Start charging!

---

## 💰 **ESTIMATED AWS COSTS**

**Infrastructure (always on):**
- DynamoDB (on-demand): ~$1-2/month
- S3 storage: ~$1/month
- Lambda (idle): $0
- API Gateway: $0 (under free tier)
- Cognito: $0 (under 50K users)
- CloudWatch: ~$1-2/month
- **Total idle:** ~$3-5/month

**Per video processing:**
- Transcribe: $1.44/hour
- Rekognition: ~$1/hour
- Lambda execution: ~$0.50
- S3 storage: ~$0.05
- **Total per video:** ~$2-3

**At 10 videos/month:** $20-30/month total  
**At 100 videos/month:** $200-300/month total

---

## 🎯 **SUCCESS CRITERIA**

You're ready to sell when:
✅ Can upload a video
✅ Transcription completes
✅ Analysis runs automatically
✅ Report generates
✅ Can download report
✅ Process takes < 2 hours
✅ No critical errors

---

**🚀 START DEPLOYING NOW!**

```bash
cd /Users/hammadhaque/Documents/cme-analysis-platform/infrastructure
cdk deploy
```

**Questions? Check:**
- AWS CloudWatch Logs for errors
- CDK documentation: https://docs.aws.amazon.com/cdk/
- This guide's troubleshooting section
