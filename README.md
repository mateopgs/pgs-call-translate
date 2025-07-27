# ConversationRelay Translate - Real-Time Voice Translation for Phone Calls

A real-time voice translation system built with FastAPI, Twilio, and Azure OpenAI that enables seamless bidirectional voice conversations between speakers of different languages.

## Overview

**ConversationRelay Translate** is a real-time translation service that bridges language barriers by providing instant voice-to-voice translation during phone calls. The system automatically creates translation sessions, manages WebSocket connections, and uses Azure OpenAI's GPT-4 for high-quality translations.

## Architecture

### Core Components

1. **Translation Session Management**
   - `TranslationSession` class manages call pairs and WebSocket connections
   - Tracks source and target call SIDs, phone numbers, and languages
   - Maintains WebSocket connections for both callers

2. **WebSocket Endpoints**
   - `/ws/source/{session_id}` - Handles source caller websocket
   - `/ws/target/{session_id}` - Handles target callee websocket
   - Real-time bidirectional voice processing

3. **Voice Webhooks**
   - `/voice/source/{session_id}` - Outbound call handler for source language speaker
   - `/voice/target/{session_id}` - Outbound call handler for target language speaker

4. **Translation Engine**
   - Streaming translation using Azure OpenAI GPT-4
   - Configurable source and target languages
   - Real-time token-by-token translation delivery

## How It Works

### Translation Process

```
Source Caller → WebSocket → Translation Engine → WebSocket → Target Callee
     ↑                                                            ↓
     ←───────── WebSocket ← Translation Engine ←────────      WebSocket
```

## Features

- **Bidirectional Translation**: Both parties can speak and hear in own language
- **Real-time Translation**: Instant translation with minimal delay
- **Session Management**: Robust session tracking with automatic cleanup
- **Configurable Languages**: Environment-based language configuration
- **Error Handling**: Comprehensive error handling and logging
- **Scalable Architecture**: FastAPI-based async architecture
- **Always On**: Deploy to Azure for 24/7 availability without ngrok

### Supported Languages

ConversationRelay supports any language pair available in Twilio's Speech-to-Text (STT) and Text-to-Speech (TTS) services. The demo UI includes a selection of popular languages, though many more are supported:

- `en-US` English US
- `de-DE` German
- `es-ES` Spanish
- `fr-FR` French
- `it-IT` Italian
- `ro-RO` Romanian
- `pt-PT` Portuguese
- `el-GR` Greek
- `ja-JP` Japanese
- `zh-CN` Chinese Mandarin
- `ar-SA` Arabic

**Default Configuration:**
- **Source Language**: Defaults to `en-US` (English)
- **Target Language**: Defaults to `de-DE` (German)

## Deployment Options

### Option 1: Azure App Service (Recommended)

Deploy to Azure for production use without ngrok:

1. **Quick Deploy with Script:**
   ```bash
   ./deploy-azure.sh
   ```

2. **Manual Azure CLI Deploy:**
   ```bash
   # See AZURE_DEPLOYMENT.md for detailed instructions
   az group create --name pgs-call-translate-rg --location "East US"
   az webapp create --name pgs-call-translate-unique --resource-group pgs-call-translate-rg --plan myplan --runtime "PYTHON:3.12"
   ```

3. **Deploy with ARM Template:**
   ```bash
   az deployment group create --resource-group pgs-call-translate-rg --template-file azure-deploy.json
   ```

See [AZURE_DEPLOYMENT.md](./AZURE_DEPLOYMENT.md) for complete deployment guide.

### Option 2: Fly.io

Use the existing Fly.io configuration:

```bash
flyctl deploy
```

### Option 3: Local Development

For development and testing:

1. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

3. **Run the Application:**
   ```bash
   python main.py
   ```

4. **Expose with ngrok (development only):**
   ```bash
   ngrok http 8080
   ```

## Environment Configuration

Create a `.env` file (copy from `.env.example`):

```env
# Azure OpenAI Configuration
AZURE_API_KEY=your_azure_openai_api_key
AZURE_API_BASE=https://your-instance.openai.azure.com
AZURE_API_VERSION=2024-12-01-preview

# Twilio Configuration
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_PHONE_NUMBER=your_twilio_phone_number

# Server Configuration (optional)
HOST=0.0.0.0
PORT=8080
```

## Production Setup

### 1. Deploy to Azure
Use the provided deployment script or manual instructions in `AZURE_DEPLOYMENT.md`.

### 2. Configure Twilio Webhooks
Update your Twilio webhooks to use your Azure URL:
- Replace: `https://your-ngrok-url.ngrok.io`
- With: `https://your-app-name.azurewebsites.net`

### 3. Monitor Health
- Health check: `https://your-app-name.azurewebsites.net/health`
- Status: `https://your-app-name.azurewebsites.net/status`
- API docs: `https://your-app-name.azurewebsites.net/docs`

## Current Status

**Phase 1**: ✅ Complete - Bidirectional real-time translation
- Source-to-target translation
- Target-to-source translation
- Session management
- WebSocket handling
- Environment-based configuration
- Web Interface: Browser-based translation interface
- **Production Deploy**: Azure App Service deployment (replaces ngrok)

## Security Features

- ✅ Environment variable configuration (no hardcoded credentials)
- ✅ Secure Azure deployment with managed secrets
- ✅ Health monitoring endpoints
- ✅ Always-on service without ngrok tunnels

## Future Enhancements

- **Conference Calls**: Multiple participants with different languages
- **Recording and Transcription**: Call recording with translated transcripts
- **Mobile App**: Native mobile application
- **Auto-scaling**: Automatic scaling based on demand

