# Migration Guide: From ngrok to Azure App Service

This guide will help you migrate your PGS Call Translate application from using ngrok to a production Azure deployment.

## Why Migrate from ngrok?

**Current (ngrok) Problems:**
- ❌ Requires manual ngrok process to be running
- ❌ Temporary URLs that change frequently
- ❌ Not suitable for production use
- ❌ Service goes down when your computer sleeps/restarts
- ❌ Limited bandwidth on free tier

**Azure App Service Benefits:**
- ✅ Always-on service (24/7 availability)
- ✅ Permanent URL that doesn't change
- ✅ Production-ready with auto-scaling
- ✅ Built-in health monitoring
- ✅ Secure environment variable management
- ✅ Automatic SSL certificates

## Migration Steps

### Step 1: Prepare Your Environment

1. **Collect your current credentials** from your local setup:
   - Azure OpenAI API key and endpoint
   - Twilio Account SID and Auth Token
   - Twilio Phone Number

2. **Install Azure CLI** (if not already installed):
   ```bash
   # Windows
   winget install Microsoft.AzureCLI
   
   # macOS
   brew install azure-cli
   
   # Linux
   curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
   ```

3. **Login to Azure:**
   ```bash
   az login
   ```

### Step 2: Deploy to Azure

Choose one of the deployment methods:

#### Option A: Quick Deploy (Recommended)

```bash
# Make the script executable
chmod +x deploy-azure.sh

# Run the deployment script
./deploy-azure.sh
```

The script will prompt you for all necessary information and handle the deployment automatically.

#### Option B: Manual Deployment

Follow the detailed instructions in [AZURE_DEPLOYMENT.md](./AZURE_DEPLOYMENT.md).

### Step 3: Update Twilio Webhooks

1. **Get your new Azure URL** from the deployment output:
   ```
   https://your-app-name.azurewebsites.net
   ```

2. **Update Twilio Console:**
   - Log in to [Twilio Console](https://console.twilio.com/)
   - Navigate to Phone Numbers → Manage → Active numbers
   - Click on your Twilio phone number
   - Update webhook URLs:
     - **Old:** `https://abc123.ngrok.io/voice/...`
     - **New:** `https://your-app-name.azurewebsites.net/voice/...`

### Step 4: Test the Migration

1. **Health Check:**
   ```bash
   curl https://your-app-name.azurewebsites.net/health
   ```

2. **Use monitoring script:**
   ```bash
   ./monitor.sh https://your-app-name.azurewebsites.net
   ```

3. **Test a call:**
   - Visit: `https://your-app-name.azurewebsites.net`
   - Create a translation session
   - Verify both parties can communicate

### Step 5: Clean Up Local Setup

Once everything is working in Azure:

1. **Stop ngrok:**
   ```bash
   # You can stop your ngrok process
   # No longer needed!
   ```

2. **Update your documentation** to point to the Azure URL

3. **Remove local environment variables** (optional):
   - Keep your `.env` file for local development
   - All production config is now in Azure

## Troubleshooting

### Common Issues

1. **"Application failed to start"**
   ```bash
   # Check logs
   az webapp log tail --name your-app-name --resource-group your-resource-group
   ```

2. **"Environment variables not found"**
   ```bash
   # Verify app settings
   az webapp config appsettings list --name your-app-name --resource-group your-resource-group
   ```

3. **"Twilio webhooks failing"**
   - Verify the webhook URLs in Twilio Console
   - Ensure they point to your Azure URL, not ngrok
   - Check that the Azure app is running and accessible

### Getting Help

1. **Check application health:**
   ```bash
   ./monitor.sh https://your-app-name.azurewebsites.net
   ```

2. **View Azure logs:**
   ```bash
   az webapp log tail --name your-app-name --resource-group your-resource-group
   ```

3. **Restart the app:**
   ```bash
   az webapp restart --name your-app-name --resource-group your-resource-group
   ```

## Cost Estimates

**Azure App Service B1 (Basic):**
- Cost: ~$13/month
- 1 vCPU, 1.75 GB RAM
- Suitable for development and light production

**Azure App Service S1 (Standard):**
- Cost: ~$56/month  
- 1 vCPU, 1.75 GB RAM
- Auto-scaling, staging slots
- Recommended for production

**Cost Comparison:**
- ngrok Pro: $8/month (but still requires your computer to run)
- Azure B1: $13/month (fully managed, always-on)

## Security Improvements

The Azure deployment includes several security improvements:

1. **Environment Variables:** All secrets are stored securely in Azure App Settings
2. **HTTPS by Default:** Automatic SSL certificates
3. **No Hardcoded Credentials:** All sensitive data moved to environment variables
4. **Health Monitoring:** Built-in monitoring and alerting capabilities

## Next Steps

After successful migration:

1. **Set up monitoring:** Configure Azure Application Insights for detailed monitoring
2. **Set up alerts:** Configure alerts for downtime or errors
3. **Set up backup:** Configure automated backups
4. **Scale as needed:** Adjust the App Service Plan based on usage

## Rollback Plan

If you need to rollback to ngrok temporarily:

1. Start ngrok: `ngrok http 8080`
2. Update Twilio webhooks back to ngrok URL
3. Run locally: `python main.py`

However, this should only be temporary while you resolve any issues with the Azure deployment.