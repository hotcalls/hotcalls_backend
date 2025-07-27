# Quick Start Deployment Guide

## Improved Deployment Script

The deployment script has been improved to be **foolproof** and **explicit**:

### ✅ Key Improvements

1. **MANDATORY --project-name**: No more defaults - you MUST specify the exact resource group name
2. **Automatic Resource Group Handling**: Script automatically imports existing resource groups
3. **Retry Logic**: Failed deployments are automatically retried with cleanup
4. **Better Error Messages**: Clear guidance on what to do if something fails
5. **Validation**: All parameters are validated before deployment starts

### 🚀 Basic Usage

**REQUIRED**: You MUST specify `--project-name`

```bash
# Deploy to staging
./deploy.sh --project-name=hotcalls-staging --environment=staging

# Deploy to production
./deploy.sh --project-name=hotcalls-prod --environment=production

# Update only (no infrastructure changes)
./deploy.sh --project-name=hotcalls-staging --update-only

# Deploy with specific branch
./deploy.sh --project-name=hotcalls-staging --branch=main
```

### 📋 What the Script Does Automatically

1. **Checks if you're logged into Azure** - prompts login if needed
2. **Handles existing resource groups** - imports them into Terraform state if they exist
3. **Creates Terraform workspaces** - based on project name and environment
4. **Retries failed deployments** - with automatic cleanup between attempts
5. **Validates all environment variables** - from your `.env` file
6. **Builds and deploys everything** - frontend, backend, Kubernetes, ingress

### ⚠️ Prerequisites

1. Ensure your `.env` file is configured with all required variables
2. Be logged into Azure CLI: `az login`
3. Have all required tools installed (Docker, kubectl, terraform, etc.)

### 🔧 The Project Name is EXACT

The `--project-name` parameter is used **exactly as specified**:
- ✅ `--project-name=hotcalls-staging` → Resource Group: `hotcalls-staging`
- ✅ `--project-name=my-company-prod` → Resource Group: `my-company-prod`
- ✅ `--project-name=test123` → Resource Group: `test123`

**No prefixes or suffixes are added!**

### 🆘 If Something Fails

The script now provides **clear error messages** with exact commands to fix issues:

```bash
# If you see resource group errors, the script will show:
❌ ERROR: Failed to import resource group after 3 attempts.
You may need to delete it manually: az group delete --name 'your-project-name'

# If workspace is missing in update-only mode:
❌ ERROR: Terraform workspace 'your-project-staging' not found for update-only mode!
You must run a full deployment first: ./deploy.sh --project-name=your-project --environment=staging
```

### 🎯 Example Complete Deployment

```bash
# 1. Make sure you have a .env file configured
# 2. Login to Azure
az login

# 3. Run deployment with explicit project name
./deploy.sh --project-name=hotcalls-staging --environment=staging --branch=staging

# 4. The script will:
#    - Check/import existing resource groups
#    - Deploy all infrastructure
#    - Build and push Docker images  
#    - Deploy to Kubernetes
#    - Set up ingress and provide the final URL
```

### 📈 Success Output

When successful, you'll see:
```
🎉 Application is ready!
🌐 Application URL: http://EXTERNAL_IP
   • Frontend: http://EXTERNAL_IP/
   • API: http://EXTERNAL_IP/api/
   • Health: http://EXTERNAL_IP/health/
   • Admin: http://EXTERNAL_IP/admin/
```

The deployment is now **foolproof** and handles edge cases automatically! 