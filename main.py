import os
import time
import json
import logging
import datetime
from typing import Dict, Optional

from fastapi import FastAPI, WebSocket, Request, Form
from fastapi.responses import Response, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncAzureOpenAI
from twilio.rest import Client
from litellm import acompletion
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Configuration constants
AZURE_WEBSITE_HOSTNAME = os.getenv("AZURE_WEBSITE_HOSTNAME", "pgs-call-translate.azurewebsites.net")
WAITING_MUSIC_URL = os.getenv("WAITING_MUSIC_URL", "https://example.com/waiting-music.mp3")
RINGTONE_URL = os.getenv("RINGTONE_URL", "https://example.com/ringtone.mp3")

# Azure OpenAI configuration
azure_key = os.getenv("AZURE_OPENAI_KEY")
azure_base = os.getenv("AZURE_OPENAI_ENDPOINT")
azure_version = os.getenv("AZURE_OPENAI_VERSION", "2024-12-01-preview")

# Twilio configuration
twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
twilio_token = os.getenv("TWILIO_AUTH_TOKEN")
twilio_phone_number = os.getenv("TWILIO_PHONE_NUMBER")

if not all([azure_key, azure_base, twilio_sid, twilio_token, twilio_phone_number]):
    logging.error("Missing required environment variables")
    
    # Set fallback values for development/testing when environment variables are missing
    azure_key = azure_key or "fallback-azure-key"
    azure_base = azure_base or "https://fallback.openai.azure.com/"
    twilio_sid = twilio_sid or "fallback-twilio-sid"
    twilio_token = twilio_token or "fallback-twilio-token"
    twilio_phone_number = twilio_phone_number or "+1234567890"

openai_client = AsyncAzureOpenAI(api_key=azure_key, azure_endpoint=azure_base, api_version=azure_version)
twilio_client = Client(twilio_sid, twilio_token)

def get_base_url(request: Request) -> str:
    if AZURE_WEBSITE_HOSTNAME:
        return f"https://{AZURE_WEBSITE_HOSTNAME}"
    host = request.headers.get("X-Forwarded-Host") or request.headers.get("Host")
    return f"https://{host}"

def get_ws_url(request: Request, path: str) -> str:
    base = get_base_url(request).replace("https://", "")
    return f"wss://{base}{path}"

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

translation_sessions: Dict[str, "TranslationSession"] = {}

class TranslationSession:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.source_websocket: Optional[WebSocket] = None
        self.target_websocket: Optional[WebSocket] = None
        self.source_language = ""
        self.target_language = ""
        self.source_tts_provider = ""
        self.source_voice = ""
        self.target_tts_provider = ""
        self.target_voice = ""
        self.base_url = ""
        self.play_waiting_music = False

def cleanup_session(session_id: str):
    """Clean up a translation session by closing WebSockets and removing from sessions dict."""
    session = translation_sessions.get(session_id)
    if session:
        try:
            if session.source_websocket:
                session.source_websocket.close()
        except Exception as e:
            logging.error(f"Error closing source websocket for session {session_id}: {e}")
        
        try:
            if session.target_websocket:
                session.target_websocket.close()
        except Exception as e:
            logging.error(f"Error closing target websocket for session {session_id}: {e}")
        
        # Remove session from dict
        translation_sessions.pop(session_id, None)
        logging.info(f"Cleaned up session {session_id}")

@app.get("/api/status")
async def status():
    return {
        "status": "ok",
        "service": "ConvRelay AI Translate",
        "environment": "Azure App Service" if AZURE_WEBSITE_HOSTNAME else "Development",
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "hostname": AZURE_WEBSITE_HOSTNAME or "local"
    }

async def translate_stream(text: str, src: str, tgt: str):
    msgs = [
        {"role": "system", "content": f"Translate from {src} to {tgt}."},
        {"role": "user", "content": text}
    ]
    stream = await acompletion(model="azure/gpt-4.1-nano",
        api_base=azure_base, api_version=azure_version, api_key=azure_key,
        messages=msgs, stream=True, temperature=0.3)
    async for chunk in stream:
        token = chunk.choices[0].delta.content or ""
        yield {"token": token, "type": "text", "last": False}
    yield {"token": "", "type": "text", "last": True}

def generate_conversation_relay_twiml(ws_url: str, language: str, tts: str, voice: str = "") -> str:
    """Generate TwiML for ConversationRelay connection."""
    voice_attr = f' voice="{voice}"' if voice else ""
    stt = 'transcriptionProvider="google"' if language.startswith("ar-") else 'transcriptionProvider="deepgram"'
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <ConversationRelay url="{ws_url}" language="{language}" ttsProvider="{tts}"{voice_attr} {stt}/>
  </Connect>
</Response>"""

@app.get("/")
async def root():
    return FileResponse("start.html")

@app.post("/initiate-call")
async def initiate_call(from_number: str = Form(...), to_number: str = Form(...),
                        source_language: str = Form(...), target_language: str = Form(...),
                        source_tts_provider: str = Form("ElevenLabs"),
                        source_voice: str = Form(""),
                        target_tts_provider: str = Form("ElevenLabs"),
                        target_voice: str = Form(""),
                        play_waiting_music: Optional[str] = Form(None),
                        request: Request = None):
    session_id = f"session_{int(time.time())}"
    session = TranslationSession(session_id)
    session.source_language = source_language
    session.target_language = target_language
    session.source_tts_provider = source_tts_provider
    session.source_voice = source_voice
    session.target_tts_provider = target_tts_provider
    session.target_voice = target_voice
    session.base_url = get_base_url(request)
    session.play_waiting_music = (play_waiting_music == "on")
    translation_sessions[session_id] = session

    # Llamadas outbound a Twilio (ASK endpoints /voice/source y /voice/target)
    await create_outbound_call(request, session_id, from_number, source=True)
    await create_outbound_call(request, session_id, to_number, source=False)

    return JSONResponse({"status":"started","session_id":session_id,"base_url":session.base_url})

async def create_outbound_call(request: Request, session_id: str, to_number: str, source: bool):
    session = translation_sessions[session_id]
    ws_path = f"/ws/source/{session_id}" if source else f"/ws/target/{session_id}"
    ws_url = get_ws_url(request, ws_path)
    language = session.source_language if source else session.target_language
    tts = session.source_tts_provider if source else session.target_tts_provider
    voice = session.source_voice if source else session.target_voice
    twiml_url = get_base_url(request) + (f"/voice/source/{session_id}" if source else f"/voice/target/{session_id}")

    twilio_client.calls.create(to=to_number, from_=twilio_phone_number,
                               url=twiml_url, method="POST")

@app.post("/voice/source/{session_id}")
async def voice_source(request: Request, session_id: str):
    ws_url = get_ws_url(request, f"/ws/source/{session_id}")
    session = translation_sessions.get(session_id)
    twiml = generate_conversation_relay_twiml(ws_url, session.source_language, session.source_tts_provider, session.source_voice)
    return Response(content=twiml, media_type="text/xml")

@app.post("/voice/target/{session_id}")
async def voice_target(request: Request, session_id: str):
    ws_url = get_ws_url(request, f"/ws/target/{session_id}")
    session = translation_sessions.get(session_id)
    twiml = generate_conversation_relay_twiml(ws_url, session.target_language, session.target_tts_provider, session.target_voice)
    return Response(content=twiml, media_type="text/xml")

@app.websocket("/ws/source/{session_id}")
async def ws_source(websocket: WebSocket, session_id: str):
    await websocket.accept()
    session = translation_sessions.get(session_id)
    if not session:
        await websocket.close(code=1000, reason="Session not found")
        return
    
    session.source_websocket = websocket
    logging.info(f"Source WebSocket connected for session {session_id}")
    
    try:
        while True:
            data = await websocket.receive_json()
            logging.info(f"Source received: {data}")
            
            # Handle speech recognition results
            if data.get("type") == "speech_recognition" and data.get("text"):
                text = data["text"]
                # Translate from source to target language
                if session.target_websocket:
                    async for translation_chunk in translate_stream(text, session.source_language, session.target_language):
                        await session.target_websocket.send_json(translation_chunk)
                        
    except Exception as e:
        logging.error(f"Error in source WebSocket {session_id}: {e}")
    finally:
        logging.info(f"Source WebSocket disconnected for session {session_id}")
        cleanup_session(session_id)

@app.websocket("/ws/target/{session_id}")
async def ws_target(websocket: WebSocket, session_id: str):
    await websocket.accept()
    session = translation_sessions.get(session_id)
    if not session:
        await websocket.close(code=1000, reason="Session not found")
        return
    
    session.target_websocket = websocket
    logging.info(f"Target WebSocket connected for session {session_id}")
    
    try:
        while True:
            data = await websocket.receive_json()
            logging.info(f"Target received: {data}")
            
            # Handle speech recognition results
            if data.get("type") == "speech_recognition" and data.get("text"):
                text = data["text"]
                # Translate from target to source language
                if session.source_websocket:
                    async for translation_chunk in translate_stream(text, session.target_language, session.source_language):
                        await session.source_websocket.send_json(translation_chunk)
                        
    except Exception as e:
        logging.error(f"Error in target WebSocket {session_id}: {e}")
    finally:
        logging.info(f"Target WebSocket disconnected for session {session_id}")
        cleanup_session(session_id)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=port)
