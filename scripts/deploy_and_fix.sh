#!/bin/bash
# Deploy fixes and run full pipeline

set -e

echo "=========================================="
echo "🚀 DEPLOYING FIXES & RUNNING PIPELINE"
echo "=========================================="

SESSION_ID="cme_7285456d8748"
REGION="us-east-1"

# Step 1: Package Lambda functions
echo ""
echo "📦 Packaging Lambda functions..."
cd backend/lambda_functions
zip -q -r lambda_functions.zip *.py
cd ../..

# Step 2: Update Lambda functions
echo ""
echo "🔄 Updating Lambda functions..."

aws lambda update-function-code \
  --function-name cme-nlp-processor \
  --zip-file fileb://backend/lambda_functions/lambda_functions.zip \
  --region $REGION \
  --output json > /dev/null
echo "   ✅ cme-nlp-processor updated"

aws lambda update-function-code \
  --function-name cme-video-processor \
  --zip-file fileb://backend/lambda_functions/lambda_functions.zip \
  --region $REGION \
  --output json > /dev/null
echo "   ✅ cme-video-processor updated"

aws lambda update-function-code \
  --function-name cme-report-generator \
  --zip-file fileb://backend/lambda_functions/lambda_functions.zip \
  --region $REGION \
  --output json > /dev/null
echo "   ✅ cme-report-generator updated"

# Step 3: Wait for updates
echo ""
echo "⏳ Waiting for Lambda updates..."
sleep 10

# Step 4: Run validation and fix script
echo ""
echo "🔧 Running pipeline validation..."
python3 scripts/validate_and_fix_pipeline.py

# Step 5: Generate PDF
echo ""
echo "📄 Generating PDF report..."
python3 scripts/generate_pdf_from_html.py

echo ""
echo "✅ DONE!"
echo ""
echo "Check: cme_report_${SESSION_ID}.pdf"

