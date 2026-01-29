#!/bin/bash

# Add Dorothy Sims user to CME Platform

echo "Creating account for Dorothy Sims (dcs@dorothyclaysims.com)..."

aws cognito-idp admin-create-user \
  --user-pool-id us-east-1_t8m33Ihhq \
  --username dcs@dorothyclaysims.com \
  --user-attributes \
    Name=email,Value=dcs@dorothyclaysims.com \
    Name=given_name,Value=Dorothy \
    Name=family_name,Value=Simms \
  --temporary-password TempPass123! \
  --message-action SUPPRESS

if [ $? -eq 0 ]; then
    echo "✅ User created successfully"

    echo "Setting permanent password..."

    aws cognito-idp admin-set-user-password \
      --user-pool-id us-east-1_t8m33Ihhq \
      --username dcs@dorothyclaysims.com \
      --password "Abc12345!" \
      --permanent

    if [ $? -eq 0 ]; then
        echo ""
        echo "╔════════════════════════════════════════╗"
        echo "║  ✅ DOROTHY SIMS ACCOUNT CREATED!     ║"
        echo "╚════════════════════════════════════════╝"
        echo ""
        echo "Login at: https://cme-analysis-platform-official.vercel.app"
        echo ""
        echo "Email:    dcs@dorothyclaysims.com"
        echo "Password: Abc12345!"
        echo ""
        echo "Name:     Dorothy Sims"
        echo ""
    else
        echo "❌ Error setting password"
    fi
else
    echo "❌ Error creating user (user might already exist)"
    echo "Trying to just reset password..."

    aws cognito-idp admin-set-user-password \
      --user-pool-id us-east-1_t8m33Ihhq \
      --username dcs@dorothyclaysims.com \
      --password "Abc12345!" \
      --permanent

    echo ""
    echo "✅ Password reset complete"
    echo "Login at: https://cme-analysis-platform-official.vercel.app"
    echo "Email:    dcs@dorothyclaysims.com"
    echo "Password: Abc12345!"
    echo "Name:     Dorothy Sims"
fi
