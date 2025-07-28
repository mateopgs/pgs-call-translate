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

AZURE_WEBSITE_HOSTNAME = "pgs-call-translate.azurewebsites.net"

azure_key = "3T3EuIFcgBiqLGtRbSd9PywVHAKw2RsbnROSIdWCmhPdvkIPnfD0JQQJ99BDACHYHv6XJ3w3AAAAACOGONVI"
azure_base = "https://ai-mateo5227ai919927469639.openai.azure.com/"
azure_version = "2024-12-01-preview"
twilio_sid = "AC50eb788caaafa637df08298a282828b3"
twilio_token = "38557d96c15ebf7f2d20401da2d84c08"

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

def twiml_response(ws_url: str, language: str, tts: str, voice: str = "") -> str:
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

    twilio_client.calls.create(to=to_number, from_=os.getenv("TWILIO_PHONE_NUMBER"),
                               url=twiml_url, method="POST")

@app.post("/voice/source/{session_id}")
async def voice_source(request: Request, session_id: str):
    ws_url = get_ws_url(request, f"/ws/source/{session_id}")
    session = translation_sessions.get(session_id)
    twiml = twiml_response(ws_url, session.source_language, session.source_tts_provider, session.source_voice)
    return Response(content=twiml, media_type="text/xml")

@app.post("/voice/target/{session_id}")
async def voice_target(request: Request, session_id: str):
    ws_url = get_ws_url(request, f"/ws/target/{session_id}")
    session = translation_sessions.get(session_id)
    twiml = twiml_response(ws_url, session.target_language, session.target_tts_provider, session.target_voice)
    return Response(content=twiml, media_type="text/xml")

@app.websocket("/ws/source/{session_id}")
async def ws_source(websocket: WebSocket, session_id: str):
    await websocket.accept()
    session = translation_sessions.get(session_id)
    session.source_websocket = websocket
    # Espera y lógica de traducción simétrica...
    await websocket.receive_text()  # placeholder
    await websocket.close()

@app.websocket("/ws/target/{session_id}")
async def ws_target(websocket: WebSocket, session_id: str):
    await websocket.accept()
    session = translation_sessions.get(session_id)
    session.target_websocket = websocket
    await websocket.receive_text()  # placeholder
    await websocket.close()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 80))
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=port)
