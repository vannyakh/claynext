# Rule: Architecture & Threading Model

## 1. Asynchronous Execution Pattern
Any task taking more than 50 milliseconds (audio/video extraction, Whisper transcription, TTS synthesis, translation, OCR, network I/O, heavy file reads) **MUST** run on a background thread.

### The `Worker` Standard
Use `Worker` from [worker.py](file:///Users/vannya/Desktop/MinJ/src/claynext/core/worker.py):

```python
from PySide6.QtCore import QThreadPool
from claynext.core.worker import Worker

def _start_heavy_task(self, media_path: str):
    self.set_busy(True)
    worker = Worker(self._heavy_task_logic, media_path)
    worker.signals.started.connect(self._on_task_started)
    worker.signals.progress.connect(self._on_task_progress) # (int percent, str status_msg)
    worker.signals.result.connect(self._on_task_result)     # object
    worker.signals.error.connect(self._on_task_error)       # (str error_msg, str stack_trace)
    worker.signals.finished.connect(self._on_task_finished)
    QThreadPool.globalInstance().start(worker)

def _heavy_task_logic(self, media_path: str, progress_callback=None):
    # progress_callback(percent, status_message) is automatically injected by Worker
    if progress_callback:
        progress_callback(10, "Extracting audio...")
    # ... heavy computation ...
    if progress_callback:
        progress_callback(100, "Done")
    return {"status": "ok"}
```

## 2. Thread Safety Rules
- **NEVER** call UI widget methods (e.g. `self.label.setText(...)`, `self.table.setRowCount(...)`) from inside `_heavy_task_logic` or any function running on the worker thread.
- **ALWAYS** emit results or progress to Qt Signals, and handle widget updates strictly in Qt Slots running on the main GUI thread.

## 3. Separation of Concerns
- `src/claynext/core/`: Headless engine logic, data structures, and CLI tools. Must remain free of PySide6 widget imports (except Qt core data classes/signals if specifically designed for workers).
- `src/claynext/gui/`: PySide6 views, custom widgets, styling, and dialogs.
- `src/claynext/constants/`: Enums, color tokens, layout measurements, and tool metadata.
- `src/claynext/utils/`: Path helpers, system configuration, and logging.
