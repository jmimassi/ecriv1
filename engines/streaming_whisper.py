"""faster-whisper streaming engine — chunk-based transcription."""

import numpy as np

SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2
CHUNK_DURATION = 3  # seconds per chunk
CHUNK_BYTES = SAMPLE_RATE * BYTES_PER_SAMPLE * CHUNK_DURATION


class StreamingWhisper:
    def __init__(self, model_size="medium"):
        self.name = f"Whisper {model_size}"
        self._model_size = model_size
        self._model = None
        self._chunk_buf = bytearray()

    @property
    def loaded(self):
        return self._model is not None

    def load(self):
        from faster_whisper import WhisperModel
        self._model = WhisperModel(
            self._model_size, device="cuda", compute_type="int8",
        )

    def reset(self):
        self._chunk_buf = bytearray()

    def feed(self, audio_int16: bytes):
        """Feed 16kHz int16 mono audio.
        When a chunk is full (~3s), transcribe it and return as final.
        """
        self._chunk_buf.extend(audio_int16)

        if len(self._chunk_buf) >= CHUNK_BYTES:
            text = self._transcribe(self._chunk_buf)
            self._chunk_buf = bytearray()
            if text:
                return text, None

        return None, None

    def finalize(self):
        """Transcribe remaining audio in the current chunk only."""
        if len(self._chunk_buf) >= 1600:
            text = self._transcribe(self._chunk_buf)
            self._chunk_buf = bytearray()
            return text if text else None
        self._chunk_buf = bytearray()
        return None

    def _transcribe(self, buf):
        audio = np.frombuffer(bytes(buf), dtype=np.int16)
        audio_f32 = audio.astype(np.float32) / 32768.0
        segments, _ = self._model.transcribe(
            audio_f32,
            language="fr",
            condition_on_previous_text=False,
            no_speech_threshold=0.4,
            hallucination_silence_threshold=1.0,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )
        parts = []
        for seg in segments:
            if seg.no_speech_prob > 0.6:
                continue
            parts.append(seg.text.strip())
        return " ".join(parts).strip()
