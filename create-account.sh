#!/bin/bash

# Create CME Platform Account

echo "Creating account for shaque025@gmail.com..."

aws cognito-idp admin-create-user \
  --user-pool-id us-east-1_t8m33Ihhq \
  --username shaque025@gmail.com \
  --user-attributes Name=email,Value=shaque025@gmail.com Name=given_name,Value=Hammad Name=family_name,Value=Haque \
  --temporary-password CMEAdmin2025! \
  --message-action SUPPRESS

if [ $? -eq 0 ]; then
    echo "✅ User created successfully"
    
    echo "Setting permanent password..."
    
    aws cognito-idp admin-set-user-password \
      --user-pool-id us-east-1_t8m33Ihhq \
      --username shaque025@gmail.com \
      --password HammadPass123! \
      --permanent
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "╔════════════════════════════════════════╗"
        echo "║  ✅ ACCOUNT CREATED SUCCESSFULLY!     ║"
        echo "╚════════════════════════════════════════╝"
        echo ""
        echo "Login at: https://cme-analysis-platform-official.vercel.app"
        echo ""
        echo "Email:    shaque025@gmail.com"
        echo "Password: EasyPass123!"
        echo ""
    else
        echo "❌ Error setting password"
    fi
else
    echo "❌ Error creating user (user might already exist)"
    echo "Trying to just reset password..."
    
    aws cognito-idp admin-set-user-password \
      --user-pool-id us-east-1_t8m33Ihhq \
      --username shaque025@gmail.com \
      --password HammadPass123! \
      --permanent
    
    echo ""
    echo "✅ Password reset complete"
    echo "Login at: https://cme-analysis-platform-official.vercel.app"
    echo "Email:    shaque025@gmail.com"
    echo "Password: EasyPass123!"
fi








