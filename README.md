# Local Document Agent

A background AI agent that continuously inspects and refines text documents using a local large language model (via Ollama). The agent is event-driven, uses file-system notifications, applies intelligent debouncing, and performs atomic writes while protecting against infinite event loops.

## Architecture Overview

```
[OS File System Event]
         │
         ▼
[Debouncer & Lock Resolution]
         │
         ▼
[Document Parsing Layer (.txt / .md)]
         │
         ▼
[LLM Inference / Semantic Correction Engine (Ollama)]
         │
         ▼
[Atomic Write & Conflict Mitigation]
```

## Features

- **Event-driven**: Uses `watchdog` instead of polling
- **Debouncing**: Waits for a period of inactivity (default 5 s) before processing
- **Content-hash guard**: Prevents the agent from re-processing its own writes
- **Atomic writes**: Temporary file + `os.replace` to avoid partial writes
- **Constrained prompting**: System prompt forces the model to return only the revised document
- **Local-first**: Works entirely offline once Ollama and a model are installed

## Prerequisites

1. **Python 3.10+**
2. **Ollama** installed and running ([https://ollama.com](https://ollama.com))
3. A local model pulled, e.g.:

```bash
ollama pull llama3.2
```

## Installation

```bash
git clone https://github.com/Mohamadx2/local-document-agent.git
cd local-document-agent
pip install -r requirements.txt
```

## Usage

1. Edit the configuration block at the top of `document_agent.py`:

```python
WATCH_DIRECTORY = Path.home() / "Documents"
TARGET_FILE     = "research_notes.txt"
OLLAMA_MODEL    = "llama3.2"          # any model you have pulled
DEBOUNCE_SEC    = 5.0
```

2. Run the agent:

```bash
python document_agent.py
```

3. Open (or create) the target file in any editor, type, and save. After the debounce interval of inactivity the agent will send the content to the local model and, if changes are proposed, rewrite the file atomically.

## Important Limitations

- Designed primarily for plain-text and Markdown files. Live Microsoft Word (`.docx`) documents are protected by exclusive locks; the agent will refuse to write while the file is open in Word.
- Full-document inference on every save is simple but does not scale well to very long manuscripts. Future versions should implement paragraph-level or section-level change detection.
- The model may occasionally ignore the “return only the text” instruction. A light post-processing filter can be added if needed.

## Design Notes

The original architecture discussion emphasised three failure modes that naïve implementations commonly encounter:

1. **File-handle collisions** with Microsoft Word
2. **Infinite recursion** caused by the agent writing back to the watched file
3. **Context-window inflation** on growing documents

This repository addresses the first two comprehensively and documents the third as future work.

## License

MIT
