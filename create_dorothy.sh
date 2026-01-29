#!/bin/bash

echo "Creating Dorothy Sims user account..."
echo "Email: dcs@dorothyclaysims.com"
echo "Password: Abc12345!"
echo ""

# Create the user
echo "Step 1: Creating user..."
aws cognito-idp admin-create-user \
  --user-pool-id us-east-1_t8m33Ihhq \
  --username dcs@dorothyclaysims.com \
  --user-attributes Name=email,Value=dcs@dorothyclaysims.com Name=given_name,Value=Dorothy Name=family_name,Value=Simms \
  --temporary-password TempPass123! \
  --message-action SUPPRESS

if [ $? -eq 0 ]; then
    echo "✅ User created successfully"
else
    echo "⚠️  User might already exist, proceeding to password reset..."
fi

echo ""
echo "Step 2: Setting permanent password..."

# Set permanent password
aws cognito-idp admin-set-user-password \
  --user-pool-id us-east-1_t8m33Ihhq \
  --username dcs@dorothyclaysims.com \
  --password "Abc12345!" \
  --permanent

if [ $? -eq 0 ]; then
    echo ""
    echo "╔════════════════════════════════════════╗"
    echo "║  ✅ DOROTHY SIMS ACCOUNT READY!       ║"
    echo "╚════════════════════════════════════════╝"
    echo ""
    echo "🎯 Login Details:"
    echo "   URL: https://cme-analysis-platform-official.vercel.app"
    echo "   Email: dcs@dorothyclaysims.com"
    echo "   Password: Abc12345!"
    echo "   Name: Dorothy Sims"
    echo ""
    echo "🚀 Account is ready for Dorothy to login!"
else
    echo "❌ Failed to set password. Please check your AWS credentials."
    echo "Make sure you're logged in with: aws configure"
fi
