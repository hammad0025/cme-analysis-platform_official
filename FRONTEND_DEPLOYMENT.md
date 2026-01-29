# 🚀 Frontend Deployment Guide - CME Analysis Platform

## Quick Deploy to Vercel (Recommended)

### Option 0: Use Deployment Script (Fastest - 2 minutes)

```bash
# From project root
./deploy-frontend.sh
```

This script will:
- Check prerequisites
- Prompt for environment variables (or use defaults)
- Set up Vercel environment variables
- Deploy to production

### Option 1: Deploy via Vercel CLI (5 minutes)

```bash
cd frontend

# Install Vercel CLI if not already installed
npm i -g vercel

# Login to Vercel
vercel login

# Deploy (follow prompts)
vercel

# Set environment variables
vercel env add REACT_APP_API_URL
# Enter: https://g4dzem9rtk.execute-api.us-east-1.amazonaws.com/prod

vercel env add REACT_APP_USER_POOL_ID
# Enter: us-east-1_t8m33Ihhq

vercel env add REACT_APP_USER_POOL_WEB_CLIENT_ID
# Enter: 42e444v111efsa21b6b3v09svp

# Deploy to production
vercel --prod
```

### Option 2: Deploy via Vercel Dashboard (10 minutes)

1. **Go to Vercel**: https://vercel.com
2. **Sign up/Login** with GitHub
3. **Import Project**:
   - Click "New Project"
   - Import your GitHub repository
   - Select the `frontend` folder as root directory
4. **Configure Build Settings**:
   - Framework Preset: Create React App
   - Build Command: `npm run build`
   - Output Directory: `build`
   - Install Command: `npm install`
5. **Add Environment Variables**:
   - Go to Project Settings → Environment Variables
   - Add these variables:
     ```
     REACT_APP_API_URL=https://g4dzem9rtk.execute-api.us-east-1.amazonaws.com/prod
     REACT_APP_USER_POOL_ID=us-east-1_t8m33Ihhq
     REACT_APP_USER_POOL_WEB_CLIENT_ID=42e444v111efsa21b6b3v09svp
     ```
6. **Deploy**: Click "Deploy"

---

## Alternative: Deploy to Netlify

### Via Netlify CLI

```bash
cd frontend

# Install Netlify CLI
npm i -g netlify-cli

# Login
netlify login

# Initialize site
netlify init

# Set environment variables
netlify env:set REACT_APP_API_URL https://g4dzem9rtk.execute-api.us-east-1.amazonaws.com/prod
netlify env:set REACT_APP_USER_POOL_ID us-east-1_t8m33Ihhq
netlify env:set REACT_APP_USER_POOL_WEB_CLIENT_ID 42e444v111efsa21b6b3v09svp

# Deploy
netlify deploy --prod
```

### Via Netlify Dashboard

1. Go to https://app.netlify.com
2. Click "Add new site" → "Import an existing project"
3. Connect to GitHub and select your repo
4. Configure:
   - Base directory: `frontend`
   - Build command: `npm run build`
   - Publish directory: `frontend/build`
5. Add environment variables in Site Settings → Environment Variables
6. Deploy

---

## Environment Variables Reference

| Variable | Value | Description |
|----------|-------|-------------|
| `REACT_APP_API_URL` | `https://g4dzem9rtk.execute-api.us-east-1.amazonaws.com/prod` | AWS API Gateway endpoint |
| `REACT_APP_USER_POOL_ID` | `us-east-1_t8m33Ihhq` | AWS Cognito User Pool ID |
| `REACT_APP_USER_POOL_WEB_CLIENT_ID` | `42e444v111efsa21b6b3v09svp` | Cognito Web Client ID |

**Note**: These values are from your AWS deployment. If you redeployed, update these values accordingly.

---

## Local Development Setup

1. **Copy environment file**:
   ```bash
   cd frontend
   cp .env.example .env.local
   ```

2. **Update `.env.local`** with your values (or use defaults if they match)

3. **Install dependencies**:
   ```bash
   npm install
   ```

4. **Start development server**:
   ```bash
   npm start
   ```

5. **Open browser**: http://localhost:3000

---

## Testing Login Flow

After deployment:

1. **Create a test user** (if not already created):
   ```bash
   aws cognito-idp admin-create-user \
     --user-pool-id us-east-1_t8m33Ihhq \
     --username test@example.com \
     --user-attributes \
         Name=email,Value=test@example.com \
         Name=given_name,Value=Test \
         Name=family_name,Value=User \
     --temporary-password "TempPass123!" \
     --message-action SUPPRESS
   
   # Set permanent password
   aws cognito-idp admin-set-user-password \
     --user-pool-id us-east-1_t8m33Ihhq \
     --username test@example.com \
     --password "YourSecurePassword123!" \
     --permanent
   ```

2. **Test login**:
   - Go to your deployed frontend URL
   - Click "Login"
   - Enter: `test@example.com` / `YourSecurePassword123!`
   - Should redirect to dashboard

---

## Troubleshooting

### Issue: "API URL not found" or CORS errors

**Solution**: 
- Verify `REACT_APP_API_URL` is set correctly in Vercel/Netlify
- Check API Gateway CORS settings in AWS Console
- Ensure API Gateway allows requests from your frontend domain

### Issue: "Cognito User Pool not found"

**Solution**:
- Verify `REACT_APP_USER_POOL_ID` and `REACT_APP_USER_POOL_WEB_CLIENT_ID` are correct
- Check Cognito User Pool exists in AWS Console
- Ensure User Pool is in `us-east-1` region

### Issue: Build fails

**Solution**:
- Check Node.js version (should be 18+)
- Run `npm install` locally to check for dependency issues
- Check build logs in Vercel/Netlify dashboard

### Issue: Login works but API calls fail

**Solution**:
- Check browser console for errors
- Verify JWT token is being stored in localStorage
- Check API Gateway logs in CloudWatch
- Verify API Gateway has Cognito authorizer configured

---

## Post-Deployment Checklist

```
□ Frontend deployed and accessible
□ Environment variables set correctly
□ Can access login page
□ Can create/login with test user
□ Can access dashboard after login
□ API calls work (check browser console)
□ Session list loads (if any sessions exist)
□ No console errors
```

---

## Next Steps

1. **Create user accounts** for Dorothy and Tim
2. **Test full workflow**: Upload video → Process → View report
3. **Set up custom domain** (optional):
   - In Vercel: Project Settings → Domains
   - Add your domain (e.g., `cme.yourdomain.com`)
   - Update DNS records as instructed

---

## Cost

- **Vercel**: Free tier includes 100GB bandwidth/month (usually sufficient)
- **Netlify**: Free tier includes 100GB bandwidth/month
- **Custom Domain**: ~$10-15/year (optional)

---

**🎉 Your frontend is now live!**

Questions? Check the main `DEPLOYMENT_GUIDE.md` or AWS Console logs.

