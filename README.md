# 🎙️ ACTA Voice AI Demo  
### Greek Telecom Voice Assistant powered by LangGraph

An end-to-end Voice AI system that answers telecom-related questions in Greek using a structured pipeline:

- 🎤 Speech-to-Text (Faster-Whisper)
- 🧠 LLM (Ollama or Groq – runtime switch)
- 📊 Confidence evaluation
- 🔊 Neural Text-to-Speech (Edge TTS)
- 🔁 LangGraph orchestration
- 🖥️ Gradio interface

Designed as an AI portfolio demo demonstrating graph-based orchestration, multi-provider LLM support, and voice interaction.

---
```mermaid
flowchart TB
    A[🎤 Audio Input]

    subgraph G["LangGraph VoiceState"]
        B[stt<br/>audio_path → user_text]
        C[answer<br/>LLM call]
        D[confidence<br/>LLM call]
        E[tts<br/>answer_text → out_wav]
        Z((END))

        B --> C --> D --> E --> Z
    end

    F[🔊 Voice Output]

    A --> B
    E --> F

```


## 🖥️ Demo Interface

![Voice AI UI](assets/UI.PNG)
