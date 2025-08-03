import os
import json
import logging
import time
import uvicorn
from typing import Dict, Optional

from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from openai import AsyncOpenAI,AsyncAzureOpenAI
from twilio.rest import Client
from litellm import acompletion

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logging.getLogger("twilio").setLevel(logging.WARNING)


# Load environment
load_dotenv()
app = FastAPI()

# Allow CORS for any origin so your front-end (deployed anywhere) can call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# <<< FIN DEL CAMBIO DE CORS >>>
openai_client = AsyncAzureOpenAI(api_key="3T3EuIFcgBiqLGtRbSd9PywVHAKw2RsbnROSIdWCmhPdvkIPnfD0JQQJ99BDACHYHv6XJ3w3AAAAACOGONVI",
                                 azure_endpoint="https://ai-mateo5227ai919927469639.openai.azure.com/",
                                 api_version="2024-12-01-preview")
twilio_client = Client("AC50eb788caaafa637df08298a282828b3","0c6935d145c8cd7774e6cb5459f3d501")

# URLs for hold / waiting music
MUSIC_URL = "https://pub-09065925c50a4711a49096e7dbee29ce.r2.dev/ringtone-02-133354.mp3"
WAIT_URL = "https://pub-09065925c50a4711a49096e7dbee29ce.r2.dev/mixkit-marimba-ringtone-1359.wav"

# In-memory session registry
class TranslationSession:
    def __init__(self, session_id: str, source_call_sid: str):
        self.session_id = session_id
        self.source_call_sid = source_call_sid
        self.target_call_sid: Optional[str] = None
        self.source_websocket: Optional[WebSocket] = None
        self.target_websocket: Optional[WebSocket] = None
        self.source_phone_number: Optional[str] = None
        self.target_phone_number: Optional[str] = None
        self.source_language: str = ""
        self.target_language: str = ""
        self.source_tts_provider: str = "ElevenLabs"
        self.source_voice: str = ""
        self.target_tts_provider: str = "ElevenLabs"
        self.target_voice: str = ""
        self.host: Optional[str] = None
        self.play_waiting_music: bool = True

translation_sessions: Dict[str, TranslationSession] = {}

async def translate_text_streaming(text: str, source_lang: str, target_lang: str):
    """Call OpenAI to translate text in streaming mode."""
    messages = [
        {"role": "system", "content": f"You are a professional real-time translator. "
                                     f"Translate the following {source_lang} text to {target_lang}. "
                                     f"Provide only the translation, no explanations."},
        {"role": "user", "content": text}
    ]
    stream = await acompletion(
        model="azure/gpt-4.1-nano",
        api_base = "https://ai-mateo5227ai919927469639.openai.azure.com/",
        api_version = "2024-12-01-preview",
        api_key = "3T3EuIFcgBiqLGtRbSd9PywVHAKw2RsbnROSIdWCmhPdvkIPnfD0JQQJ99BDACHYHv6XJ3w3AAAAACOGONVI",
        messages=messages,
        stream=True,
        temperature=0.3,  # Lower temperature for more consistent translations
)

    async for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield {"token": delta, "type": "text", "last": False}

    # signal end of stream
    yield {"token": "", "type": "text", "last": True}

def generate_conversation_relay_twiml(ws_url: str, language: str,
                                      tts_provider: str, voice: str = "") -> str:
    """Build TwiML for Twilio <ConversationRelay> widget."""
    voice_attr = f' voice="{voice}"' if voice else ""
    stt_attr = ' transcriptionProvider="google"' if language.startswith("ar-") else \
               ' transcriptionProvider="deepgram"'
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <ConversationRelay
      debug="speaker-events"
      url="{ws_url}"
      language="{language}"
      ttsProvider="{tts_provider}"
      {voice_attr}
      {stt_attr}/>
  </Connect>
</Response>'''

async def check_session_readiness_and_notify(session: TranslationSession) -> bool:
    """Wait until both websockets are connected, then notify readiness."""
    if not (session.source_websocket and session.target_websocket):
        wait_event = {
            "type": "play",
            "source": WAIT_URL,
            "loop": 0,
            "preemptible": True,
            "interruptible": False
        }
        if session.source_websocket:
            await session.source_websocket.send_json(wait_event)
        if session.target_websocket:
            await session.target_websocket.send_json(wait_event)
        return False

    # both sides connected — send a localized "ready" message
    for ws, lang in (
        (session.source_websocket, session.source_language),
        (session.target_websocket, session.target_language),
    ):
        text = ""
        async for evt in translate_text_streaming("You are ready to talk.", "en-US", lang):
            text += evt["token"]
        await ws.send_json({"type": "text", "token": text, "last": True})

    return True

async def cleanup_session(session_id: str):
    """Close both websockets and drop session from registry."""
    session = translation_sessions.pop(session_id, None)
    if not session:
        return

    end_msg = {"type": "end", "handoffData": "session complete"}
    for ws in (session.source_websocket, session.target_websocket):
        if ws:
            try:
                await ws.send_json(end_msg)
                await ws.close()
            except Exception:
                pass

async def play_waiting_music(ws: WebSocket):
    """Play hold music while waiting for the other side."""
    await ws.send_json({
        "type": "play",
        "source": MUSIC_URL,
        "loop": 0,
        "preemptible": True,
        "interruptible": True
    })

async def create_outbound_call(session_id: str, host: str,
                               to_number: str, twilio_number: str,
                               path: str, is_target: bool):
    """Initiate a call via Twilio to one party."""
    session = translation_sessions.get(session_id)
    if not session:
        logging.error(f"Session {session_id} not found")
        return

    webhook_url = f"https://{host}{path}/{session_id}"
    logging.info(f"Initiating call to {to_number} using webhook {webhook_url}")
    call = twilio_client.calls.create(
        to=to_number,
        from_=twilio_number,
        url=webhook_url,
        method="POST",
        record=True
    )

    if is_target:
        session.target_call_sid = call.sid
    else:
        session.source_call_sid = call.sid

@app.websocket("/ws/source/{session_id}")
async def ws_source(websocket: WebSocket, session_id: str):
    await websocket.accept()
    try:
        while True:
            msg = json.loads(await websocket.receive_text())
            session = translation_sessions.get(session_id)
            if not session:
                continue

            if msg["type"] == "setup":
                session.source_websocket = websocket
                if not await check_session_readiness_and_notify(session):
                    continue

            elif msg["type"] == "prompt":
                if not session.target_websocket:
                    continue
                prompt = msg["voicePrompt"]
                async for evt in translate_text_streaming(prompt,
                                                          session.source_language,
                                                          session.target_language):
                    await session.target_websocket.send_json(evt)
                if session.play_waiting_music:
                    await play_waiting_music(session.source_websocket)

    except Exception as e:
        logging.error(f"Source WS error: {e}")
    finally:
        await cleanup_session(session_id)

@app.websocket("/ws/target/{session_id}")
async def ws_target(websocket: WebSocket, session_id: str):
    await websocket.accept()
    try:
        while True:
            msg = json.loads(await websocket.receive_text())
            session = translation_sessions.get(session_id)
            if not session:
                continue

            if msg["type"] == "setup":
                session.target_websocket = websocket
                if not await check_session_readiness_and_notify(session):
                    continue

            elif msg["type"] == "prompt":
                if not session.source_websocket:
                    continue
                prompt = msg["voicePrompt"]
                async for evt in translate_text_streaming(prompt,
                                                          session.target_language,
                                                          session.source_language):
                    await session.source_websocket.send_json(evt)
                if session.play_waiting_music:
                    await play_waiting_music(session.target_websocket)

    except Exception as e:
        logging.error(f"Target WS error: {e}")
    finally:
        await cleanup_session(session_id)

@app.post("/voice/source/{session_id}")
async def voice_source(request: Request, session_id: str):
    """Twilio webhook for source-language outbound call."""
    form = await request.form()
    host = request.headers.get("host")
    ws_url = f"wss://{host}/ws/source/{session_id}"
    session = translation_sessions.get(session_id)
    language = session.source_language if session else "es-ES"
    tts = session.source_tts_provider if session else "ElevenLabs"
    voice = session.source_voice if session else ""
    twiml = generate_conversation_relay_twiml(ws_url, language, tts, voice)
    return Response(content=twiml, media_type="text/xml")

@app.post("/voice/target/{session_id}")
async def voice_target(request: Request, session_id: str):
    """Twilio webhook for target-language outbound call."""
    form = await request.form()
    host = request.headers.get("host")
    ws_url = f"wss://{host}/ws/target/{session_id}"
    session = translation_sessions.get(session_id)
    language = session.target_language if session else  "en-US"
    tts = session.target_tts_provider if session else "ElevenLabs"
    voice = session.target_voice if session else ""
    twiml = generate_conversation_relay_twiml(ws_url, language, tts, voice)
    return Response(content=twiml, media_type="text/xml")

@app.post("/initiate-call")
async def initiate_call(request: Request):
    """Public API endpoint to start a new translation session."""
    data = await request.json()
    required = ("from_number", "to_number", "source_language", "target_language")
    if not all(k in data for k in required):
        return JSONResponse({"error": "Missing required fields"}, status_code=400)

    twilio_number = "+14432251592"
    if not twilio_number:
        return JSONResponse({"error": "Twilio phone not configured"}, status_code=500)

    session_id = f"session_{int(time.time())}_{data['from_number'].lstrip('+')}_{data['to_number'].lstrip('+')}"
    session = TranslationSession(session_id, "")
    session.source_phone_number = data["from_number"]
    session.target_phone_number = data["to_number"]
    session.source_language = data["source_language"]
    session.target_language = data["target_language"]
    session.source_tts_provider = data.get("source_tts_provider", "ElevenLabs")
    session.source_voice = data.get("source_voice", "")
    session.target_tts_provider = data.get("target_tts_provider", "ElevenLabs")
    session.target_voice = data.get("target_voice", "")
    session.host = request.headers.get("host")
    session.play_waiting_music = data.get("play_waiting_music", True)
    translation_sessions[session_id] = session

    # Kick off both outbound calls
    await create_outbound_call(session_id, session.host,
                               session.source_phone_number,
                               twilio_number, "/voice/source", False)
    await create_outbound_call(session_id, session.host,
                               session.target_phone_number,
                               twilio_number, "/voice/target", True)

    return JSONResponse({
        "status": "success",
        "session_id": session_id
    }, status_code=200)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8080")), reload=True)