# CME Analysis Platform - Deployment Guide

## 🚀 Quick Start Deployment

This guide will help you deploy the CME Analysis Platform to AWS.

### Prerequisites

1. **AWS Account** with access to:
   - Lambda
   - DynamoDB
   - S3
   - API Gateway
   - Cognito
   - Transcribe Medical
   - Rekognition
   - Bedrock (Claude model access)
   - Step Functions

2. **Development Environment:**
   - Python 3.12+
   - Node.js 18+
   - AWS CLI configured
   - AWS CDK CLI (`npm install -g aws-cdk`)

3. **Bedrock Model Access:**
   - Request access to Claude 3 Sonnet in AWS Bedrock console
   - Navigate to: AWS Console → Bedrock → Model access → Request access

---

## Step 1: Clone and Setup

```bash
cd /Users/hammadhaque/Documents
cd cme-analysis-platform
```

---

## Step 2: Backend Setup

```bash
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Package Lambda functions
cd lambda_functions
zip -r lambda_function.zip *.py
cd ..
```

---

## Step 3: Infrastructure Deployment

```bash
cd ../infrastructure

# Install CDK dependencies
pip install -r requirements.txt

# Bootstrap CDK (first time only)
cdk bootstrap aws://ACCOUNT-ID/us-east-1

# Review infrastructure changes
cdk synth

# Deploy the stack
cdk deploy

# Note the outputs:
# - API Gateway URL
# - Cognito User Pool ID
# - Cognito Client ID
# - S3 Bucket Name
```

**Expected Output:**
```
Outputs:
CMEAnalysisPlatformStack.APIURL = https://xxxxx.execute-api.us-east-1.amazonaws.com/prod
CMEAnalysisPlatformStack.UserPoolId = us-east-1_xxxxx
CMEAnalysisPlatformStack.UserPoolClientId = xxxxx
CMEAnalysisPlatformStack.BucketName = cme-analysis-recordings-xxxxx
```

---

## Step 4: Configure Frontend

```bash
cd ../frontend

# Create environment file
cat > .env << EOF
REACT_APP_API_URL=https://xxxxx.execute-api.us-east-1.amazonaws.com/prod
REACT_APP_USER_POOL_ID=us-east-1_xxxxx
REACT_APP_USER_POOL_CLIENT_ID=xxxxx
REACT_APP_REGION=us-east-1
EOF

# Install dependencies
npm install

# Start development server
npm start
```

Visit `http://localhost:3000` to see the app running locally.

---

## Step 5: Create Admin User

```bash
# Create admin user in Cognito
aws cognito-idp admin-create-user \
  --user-pool-id us-east-1_xxxxx \
  --username admin@yourlawfirm.com \
  --user-attributes Name=email,Value=admin@yourlawfirm.com \
                    Name=given_name,Value=Admin \
                    Name=family_name,Value=User \
  --temporary-password TempPassword123! \
  --message-action SUPPRESS

# Set permanent password
aws cognito-idp admin-set-user-password \
  --user-pool-id us-east-1_xxxxx \
  --username admin@yourlawfirm.com \
  --password YourSecurePassword123! \
  --permanent
```

---

## Step 6: Production Frontend Deployment

### Option A: Deploy to AWS Amplify

```bash
# Install Amplify CLI
npm install -g @aws-amplify/cli

# Initialize Amplify
amplify init

# Add hosting
amplify add hosting

# Publish
amplify publish
```

### Option B: Deploy to Vercel

```bash
# Install Vercel CLI
npm install -g vercel

# Deploy
cd frontend
vercel --prod

# Set environment variables in Vercel dashboard
```

### Option C: Deploy to S3 + CloudFront

```bash
cd frontend

# Build for production
npm run build

# Upload to S3
aws s3 sync build/ s3://your-cme-frontend-bucket/ --delete

# Invalidate CloudFront cache
aws cloudfront create-invalidation \
  --distribution-id DISTRIBUTION_ID \
  --paths "/*"
```

---

## Step 7: Configure FFmpeg for Video Processing

For video segmentation, Lambda needs FFmpeg. Two options:

### Option A: Use Lambda Layer

```bash
# Create FFmpeg layer
cd /tmp
wget https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz
tar xf ffmpeg-release-amd64-static.tar.xz
mkdir -p ffmpeg-layer/bin
cp ffmpeg-*-amd64-static/ffmpeg ffmpeg-layer/bin/
cd ffmpeg-layer
zip -r ../ffmpeg-layer.zip .

# Upload as Lambda layer
aws lambda publish-layer-version \
  --layer-name ffmpeg \
  --zip-file fileb:///tmp/ffmpeg-layer.zip \
  --compatible-runtimes python3.12

# Add layer to video processor Lambda
aws lambda update-function-configuration \
  --function-name cme-video-processor \
  --layers arn:aws:lambda:REGION:ACCOUNT:layer:ffmpeg:1
```

### Option B: Use AWS MediaConvert

Update `cme_video_processor.py` to use MediaConvert instead of FFmpeg.

---

## Step 8: Test the System

### Test Session Creation

```bash
curl -X POST https://your-api-url/cme/sessions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "patient_id": "PT001",
    "patient_name": "John Doe",
    "doctor_name": "Dr. Smith",
    "state": "FL",
    "exam_date": "2025-01-15",
    "attorney_name": "Dorothy Clay Sims"
  }'
```

### Test Upload Flow

1. Create session → Get session_id
2. Get upload URL → Upload video file
3. Start processing → Monitor status
4. Generate report → Download PDF/HTML

---

## Step 9: Monitoring & Logging

### View Logs

```bash
# API Lambda logs
aws logs tail /aws/lambda/cme-api-handler --follow

# NLP Processor logs
aws logs tail /aws/lambda/cme-nlp-processor --follow

# Video Processor logs
aws logs tail /aws/lambda/cme-video-processor --follow
```

### CloudWatch Dashboard

Visit: AWS Console → CloudWatch → Dashboards → CME-Analysis-Platform

Monitor:
- API request rates
- Processing times
- Error rates
- DynamoDB throughput

---

## Step 10: Security Hardening

### Enable WAF (Web Application Firewall)

```bash
# Create WAF web ACL for API Gateway
aws wafv2 create-web-acl \
  --name cme-api-waf \
  --scope REGIONAL \
  --default-action Allow={} \
  --rules file://waf-rules.json
```

### Enable CloudTrail

```bash
# Enable audit logging
aws cloudtrail create-trail \
  --name cme-audit-trail \
  --s3-bucket-name your-audit-bucket
```

### Rotate Secrets

Set up automatic rotation for:
- Cognito client secrets
- Database encryption keys
- API keys

---

## Production Checklist

- [ ] All Lambda functions deployed
- [ ] DynamoDB tables created with encryption
- [ ] S3 bucket configured with encryption
- [ ] Cognito user pool created
- [ ] API Gateway deployed
- [ ] CloudWatch alarms configured
- [ ] WAF rules applied
- [ ] CloudTrail enabled
- [ ] Admin users created
- [ ] Frontend deployed
- [ ] SSL/TLS certificates configured
- [ ] DNS records updated
- [ ] Backup policies configured
- [ ] Data retention policies set
- [ ] Compliance review completed

---

## Cost Estimates

### Small Law Firm (10 CMEs/month):
- Lambda: ~$20/month
- S3 Storage: ~$50/month (depends on recording storage)
- DynamoDB: ~$10/month
- Transcribe: ~$15/month
- Bedrock: ~$30/month
- **Total: ~$125/month**

### Medium Firm (50 CMEs/month):
- Lambda: ~$80/month
- S3 Storage: ~$200/month
- DynamoDB: ~$25/month
- Transcribe: ~$75/month
- Bedrock: ~$120/month
- **Total: ~$500/month**

---

## Troubleshooting

### Issue: Lambda Timeout on Video Processing

**Solution:** Increase timeout and memory:
```bash
aws lambda update-function-configuration \
  --function-name cme-video-processor \
  --timeout 900 \
  --memory-size 3008
```

### Issue: Transcribe Job Fails

**Solution:** Check IAM permissions and S3 bucket policy.

### Issue: Out of Memory

**Solution:** Increase Lambda memory or use streaming processing.

---

## Support & Maintenance

### Daily:
- Monitor CloudWatch metrics
- Check error logs

### Weekly:
- Review cost reports
- Update dependencies if needed

### Monthly:
- Backup DynamoDB tables
- Rotate access keys
- Review security logs

---

## Rollback Procedure

If deployment fails:

```bash
# Rollback CDK stack
cdk deploy --rollback

# Restore from backup
aws dynamodb restore-table-from-backup \
  --target-table-name cme-sessions \
  --backup-arn arn:aws:dynamodb:...
```

---

## Next Steps

1. **Customize for Your Firm:** Add firm branding to frontend
2. **Integrate with Case Management:** Connect to existing systems
3. **Set Up Alerts:** Configure SNS notifications for processing completion
4. **Train Staff:** Provide training on using the platform
5. **Legal Review:** Ensure compliance with state-specific laws

---

## Resources

- [AWS CDK Documentation](https://docs.aws.amazon.com/cdk/)
- [AWS Transcribe Medical](https://docs.aws.amazon.com/transcribe/latest/dg/transcribe-medical.html)
- [AWS Bedrock](https://docs.aws.amazon.com/bedrock/)
- [Florida Rule 1.360](https://www.floridasupremecourt.org/Rules-of-Procedure)

---

**Deployed and maintained with ❤️ for plaintiff attorneys**


