#!/bin/bash

# Change password for shaque025@gmail.com to EasyPass123!

echo "Changing password for shaque025@gmail.com to EasyPass123!..."

aws cognito-idp admin-set-user-password \
  --user-pool-id us-east-1_t8m33Ihhq \
  --username shaque025@gmail.com \
  --password "EasyPass123!" \
  --permanent

if [ $? -eq 0 ]; then
    echo ""
    echo "╔════════════════════════════════════════╗"
    echo "║  ✅ PASSWORD CHANGED SUCCESSFULLY!    ║"
    echo "╚════════════════════════════════════════╝"
    echo ""
    echo "Login at: https://cme-analysis-platform-official.vercel.app"
    echo ""
    echo "Email:    shaque025@gmail.com"
    echo "Password: EasyPass123!"
    echo ""
else
    echo "❌ Error changing password"
fi
