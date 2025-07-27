#!/bin/bash

# Azure App Service Deployment Script
# This script automates the deployment of PGS Call Translate to Azure App Service

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 PGS Call Translate - Azure Deployment Script${NC}"
echo ""

# Check if Azure CLI is installed
if ! command -v az &> /dev/null; then
    echo -e "${RED}❌ Azure CLI is not installed. Please install it first.${NC}"
    echo "Visit: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli"
    exit 1
fi

# Check if user is logged in
if ! az account show &> /dev/null; then
    echo -e "${YELLOW}⚠️ You are not logged in to Azure. Please log in first.${NC}"
    echo "Run: az login"
    exit 1
fi

# Prompt for required information
echo -e "${YELLOW}📝 Please provide the following information:${NC}"
echo ""

read -p "Resource Group Name (or press Enter for 'pgs-call-translate-rg'): " RESOURCE_GROUP
RESOURCE_GROUP=${RESOURCE_GROUP:-"pgs-call-translate-rg"}

read -p "App Name (or press Enter for auto-generated): " APP_NAME
if [ -z "$APP_NAME" ]; then
    APP_NAME="pgs-call-translate-$(date +%s)"
fi

read -p "Location (or press Enter for 'East US'): " LOCATION
LOCATION=${LOCATION:-"East US"}

echo ""
echo -e "${YELLOW}🔐 Security Configuration:${NC}"
read -sp "Azure OpenAI API Key: " AZURE_API_KEY
echo ""
read -p "Azure OpenAI Base URL: " AZURE_API_BASE
read -sp "Twilio Account SID: " TWILIO_ACCOUNT_SID
echo ""
read -sp "Twilio Auth Token: " TWILIO_AUTH_TOKEN
echo ""
read -p "Twilio Phone Number: " TWILIO_PHONE_NUMBER
echo ""

# Validate required inputs
if [ -z "$AZURE_API_KEY" ] || [ -z "$AZURE_API_BASE" ] || [ -z "$TWILIO_ACCOUNT_SID" ] || [ -z "$TWILIO_AUTH_TOKEN" ] || [ -z "$TWILIO_PHONE_NUMBER" ]; then
    echo -e "${RED}❌ All security configuration fields are required.${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}📋 Deployment Summary:${NC}"
echo "Resource Group: $RESOURCE_GROUP"
echo "App Name: $APP_NAME"
echo "Location: $LOCATION"
echo "Azure OpenAI Base: $AZURE_API_BASE"
echo "Twilio Phone: $TWILIO_PHONE_NUMBER"
echo ""

read -p "Continue with deployment? (y/N): " CONFIRM
if [[ ! $CONFIRM =~ ^[Yy]$ ]]; then
    echo "Deployment cancelled."
    exit 0
fi

echo ""
echo -e "${GREEN}🏗️ Starting deployment...${NC}"

# Create resource group
echo "Creating resource group..."
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none

# Deploy using ARM template
echo "Deploying App Service..."
DEPLOYMENT_OUTPUT=$(az deployment group create \
    --resource-group "$RESOURCE_GROUP" \
    --template-file azure-deploy.json \
    --parameters \
        appName="$APP_NAME" \
        azureApiKey="$AZURE_API_KEY" \
        azureApiBase="$AZURE_API_BASE" \
        twilioAccountSid="$TWILIO_ACCOUNT_SID" \
        twilioAuthToken="$TWILIO_AUTH_TOKEN" \
        twilioPhoneNumber="$TWILIO_PHONE_NUMBER" \
    --query 'properties.outputs' \
    --output json)

# Extract outputs
APP_URL=$(echo $DEPLOYMENT_OUTPUT | jq -r '.appServiceUrl.value')

# Deploy code
echo "Deploying application code..."
if [ -f "requirements.txt" ]; then
    # Create a temporary zip file
    zip -r deploy.zip . -x "*.git*" "*__pycache__*" "*.pyc" "deploy.zip"
    
    # Deploy the zip file
    az webapp deployment source config-zip \
        --name "$APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --src deploy.zip \
        --output none
    
    # Clean up
    rm deploy.zip
else
    echo -e "${RED}❌ requirements.txt not found. Make sure you're in the project directory.${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}✅ Deployment completed successfully!${NC}"
echo ""
echo -e "${GREEN}🌐 Your application is available at:${NC}"
echo "$APP_URL"
echo ""
echo -e "${YELLOW}📝 Next Steps:${NC}"
echo "1. Update your Twilio webhooks to use: $APP_URL"
echo "2. Test the application by visiting: $APP_URL"
echo "3. Monitor logs with: az webapp log tail --name $APP_NAME --resource-group $RESOURCE_GROUP"
echo ""
echo -e "${GREEN}🎉 No more ngrok needed! Your service is now always active on Azure.${NC}"