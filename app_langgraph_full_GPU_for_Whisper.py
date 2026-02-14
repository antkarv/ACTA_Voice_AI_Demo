import os
import tempfile
import gradio as gr
import re
import win32com.client
import asyncio
import edge_tts
import json
import requests

from faster_whisper import WhisperModel
from ollama import chat
from dotenv import load_dotenv
load_dotenv()


# -----------------------
# CONFIG
# -----------------------
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
WHISPER_SIZE = os.getenv("WHISPER_SIZE", "medium")  # tiny, small, medium, large
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")      # "cuda" if available else "cpu"
WHISPER_COMPUTE = os.getenv("WHISPER_COMPUTE", "int8")   # "float16" often for cuda, "int8" for cpu

# Cloud LLM (Groq - OpenAI compatible)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("LLM_MODEL_GROQ", "openai/gpt-oss-120b")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")

DEFAULT_LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()  # "ollama" or "groq"


#ACKS = ["Μάλιστα…", "Ας το δούμε…", "Καλή ερώτηση…", "Βεβαίως…", "Ας το εξηγήσω…"]

SYSTEM_PROMPT = """Είσαι μια ευγενική, ψύχραιμη και έμπειρη βοηθός τηλεπικοινωνιών.
Μιλάς ΠΑΝΤΑ άψογα ελληνικά.

ΑΥΣΤΗΡΟΙ ΚΑΝΟΝΕΣ (πολύ σημαντικό):
- Απάντησε ΜΟΝΟ στα ελληνικά. ΜΗ χρησιμοποιείς αγγλικές λέξεις ή αγγλικές προτάσεις. Μην ξεπερνάς τις 1000 λέξεις στην απάντηση. 
- Δώσε μια σύντομη, πρακτική περίληψη όχι πάνω από 1000 λέξεις.
- Μην χρησιμοποιείς σύπτυξη (π.χ. αντί γι'αυτό, δώσε για αυτό).
- Αν εμφανιστεί τεχνικός όρος, δώσε ελληνική εξήγηση. (π.χ. «διαφωνία θορύβου», «εξασθένηση»)
- Για συντομογραφίες όπως VDSL, γράψε: «V D S L» (με κενά), για να ακούγεται σωστά στο TTS.
- Μίλα όπως θα μιλούσε ένας μηχανικός προφορικά: σύντομες προτάσεις, χωρίς “έκθεση”.
- Μην αναφέρεις ότι είσαι μοντέλο/AI. Μην αναφέρεις πολιτικές.

ΔΟΜΗ ΑΠΑΝΤΗΣΗΣ:
1) Ξεκίνα ΠΑΝΤΑ με μια συντομη φιλική εισαγωγή αλλά σε επαγγελματικό τόνο.
2) Δώσε την κύρια απάντηση σε 3–6 σύντομες προτάσεις.
3) Αν χρειάζεται, πρόσθεσε 2–4 bullets με πρακτικά σημεία.

ΑΚΡΙΒΕΙΑ / ΑΒΕΒΑΙΟΤΗΤΑ:
- Μην επινοείς εμπορικές/συμβατικές εγγυήσεις παρόχων.
- Αν δεν είσαι σίγουρη, πες καθαρά: «Δεν είμαι σίγουρη για ορισμένες λεπτομέρειες.» και μείνε σε γενικές αρχές.

ΕΙΔΙΚΑ ΓΙΑ VDSL:
Εξήγησε με πρακτικά παραδείγματα: απόσταση από καμπίνα, ποιότητα χαλκού, παρεμβολές (crosstalk),
εσωτερική καλωδίωση, λόγος σήματος προς θόρυβο (SNR), εξασθένηση.

VERY IMPORTANT: If you support thinking / chain-of-thought, ALWAYS use it to reason step-by-step before answering 
the question, but don't show the reasoning to the user and also don't overthink (check your available tokens) because 
the user must have a final answer anyway.
"""


CONFIDENCE_PROMPT = """Δώσε ΜΟΝΟ μία λέξη από: ΧΑΜΗΛΗ, ΜΕΤΡΙΑ, ΥΨΗΛΗ.
Αξιολόγησε την εμπιστοσύνη της απάντησης που δόθηκε από έναν τεχνικό τηλεπικοινωνιών βάσει της ερώτησης του χρήστη.
- ΥΨΗΛΗ: αν η απάντηση είναι σαφής, ακριβής και πλήρης.
- ΜΕΤΡΙΑ: αν η απάντηση είναι γενική ή έχει μικρές ανακρίβειες.
- ΧΑΜΗΛΗ: αν η απάντηση είναι ασαφής, ανακριβής ή ελλιπής.
"""


# -----------------------
# Load STT once
# -----------------------
stt_model = WhisperModel(WHISPER_SIZE, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE)


def groq_chat(messages, *, model: str | None = None, max_tokens: int = 2000, temperature: float = 0.2) -> tuple[str, dict]:
    """
    Groq OpenAI-compatible /chat/completions.
    returns: (reply_text, usage_dict)
    """
    
    if not GROQ_API_KEY:
        return "[LLM error] GROQ_API_KEY missing", {}

    url = f"{GROQ_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model or GROQ_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": 0.9,
    }
    print(f"[DEBUG] Groq chat call, model={model}, max_tokens={max_tokens}, temperature={temperature}")

    try:
        resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=120)
        resp.raise_for_status()
        data = resp.json()
        reply = (data["choices"][0]["message"]["content"] or "").strip()
        usage = data.get("usage") or {}
        return reply, usage
    except Exception as e:
        return f"[LLM error] {e}", {}

def llm_answer(user_text: str, provider: str) -> str:
    provider = (provider or "ollama").lower().strip()

    if provider == "groq":
        reply, _usage = groq_chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            max_tokens=2000,
            temperature=0.2,
        )
        print(f"[DEBUG] Groq reply: {reply}")
        ans = (reply or "").strip()

        # If Groq key missing or error -> return message (and keep demo alive)
        if ans.startswith("[LLM error]"):
            return ans

        # Greek-only guard (same idea as your Ollama guard)
        latin = sum(ch.isascii() and ch.isalpha() for ch in ans)
        if latin > 20:
            reply2, _ = groq_chat(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Ξαναγράψε την απάντηση ΜΟΝΟ στα ελληνικά, χωρίς καθόλου αγγλικές λέξεις εκτός από τις λέξεις που είναι τεχνικοί όροι:\n\n{ans}"},
                ],
                max_tokens=2000,
                temperature=0.15,
            )
            if reply2 and not reply2.startswith("[LLM error]"):
                ans = reply2.strip()
        return ans

    # default: ollama
    ollama_reply = ollama_answer(user_text)
    print(f"[DEBUG] Ollama reply: {ollama_reply}")
    return ollama_reply


def llm_confidence(user_text: str, answer_text: str, provider: str) -> str:
    provider = (provider or "ollama").lower().strip()

    if provider == "groq":
        reply, _usage = groq_chat(
            [
                {"role": "system", "content": CONFIDENCE_PROMPT},
                {"role": "user", "content": f"Ερώτηση χρήστη:\n{user_text}\n\nΑπάντηση:\n{answer_text}"},
            ],
            max_tokens=220,
            temperature=0.0,
        )
        print(f"[DEBUG] Groq confidence reply: {reply}")
        if not reply or reply.startswith("[LLM error]"):
            return "Χαμηλή"

        label = reply.strip().upper()
        if "ΥΨΗ" in label:
            return "Υψηλή"
        if "ΜΕΤΡ" in label:
            return "Μέτρια"
        return "Χαμηλή"

    # default: ollama
    ollama_confidence_reply = ollama_confidence(user_text, answer_text)
    print(f"[DEBUG] Ollama confidence reply: {ollama_confidence_reply}")
    return ollama_confidence_reply


def transcribe_audio(audio_path: str) -> str:
    segments, _info = stt_model.transcribe(
        audio_path,
        language="el",
        task="transcribe",
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
        beam_size=5,
        best_of=5,
    )
    text = " ".join(seg.text.strip() for seg in segments).strip()
    return text


def ollama_answer(user_text: str) -> str:
    print(f"[DEBUG] ollama_answer (model={OLLAMA_MODEL})")
    resp = chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
        options={
            "temperature": 0.15,
            "top_p": 0.9,
            "repeat_penalty": 1.1,
            "num_predict": 20000,   # keeps answers short for voice
        },
    )
    ans = (resp["message"]["content"] or "").strip()
    # very simple guard: if too much Latin text, ask model to rephrase Greek-only
    latin = sum(ch.isascii() and ch.isalpha() for ch in ans)
    if latin > 20:
        resp2 = chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Ξαναγράψε την απάντηση ΜΟΝΟ στα ελληνικά, χωρίς καθόλου αγγλικές λέξεις εκτός από τις λέξεις που είναι τεχνικοί όροι::\n\n{ans}"},
            ],
            options={"temperature": 0.15, "top_p": 0.9, "repeat_penalty": 1.1, "num_predict": 2000, },
            think=True
        )
        ans = (resp2["message"]["content"] or "").strip()

    return ans


def ollama_confidence(user_text: str, answer_text: str) -> str:
    print(f"[DEBUG] ollama_confidence (model={OLLAMA_MODEL})")
    resp = chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": CONFIDENCE_PROMPT},
            {"role": "user", "content": f"Ερώτηση χρήστη:\n{user_text}\n\nΑπάντηση:\n{answer_text}\n\nΜΟΝΟ η λέξη:"},
        ],
        options={"temperature": 0.0, "top_p": 0.9, "repeat_penalty": 1.1, "num_predict": 20000, },
        think=True
    )
    label = (resp["message"]["content"] or "").strip().upper()
    if "ΥΨΗ" in label:
        return "Υψηλή"
    if "ΜΕΤΡ" in label:
        return "Μέτρια"
    return "Χαμηλή"


def tts_sapi_to_wav(text: str) -> str:
    """
    Windows SAPI TTS -> WAV file (no external binaries).
    Tries to pick a Greek female voice if available.
    """
    fd, out_wav = tempfile.mkstemp(suffix=".wav")
    os.close(fd)

    # Clean text a bit for TTS
    t = (text or "").strip()
    t = re.sub(r"\s+", " ", t)

    speaker = win32com.client.Dispatch("SAPI.SpVoice")

    # Try to select a Greek voice (prefer female when possible)
    # NOTE: Available voices depend on installed Windows language packs.
    voices = speaker.GetVoices()
    # Force Zira (female) if available
    for i in range(voices.Count):
        v = voices.Item(i)
        if "zira" in (v.GetDescription() or "").lower():
            speaker.Voice = v
            break

    selected = None

    for i in range(voices.Count):
        v = voices.Item(i)
        desc = (v.GetDescription() or "").lower()
        # heuristics: greek + (female if mentioned)
        if "greek" in desc or "ελλην" in desc or "el-gr" in desc:
            selected = v
            if "female" in desc or "woman" in desc or "γυν" in desc:
                break

    if selected is not None:
        speaker.Voice = selected

    # Output to WAV file
    stream = win32com.client.Dispatch("SAPI.SpFileStream")
    # 3 = SSFMCreateForWrite
    stream.Open(out_wav, 3)
    speaker.AudioOutputStream = stream

    speaker.Speak(t)

    stream.Close()
    speaker.AudioOutputStream = None

    return out_wav


EDGE_TTS_VOICE = os.getenv("EDGE_TTS_VOICE", "el-GR-AthinaNeural")


def tts_edge_to_wav(text: str) -> str:
    """
    Edge Neural TTS (Greek) -> WAV
    No API key, online service.
    """
    fd, out_wav = tempfile.mkstemp(suffix=".wav")
    os.close(fd)

    async def _run():
        communicate = edge_tts.Communicate(
            text=(text or "").strip(),
            voice=EDGE_TTS_VOICE,
            rate="+0%",
            volume="+0%"
        )
        await communicate.save(out_wav)

    asyncio.run(_run())
    return out_wav

def tts_to_wav(text: str) -> str:
    """
    Primary: Edge TTS (Greek neural)
    Fallback: Windows SAPI (female)
    """
    try:
        return tts_edge_to_wav(text)
    except Exception as e:
        print("[WARN] Edge TTS failed, falling back to SAPI:", e)
        return tts_sapi_to_wav(text)



# ----------------------------
# LangGraph minimal integration (linear voice pipeline, no streaming)
# ----------------------------
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END

class VoiceState(TypedDict, total=False):
    audio_path: Optional[str]
    provider: str
    transparency: bool
    user_text: str
    answer_text: str
    confidence: str
    out_wav: Optional[str]

def stt_node(state: VoiceState) -> VoiceState:
    audio_path = state.get("audio_path")
    state["user_text"] = transcribe_audio(audio_path) if audio_path else ""
    return state

def answer_node(state: VoiceState) -> VoiceState:
    provider = state.get("provider", "groq")
    user_text = state.get("user_text", "")
    state["answer_text"] = llm_answer(user_text, provider)
    return state

def confidence_node(state: VoiceState) -> VoiceState:
    provider = state.get("provider", "groq")
    user_text = state.get("user_text", "")
    answer_text = state.get("answer_text", "")
    conf = llm_confidence(user_text, answer_text, provider)
    state["confidence"] = (conf or "").strip()

    # If confidence low, strongly encourage explicit uncertainty at the top (without rewriting everything)
    if state["confidence"] == "Χαμηλή" and "Δεν είμαι σίγουρη" not in answer_text:
        state["answer_text"] = "Δεν είμαι σίγουρη 100% — μπορεί να χρειάζονται περισσότερες πληροφορίες.\n\n" + answer_text
    return state

def tts_node(state: VoiceState) -> VoiceState:
    answer_text = state.get("answer_text", "")
    state["out_wav"] = tts_to_wav(answer_text) if answer_text else None
    return state

_voice_graph = StateGraph(VoiceState)
_voice_graph.add_node("stt", stt_node)
_voice_graph.add_node("answer", answer_node)
_voice_graph.add_node("confidence", confidence_node)
_voice_graph.add_node("tts", tts_node)
_voice_graph.set_entry_point("stt")
_voice_graph.add_edge("stt", "answer")
_voice_graph.add_edge("answer", "confidence")
_voice_graph.add_edge("confidence", "tts")
_voice_graph.add_edge("tts", END)

VOICE_APP = _voice_graph.compile()


def run_pipeline(audio, transparency: bool, provider: str):
    """
    Non-streaming pipeline (Option A):
    STT -> LLM answer -> confidence -> TTS, executed via LangGraph.
    Gradio audio input is configured with type='filepath' in the UI.
    """
    if not audio:
        return "Σφάλμα: δεν υπάρχει ήχος.", "", "", "Χαμηλή", None

    init_state: VoiceState = {
        "audio_path": audio,
        "provider": provider,
        "transparency": bool(transparency),
    }

    final_state: VoiceState = VOICE_APP.invoke(init_state)

    user_text = final_state.get("user_text", "")
    answer_text = final_state.get("answer_text", "")
    conf = final_state.get("confidence", "")
    out_wav = final_state.get("out_wav", None)

    # Preserve your UI behavior: hide transcript/answer/confidence when transparency is off
    stt_text = user_text if transparency else ""
    ai_text = answer_text if transparency else ""
    conf_text = conf if transparency else ""

    status = "Ολοκληρώθηκε."
    # If LLM error, expose it in status and skip TTS
    if isinstance(answer_text, str) and answer_text.startswith("[LLM error]"):
        status = f"Σφάλμα LLM ({provider}): {answer_text}"
        out_wav = None

    if not user_text.strip():
        status = "Δεν κατάλαβα καθαρά. Δοκίμασε ξανά."
        return status, "", "", "Χαμηλή", None

    return status, stt_text, ai_text, conf_text, out_wav

with gr.Blocks(title="ACTA Voice AI Demo") as demo:
    gr.Markdown("# ACTA Voice AI Demo (Greek)\n### • Female voice • Ollama or Groq (live switch)")

    with gr.Row():
        provider_dd = gr.Dropdown(
        label="LLM Provider",
        choices=["ollama", "groq"],
        value=DEFAULT_LLM_PROVIDER if DEFAULT_LLM_PROVIDER in ["ollama", "groq"] else "ollama",
        interactive=True,
        )
        transparency = gr.Checkbox(label="Διαφάνεια (για engineers)", value=False)


    with gr.Row():
        audio_in = gr.Audio(
            sources=["microphone"],
            type="filepath",
            label="🎤 Πάτα record, μίλα στα ελληνικά, και σταμάτα",
        )

    btn = gr.Button("▶️ Εκτέλεση (STT → LLM → TTS)", variant="primary")
    status = gr.Textbox(label="Κατάσταση", value="Έτοιμο.", interactive=False)

    # Hidden panel (B)
    with gr.Accordion("Πίνακας Διαφάνειας (Transcript / Answer / Confidence)", open=False):
        stt_text = gr.Textbox(label="Transcript (STT)", lines=3)
        ai_text = gr.Textbox(label="AI Answer (Text)", lines=8)
        conf = gr.Textbox(label="Confidence", interactive=False)

    audio_out = gr.Audio(label="🔊 AI Voice Output", type="filepath")
    clear_btn = gr.Button("🧹 Νέα ερώτηση (Καθάρισε)")
    clear_btn.click(
        fn=lambda: (None, "Έτοιμο.", "", "", "", None),
        inputs=[],
        outputs=[audio_in, status, stt_text, ai_text, conf, audio_out],
    )


    btn.click(
        fn=run_pipeline,
        inputs=[audio_in, transparency, provider_dd],
        outputs=[status, stt_text, ai_text, conf, audio_out],
    )

#demo.queue().launch(server_name="127.0.0.1", server_port=7860)
if __name__ == "__main__":
    demo.queue().launch(server_name="127.0.0.1", server_port=7860, share=True)

