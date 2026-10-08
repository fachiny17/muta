import collections
import io
import os
import re
import subprocess
import threading

import numpy as np
import soundfile as sf
import torch
from fastapi import FastAPI, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel
from transformers import (AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig,
                          WhisperForConditionalGeneration, WhisperProcessor)

LLM_ID = "NCAIR1/N-ATLaS"
ASR_IDS = {"ha": "NCAIR1/Hausa-ASR", "yo": "NCAIR1/Yoruba-ASR",
           "ig": "NCAIR1/Igbo-ASR", "en": "NCAIR1/NigerianAccentedEnglish"}  # verify against the model cards
MAX_ASR_RESIDENT = 2


def _secret(name: str) -> str:
    """Environment variable first, then Colab Secrets, then Kaggle Secrets."""
    if os.getenv(name):
        return os.environ[name]
    try:
        from google.colab import userdata  # Colab
        return userdata.get(name) or ""
    except Exception:
        pass
    try:
        from kaggle_secrets import UserSecretsClient  # Kaggle
        return UserSecretsClient().get_secret(name)
    except Exception:
        return ""


KEY = _secret("GATEWAY_KEY")
state = {"tok": None, "llm": None, "llm_error": None}
asr_cache = collections.OrderedDict()
asr_errors = {}
lock = threading.Lock()  # one GPU job at a time keeps memory predictable

app = FastAPI(title="N-ATLAS gateway")


def load_llm() -> None:
    from huggingface_hub import login
    login(_secret("HF_TOKEN"))
    try:
        bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.float16)
        state["tok"] = AutoTokenizer.from_pretrained(LLM_ID)
        state["llm"] = AutoModelForCausalLM.from_pretrained(LLM_ID, quantization_config=bnb, device_map="auto")
    except Exception as e:
        state["llm_error"] = str(e)[:300]
        raise


def predownload() -> None:
    """Download the ASR weights to disk now so the first request per language is not slow."""
    from huggingface_hub import snapshot_download
    for lang, rid in ASR_IDS.items():
        try:
            snapshot_download(rid)
            print(f"downloaded {rid}")
        except Exception as e:
            asr_errors[lang] = f"download failed: {str(e)[:200]}"
            print(f"WARNING: could not download {rid}: {str(e)[:200]}")


def _auth(key):
    if not KEY or key != KEY:
        raise HTTPException(401, "bad or missing api key")


def get_asr(lang: str):
    if lang not in ASR_IDS:
        raise HTTPException(400, f"lang must be one of {list(ASR_IDS)}")
    if lang in asr_cache:
        asr_cache.move_to_end(lang)
        return asr_cache[lang]
    try:
        rid = ASR_IDS[lang]
        m = WhisperForConditionalGeneration.from_pretrained(rid, torch_dtype=torch.float16).cuda().eval()
        p = WhisperProcessor.from_pretrained(rid)
    except Exception as e:  # report honestly instead of pretending the language works
        asr_errors[lang] = str(e)[:300]
        raise HTTPException(503, f"ASR model for '{lang}' failed to load: {asr_errors[lang]}")
    asr_errors.pop(lang, None)
    asr_cache[lang] = (m, p)
    while len(asr_cache) > MAX_ASR_RESIDENT:
        _, (old, _) = asr_cache.popitem(last=False)
        del old
        torch.cuda.empty_cache()
    return asr_cache[lang]


@app.get("/health")
def health(x_api_key: str = Header(None)):
    _auth(x_api_key)
    return {"ok": state["llm"] is not None, "llm_loaded": state["llm"] is not None,
            "llm_error": state["llm_error"], "asr_loaded": list(asr_cache), "asr_errors": asr_errors}


@app.post("/v1/asr")
async def asr(file: UploadFile, lang: str = Form(...), x_api_key: str = Header(None)):
    _auth(x_api_key)
    audio, sr = sf.read(io.BytesIO(await file.read()), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != 16000:
        raise HTTPException(400, "send 16 kHz mono wav")
    with lock:
        m, p = get_asr(lang)
        feats = p(audio, sampling_rate=16000, return_tensors="pt").input_features.to("cuda", torch.float16)
        with torch.no_grad():
            ids = m.generate(feats, max_new_tokens=220)  # if output is gibberish, follow the model card's generation settings
    return {"text": p.batch_decode(ids, skip_special_tokens=True)[0].strip()}


class ChatReq(BaseModel):
    messages: list[dict]
    max_tokens: int = 300
    temperature: float = 0.3


@app.post("/v1/chat")
def chat(req: ChatReq, x_api_key: str = Header(None)):
    _auth(x_api_key)
    if state["llm"] is None:
        raise HTTPException(503, "LLM not loaded")
    tok, llm = state["tok"], state["llm"]
    eot = tok.convert_tokens_to_ids("<|eot_id|>")
    eos = [tok.eos_token_id] + ([eot] if isinstance(eot, int) and eot != tok.unk_token_id else [])
    with lock:
        ids = tok.apply_chat_template(req.messages, add_generation_prompt=True, return_tensors="pt").to(llm.device)
        with torch.no_grad():
            out = llm.generate(ids, max_new_tokens=req.max_tokens, do_sample=req.temperature > 0.05,
                               temperature=max(req.temperature, 0.05), top_p=0.9, eos_token_id=eos)
    return {"reply": tok.decode(out[0][ids.shape[-1]:], skip_special_tokens=True).strip()}


def start_in_notebook(port: int = 8000) -> str:
    """Kaggle/Colab helper: load the LLM, start uvicorn, open a Cloudflare quick tunnel."""
    import nest_asyncio
    import uvicorn
    if not KEY:
        raise RuntimeError("GATEWAY_KEY secret is missing (add it in Colab/Kaggle Secrets and enable notebook access)")
    load_llm()
    predownload()
    nest_asyncio.apply()
    threading.Thread(target=uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=port)).run, daemon=True).start()
    subprocess.run("wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/"
                   "cloudflared-linux-amd64 -O cloudflared && chmod +x cloudflared", shell=True)
    tun = subprocess.Popen(["./cloudflared", "tunnel", "--url", f"http://localhost:{port}"],
                           stderr=subprocess.PIPE, text=True)
    url = None
    for line in tun.stderr:
        m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
        if m:
            url = m.group(0)
            break
    threading.Thread(target=lambda: [None for _ in tun.stderr], daemon=True).start()
    print("GATEWAY_URL =", url)
    start_heartbeat(url)
    return url


def start_heartbeat(url: str, every: int = 60) -> None:
    """If APP_URL and ADMIN_KEY secrets exist, keep telling the hosted app our current URL.

    This removes the manual 'copy the new URL into the environment' step after every restart,
    and also recovers automatically when the hosted app wakes from sleep or redeploys.
    """
    app_url, admin = _secret("APP_URL").rstrip("/"), _secret("ADMIN_KEY")
    if not (app_url and admin):
        print("APP_URL / ADMIN_KEY secrets not set: set GATEWAY_URL on the app manually.")
        return
    import json
    import time
    import urllib.request

    def loop():
        while True:
            try:
                req = urllib.request.Request(app_url + "/internal/gateway", data=json.dumps({"url": url}).encode(),
                                             headers={"Content-Type": "application/json", "x-admin-key": admin}, method="POST")
                urllib.request.urlopen(req, timeout=20).read()
            except Exception as e:
                print("heartbeat failed:", str(e)[:120])
            time.sleep(every)

    threading.Thread(target=loop, daemon=True).start()
    print("Heartbeat started: registering", url, "with", app_url)
