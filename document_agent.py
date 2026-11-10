"""
Background document agent with local LLM (Ollama)
-------------------------------------------------
Watches a text file, waits for quiescence, sends the content to a
local Ollama model for constrained revision, and writes the result
atomically while suppressing self-triggered event loops.
"""

import hashlib
import os
import tempfile
import threading
import time
from pathlib import Path

import ollama                                      # pip install ollama
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
WATCH_DIRECTORY = Path.home() / "Documents"
TARGET_FILE     = "research_notes.txt"
OLLAMA_MODEL    = "llama3.2"                       # change to any local model
DEBOUNCE_SEC    = 5.0
MAX_TOKENS      = 4096                             # safety bound for long documents


SYSTEM_PROMPT = """You are a precise document editor. 
Your sole task is to improve the clarity, grammar, and logical flow of the 
supplied text while preserving the author's original meaning, terminology, 
and structure as far as possible.

Rules you must obey:
1. Return ONLY the revised document text.
2. Do not add introductions, explanations, markdown fences, or commentary.
3. Do not invent new sections or remove existing content unless the change 
   is required for grammatical correctness or obvious logical coherence.
4. If the text requires no improvement, return it unchanged.
"""


class DocumentAgent(FileSystemEventHandler):
    def __init__(self, target_path: str, model: str, debounce_seconds: float = 5.0):
        self.target_path = Path(target_path).resolve()
        self.model = model
        self.debounce_seconds = debounce_seconds
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()
        self._last_hash: str | None = None

    def on_modified(self, event):
        if event.is_directory:
            return
        if Path(event.src_path).resolve() != self.target_path:
            return

        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(
                self.debounce_seconds,
                self._process,
                args=(str(self.target_path),)
            )
            self._timer.start()

    def _process(self, file_path: str):
        print(f"[Agent] Quiescence reached – analysing {file_path}")
        try:
            content = Path(file_path).read_text(encoding="utf-8")
        except (PermissionError, OSError) as exc:
            print(f"[Agent] Read failed (file locked or missing): {exc}")
            return

        current_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if current_hash == self._last_hash:
            print("[Agent] Content identical to previous revision – skipping.")
            return

        if len(content) > MAX_TOKENS * 4:          # rough character estimate
            print("[Agent] Document exceeds safe length; truncation or chunking required.")
            return

        try:
            corrected = self._call_llm(content)
        except Exception as exc:
            print(f"[Agent] LLM inference failed: {exc}")
            return

        if corrected.strip() == content.strip():
            print("[Agent] Model returned no substantive changes.")
            self._last_hash = current_hash
            return

        # Atomic replacement
        try:
            directory = self.target_path.parent
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=directory,
                delete=False,
                suffix=".tmp"
            ) as tmp:
                tmp.write(corrected)
                tmp_path = tmp.name

            os.replace(tmp_path, self.target_path)
            self._last_hash = hashlib.sha256(corrected.encode("utf-8")).hexdigest()
            print(f"[Agent] Document revised and written ({len(corrected)} characters).")
        except Exception as exc:
            print(f"[Agent] Atomic write failed: {exc}")
            if "tmp_path" in locals() and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def _call_llm(self, text: str) -> str:
        """
        Sends the document to the local Ollama server under a tightly
        constrained system prompt and returns the model's reply.
        """
        response = ollama.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": text},
            ],
            options={
                "temperature": 0.2,          # low temperature for editorial consistency
                "num_predict": MAX_TOKENS,
            }
        )
        return response["message"]["content"].strip()


def main():
    target = WATCH_DIRECTORY / TARGET_FILE
    if not target.exists():
        target.write_text(
            "# Research notes\n\nBegin drafting here. The agent will refine "
            "the text after each period of inactivity.\n",
            encoding="utf-8"
        )
        print(f"[Setup] Created starter file: {target}")

    handler = DocumentAgent(
        target_path=str(target),
        model=OLLAMA_MODEL,
        debounce_seconds=DEBOUNCE_SEC
    )
    observer = Observer()
    observer.schedule(handler, path=str(WATCH_DIRECTORY), recursive=False)
    observer.start()

    print(f"[*] Local LLM agent active")
    print(f"    Target : {target}")
    print(f"    Model  : {OLLAMA_MODEL}")
    print(f"    Debounce: {DEBOUNCE_SEC}s")
    print("    Edit and save the file; the agent reacts after inactivity.")
    print("    Ctrl-C to terminate.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Shutting down observer.")
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
