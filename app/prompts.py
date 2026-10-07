"""All prompts live here. Edit this file to change tutor behaviour."""
from app.config import LANGS


def tutor_system(lang: str) -> str:
    name = LANGS.get(lang, "English")
    return (
        "You are an academic assistant for Nigerian students. You are an AI, not a human teacher. "
        f"Reply ONLY in {name}. Be accurate, clear and concise (under 120 words). "
        "Explain simply, and use a short example when it helps, with Nigerian context where relevant. "
        "If you are not sure, say so honestly. Never invent references, sources or facts."
    )


def question_messages(question: str, lang: str, history: list | None = None) -> list:
    msgs = [{"role": "system", "content": tutor_system(lang)}]
    msgs += list(history or [])
    msgs.append({"role": "user", "content": question})
    return msgs


def summary_messages(text: str, lang: str) -> list:
    name = LANGS.get(lang, "English")
    return [{"role": "system", "content": f"Summarize the lesson below in {name}, in under 120 words, "
                                          "as short bullet points. Do not add facts that are not in the text."},
            {"role": "user", "content": text}]
