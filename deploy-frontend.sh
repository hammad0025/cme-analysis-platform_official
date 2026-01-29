#!/bin/bash

# CME Analysis Platform - Frontend Deployment Script
# This script helps deploy the frontend to Vercel

set -e

echo "🚀 CME Analysis Platform - Frontend Deployment"
echo "================================================"
echo ""

# Check if we're in the right directory
if [ ! -f "frontend/package.json" ]; then
    echo "❌ Error: Must run from project root directory"
    exit 1
fi

cd frontend

# Check if Vercel CLI is installed
if ! command -v vercel &> /dev/null; then
    echo "📦 Installing Vercel CLI..."
    npm install -g vercel
fi

echo ""
echo "📋 Current Configuration:"
echo "   API URL: ${REACT_APP_API_URL:-https://g4dzem9rtk.execute-api.us-east-1.amazonaws.com/prod}"
echo "   User Pool ID: ${REACT_APP_USER_POOL_ID:-us-east-1_t8m33Ihhq}"
echo "   Client ID: ${REACT_APP_USER_POOL_WEB_CLIENT_ID:-42e444v111efsa21b6b3v09svp}"
echo ""

# Prompt for environment variables if not set
if [ -z "$REACT_APP_API_URL" ]; then
    read -p "Enter API URL (or press Enter for default): " api_url
    REACT_APP_API_URL=${api_url:-https://g4dzem9rtk.execute-api.us-east-1.amazonaws.com/prod}
fi

if [ -z "$REACT_APP_USER_POOL_ID" ]; then
    read -p "Enter User Pool ID (or press Enter for default): " pool_id
    REACT_APP_USER_POOL_ID=${pool_id:-us-east-1_t8m33Ihhq}
fi

if [ -z "$REACT_APP_USER_POOL_WEB_CLIENT_ID" ]; then
    read -p "Enter Client ID (or press Enter for default): " client_id
    REACT_APP_USER_POOL_WEB_CLIENT_ID=${client_id:-42e444v111efsa21b6b3v09svp}
fi

echo ""
echo "🔐 Setting up Vercel environment variables..."

# Login to Vercel if not already logged in
if ! vercel whoami &> /dev/null; then
    echo "Please login to Vercel..."
    vercel login
fi

# Set environment variables
echo "Setting REACT_APP_API_URL..."
echo "$REACT_APP_API_URL" | vercel env add REACT_APP_API_URL production

echo "Setting REACT_APP_USER_POOL_ID..."
echo "$REACT_APP_USER_POOL_ID" | vercel env add REACT_APP_USER_POOL_ID production

echo "Setting REACT_APP_USER_POOL_WEB_CLIENT_ID..."
echo "$REACT_APP_USER_POOL_WEB_CLIENT_ID" | vercel env add REACT_APP_USER_POOL_WEB_CLIENT_ID production

echo ""
echo "🚀 Deploying to Vercel..."
vercel --prod

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📝 Next steps:"
echo "   1. Visit your Vercel dashboard to get your deployment URL"
echo "   2. Test login with a test user"
echo "   3. Verify API calls work"
echo ""
echo "📚 For more details, see FRONTEND_DEPLOYMENT.md"

