# 🚀 HotCalls Azure Deployment Checklist

## ✅ **PREREQUISITES (You Have These)**
- [x] Azure CLI installed and authenticated (`az account show`)
- [x] Terraform installed (`terraform --version`)
- [x] Docker installed (`docker --version`)
- [x] kubectl installed (`kubectl version --client`)

## 📋 **PREPARATION STEPS**

### **1. Review and Update Configuration**
```bash
# Edit the dev configuration file
vim terraform/dev.tfvars
```

**Required changes in `dev.tfvars`:**
- ✅ `alert_email_addresses` - Your email for Azure alerts
- ✅ `apim_publisher_email` - Your email for API Management
- ✅ `location` - Keep "West Europe" or change to preferred region

### **2. Generate Required Secrets (Auto-generated)**
The following will be **automatically generated** by Terraform:
- 🔐 **Database password** - Random secure password
- 🔑 **Django SECRET_KEY** - Random 50-char key
- 🏷️ **Resource names** - Unique with random suffix
- 🔐 **Redis password** - Auto-generated
- 🗝️ **Storage keys** - Azure managed

### **3. Container Registry Name**
**Auto-generated format:** `hotcallsdev<random-suffix>acr`
- Example: `hotcallsdev7a2b1acr.azurecr.io`
- You'll need this for building Docker images

## 🎯 **DEPLOYMENT PHASES**

### **Phase 1: Infrastructure (15-20 minutes)**
```bash
cd terraform
terraform init
terraform plan -var-file="dev.tfvars"
terraform apply -var-file="dev.tfvars"
```

**Creates:**
- 🏗️ Resource Group: `hotcalls-dev-rg`
- 🌐 Virtual Network with subnets
- ☸️ AKS Cluster (1 node, Standard_B2s)
- 🐳 Container Registry
- 🗄️ PostgreSQL Database
- 🗝️ Key Vault for secrets
- 📦 Storage Account for files
- 📊 Monitoring (App Insights + Log Analytics)

### **Phase 2: Application Deployment (10-15 minutes)**
```bash
# Get AKS credentials
az aks get-credentials --resource-group hotcalls-dev-rg --name hotcalls-dev-aks

# Build and push Docker image
docker build -t <ACR_NAME>/hotcalls-backend:latest .
docker push <ACR_NAME>/hotcalls-backend:latest

# Deploy to Kubernetes
cd k8s
export ACR_LOGIN_SERVER="<ACR_NAME>.azurecr.io"
./deploy.sh dev
```

## 💰 **COST ESTIMATION (DEV)**

| Service | Size | Monthly Cost (EUR) |
|---------|------|--------------------|
| **AKS** | 1x Standard_B2s | ~€30 |
| **PostgreSQL** | B1ms | ~€15 |
| **Container Registry** | Basic | ~€5 |
| **Storage Account** | Standard LRS | ~€2 |
| **Key Vault** | Standard | ~€1 |
| **App Insights** | Basic | ~€3 |
| **Network** | Basic | ~€5 |
| **TOTAL** | | **~€61/month** |

## 🔍 **WHAT YOU'LL GET**

### **Azure Resources Created:**
```
Resource Group: hotcalls-dev-rg
├── AKS Cluster: hotcalls-dev-aks
├── Container Registry: hotcallsdev<suffix>acr
├── PostgreSQL: hotcalls-dev-postgres
├── Key Vault: hotcalls-dev-kv
├── Storage: hotcallsdev<suffix>st
├── Log Analytics: hotcalls-dev-logs
└── App Insights: hotcalls-dev-appinsights
```

### **Kubernetes Workloads:**
```
Namespace: hotcalls-dev
├── Deployment: hotcalls-backend (1 replica)
├── Deployment: hotcalls-celery-worker (1 replica)  
├── Deployment: hotcalls-celery-beat (1 replica)
├── Service: hotcalls-backend-service
├── HPA: Auto-scaling 1-2 replicas
└── Ingress: External access
```

### **Access Points:**
- 🌐 **API**: `https://<INGRESS-IP>/api/`
- 📚 **Swagger**: `https://<INGRESS-IP>/api/docs/`
- 🔍 **Health**: `https://<INGRESS-IP>/health/`
- 📊 **Metrics**: Azure Portal → App Insights

## 🚨 **IMPORTANT NOTES**

### **⚠️ Generated Secrets Location:**
```bash
# After terraform apply, get connection info:
terraform output database_connection_string
terraform output storage_connection_string
terraform output redis_connection_string
```

### **🔒 Security:**
- All passwords are auto-generated and stored in Key Vault
- Database has SSL required
- Storage account has private access
- AKS uses managed identity

### **💡 Tips:**
- Keep the `terraform.tfstate` file safe (contains infrastructure state)
- Use `terraform destroy` to clean up when done testing
- Monitor costs in Azure Portal
- Check logs in App Insights for troubleshooting

## ⚡ **QUICK START COMMANDS**

```bash
# 1. Deploy infrastructure
cd terraform && terraform apply -var-file="dev.tfvars"

# 2. Connect to AKS
az aks get-credentials --resource-group hotcalls-dev-rg --name hotcalls-dev-aks

# 3. Deploy application
cd ../k8s && export ACR_LOGIN_SERVER="$(terraform -chdir=../terraform output -raw acr_login_server)"
./deploy.sh dev

# 4. Check status
kubectl get all -n hotcalls-dev
```

**Ready to deploy? Let's go! 🚀** 