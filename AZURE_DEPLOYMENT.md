# Azure App Service Deployment Guide

This guide will help you deploy the PGS Call Translate application to Azure App Service, eliminating the need for ngrok.

## Prerequisites

1. Azure CLI installed and logged in
2. Azure subscription with sufficient permissions
3. Resource Group created (or permission to create one)

## Step 1: Create Azure App Service

```bash
# Set variables
RESOURCE_GROUP="pgs-call-translate-rg"
APP_NAME="pgs-call-translate-$(date +%s)"  # Unique name
LOCATION="East US"
PLAN_NAME="pgs-call-translate-plan"

# Create resource group (if it doesn't exist)
az group create --name $RESOURCE_GROUP --location "$LOCATION"

# Create App Service Plan (Linux, Basic B1)
az appservice plan create \
  --name $PLAN_NAME \
  --resource-group $RESOURCE_GROUP \
  --location "$LOCATION" \
  --is-linux \
  --sku B1

# Create App Service
az webapp create \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --plan $PLAN_NAME \
  --runtime "PYTHON:3.12"
```

## Step 2: Configure Environment Variables

```bash
# Set application settings (environment variables)
az webapp config appsettings set \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --settings \
    AZURE_API_KEY="your_azure_openai_api_key" \
    AZURE_API_BASE="https://your-instance.openai.azure.com" \
    AZURE_API_VERSION="2024-12-01-preview" \
    TWILIO_ACCOUNT_SID="your_twilio_account_sid" \
    TWILIO_AUTH_TOKEN="your_twilio_auth_token" \
    TWILIO_PHONE_NUMBER="your_twilio_phone_number" \
    HOST="0.0.0.0" \
    PORT="8000"
```

## Step 3: Configure Startup Command

```bash
# Set startup command
az webapp config set \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --startup-file "python -m uvicorn main:app --host 0.0.0.0 --port 8000"
```

## Step 4: Deploy the Application

### Option A: Deploy from Local Files

```bash
# Create deployment package
zip -r app.zip . -x "*.git*" "*__pycache__*" "*.pyc"

# Deploy via ZIP
az webapp deployment source config-zip \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --src app.zip
```

### Option B: Deploy from GitHub (Recommended)

```bash
# Enable GitHub deployment
az webapp deployment source config \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --repo-url https://github.com/mateopgs/pgs-call-translate \
  --branch main \
  --manual-integration
```

## Step 5: Configure Always On

```bash
# Enable Always On to keep the service running
az webapp config set \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --always-on true
```

## Step 6: Get Your Public URL

```bash
# Get the public URL of your deployed app
echo "Your app is deployed at: https://$APP_NAME.azurewebsites.net"
```

## Step 7: Update Twilio Webhooks

Replace your ngrok URL with the Azure App Service URL in your Twilio console webhooks:

- Old: `https://your-ngrok-url.ngrok.io`
- New: `https://your-app-name.azurewebsites.net`

## Health Check

Your app will be available at:
- Main interface: `https://your-app-name.azurewebsites.net/`
- Health check: `https://your-app-name.azurewebsites.net/docs`

## Troubleshooting

1. **Check logs:**
   ```bash
   az webapp log tail --name $APP_NAME --resource-group $RESOURCE_GROUP
   ```

2. **Restart the app:**
   ```bash
   az webapp restart --name $APP_NAME --resource-group $RESOURCE_GROUP
   ```

3. **Check configuration:**
   ```bash
   az webapp config appsettings list --name $APP_NAME --resource-group $RESOURCE_GROUP
   ```

## Cost Optimization

- Use B1 Basic plan (~$13/month) for development
- Use S1 Standard plan (~$56/month) for production (includes auto-scaling)
- Consider Azure Container Apps for potentially lower costs with automatic scaling to zero

## Alternative: Azure Container Apps

For modern cloud-native deployment with automatic scaling:

```bash
# Create Container App Environment
az containerapp env create \
  --name pgs-translate-env \
  --resource-group $RESOURCE_GROUP \
  --location "$LOCATION"

# Deploy Container App
az containerapp create \
  --name pgs-call-translate \
  --resource-group $RESOURCE_GROUP \
  --environment pgs-translate-env \
  --image mcr.microsoft.com/azuredocs/containerapps-helloworld:latest \
  --target-port 8080 \
  --ingress external \
  --env-vars \
    AZURE_API_KEY="your_azure_openai_api_key" \
    AZURE_API_BASE="https://your-instance.openai.azure.com" \
    TWILIO_ACCOUNT_SID="your_twilio_account_sid" \
    TWILIO_AUTH_TOKEN="your_twilio_auth_token"
```