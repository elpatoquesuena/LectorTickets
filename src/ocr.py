"""On-device OCR for Android using Google ML Kit through PyJNIus.

The OCR runs locally on the phone: ticket images are not uploaded to a server.
On non-Android platforms the module reports that native ML Kit is unavailable.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path


class OCRUnavailable(RuntimeError):
    pass


def _android_ocr(path: str, timeout: float = 30.0) -> str:
    try:
        from jnius import PythonJavaClass, autoclass, attach_thread, java_method
    except Exception as exc:
        raise OCRUnavailable("No se pudo cargar el puente Android (PyJNIus).") from exc

    activity_host_class = os.getenv("MAIN_ACTIVITY_HOST_CLASS_NAME")
    if not activity_host_class:
        raise OCRUnavailable("Falta la actividad Android de Flet.")

    class SuccessListener(PythonJavaClass):
        __javainterfaces__ = ["com/google/android/gms/tasks/OnSuccessListener"]
        __javacontext__ = "app"

        def __init__(self, state):
            super().__init__()
            self.state = state

        @java_method("(Ljava/lang/Object;)V")
        def onSuccess(self, result):
            try:
                attach_thread()
            except Exception:
                pass
            try:
                self.state["text"] = str(result.getText() or "")
            except Exception as exc:
                self.state["error"] = str(exc)
            finally:
                self.state["done"].set()

    class FailureListener(PythonJavaClass):
        __javainterfaces__ = ["com/google/android/gms/tasks/OnFailureListener"]
        __javacontext__ = "app"

        def __init__(self, state):
            super().__init__()
            self.state = state

        @java_method("(Ljava/lang/Exception;)V")
        def onFailure(self, error):
            try:
                attach_thread()
            except Exception:
                pass
            self.state["error"] = str(error)
            self.state["done"].set()

    ActivityHost = autoclass(activity_host_class)
    activity = ActivityHost.mActivity
    context = activity.getApplicationContext()

    Uri = autoclass("android.net.Uri")
    File = autoclass("java.io.File")
    TextRecognition = autoclass("com.google.mlkit.vision.text.TextRecognition")
    TextRecognizerOptions = autoclass("com.google.mlkit.vision.text.latin.TextRecognizerOptions")
    InputImage = autoclass("com.google.mlkit.vision.common.InputImage")

    image_file = File(str(Path(path).resolve()))
    uri = Uri.fromFile(image_file)
    image = InputImage.fromFilePath(context, uri)
    recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)

    state = {"done": threading.Event(), "text": "", "error": None}
    success = SuccessListener(state)
    failure = FailureListener(state)

    try:
        recognizer.process(image).addOnSuccessListener(success).addOnFailureListener(failure)
        if not state["done"].wait(timeout):
            raise OCRUnavailable("El OCR tardó demasiado. Probá con una foto más nítida.")
        if state["error"]:
            raise OCRUnavailable(f"ML Kit no pudo leer la imagen: {state['error']}")
        text = state["text"].strip()
        if not text:
            raise OCRUnavailable("No se encontró texto legible en el ticket.")
        return text
    finally:
        try:
            recognizer.close()
        except Exception:
            pass


def recognize_image(path: str) -> str:
    """Recognize text from a local image. Android is the supported runtime."""
    if not Path(path).exists():
        raise OCRUnavailable("La imagen del ticket no existe.")
    if os.getenv("ANDROID_ARGUMENT") or os.getenv("MAIN_ACTIVITY_HOST_CLASS_NAME"):
        return _android_ocr(path)
    raise OCRUnavailable("El OCR integrado usa Google ML Kit y está disponible en Android.")
