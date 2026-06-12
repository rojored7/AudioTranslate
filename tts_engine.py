import wave
import json
from pathlib import Path
from abc import ABC, abstractmethod
from typing import Optional
import requests

CUSTOM_TOKEN_PREFIX = "<custom_token_"
ORPHEUS_SAMPLE_RATE = 24000


class TTSEngine(ABC):
    """Abstract base class for TTS engines."""

    @abstractmethod
    def generate_audio(self, text: str, output_path: str) -> bool:
        """Generate audio from text. Returns True if successful."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the TTS engine is available."""
        pass


class OllamaTTSEngine(TTSEngine):
    """TTS engine using Ollama with Orpheus model via OpenAI-compatible API."""

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        model: str = "legraphista/Orpheus:latest",
        voice: str = "tara",
    ):
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model
        self.voice = voice  # tara, leah, jess, leo, dan, mia, zac, zoe
        self._snac_model = None
        self._snac_device = None

    def is_available(self) -> bool:
        """Check if Ollama is running and the Orpheus model is available."""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=3)
            if response.status_code == 200:
                models = [m.get("name", "") for m in response.json().get("models", [])]
                return any(self.model in name for name in models)
            return False
        except Exception:
            return False

    def _load_snac(self) -> bool:
        """Lazy-load the SNAC audio codec model."""
        if self._snac_model is not None:
            return True
        try:
            import torch
            from snac import SNAC

            device = (
                "cuda"
                if torch.cuda.is_available()
                else "mps"
                if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()
                else "cpu"
            )
            print(f"[SNAC] Cargando modelo en {device}...")
            self._snac_model = SNAC.from_pretrained("hubertsiuzdak/snac_24khz").eval().to(device)
            self._snac_device = device
            print(f"[SNAC] Modelo listo en {device}")
            return True
        except Exception as e:
            print(f"[SNAC] Error cargando modelo: {e}")
            return False

    def _turn_token_into_id(self, token_string: str, index: int) -> Optional[int]:
        """Convert a <custom_token_N> string to an integer SNAC token ID.

        Logic from Orpheus-FastAPI/tts_engine/speechpipe.py.
        The offset formula encodes layer position: token_id = N - 10 - (layer * 4096)
        where layer = index % 7.
        """
        if CUSTOM_TOKEN_PREFIX not in token_string:
            return None
        stripped = token_string.strip()
        last_start = stripped.rfind(CUSTOM_TOKEN_PREFIX)
        last_token = stripped[last_start:]
        if not (last_token.startswith(CUSTOM_TOKEN_PREFIX) and last_token.endswith(">")):
            return None
        try:
            number_str = last_token[14:-1]  # len("<custom_token_") == 14
            return int(number_str) - 10 - ((index % 7) * 4096)
        except (ValueError, IndexError):
            return None

    def _convert_to_audio(self, multiframe: list) -> Optional[bytes]:
        """Decode a buffer of SNAC token IDs to 16-bit PCM bytes.

        Expects multiples of 7 tokens (one SNAC frame = 7 tokens).
        Logic from Orpheus-FastAPI/tts_engine/speechpipe.py.
        """
        import torch
        import numpy as np

        if len(multiframe) < 7:
            return None

        num_frames = len(multiframe) // 7
        frame = multiframe[: num_frames * 7]
        dev = self._snac_device

        codes_0 = torch.zeros(num_frames, dtype=torch.int32, device=dev)
        codes_1 = torch.zeros(num_frames * 2, dtype=torch.int32, device=dev)
        codes_2 = torch.zeros(num_frames * 4, dtype=torch.int32, device=dev)
        ft = torch.tensor(frame, dtype=torch.int32, device=dev)

        for j in range(num_frames):
            i = j * 7
            codes_0[j] = ft[i]
            codes_1[j * 2] = ft[i + 1]
            codes_1[j * 2 + 1] = ft[i + 4]
            codes_2[j * 4] = ft[i + 2]
            codes_2[j * 4 + 1] = ft[i + 3]
            codes_2[j * 4 + 2] = ft[i + 5]
            codes_2[j * 4 + 3] = ft[i + 6]

        codes = [codes_0.unsqueeze(0), codes_1.unsqueeze(0), codes_2.unsqueeze(0)]

        if any(torch.any(c < 0) or torch.any(c > 4096) for c in codes):
            return None

        with torch.inference_mode():
            audio_hat = self._snac_model.decode(codes)
            audio_np = audio_hat[:, :, 2048:4096].detach().cpu().numpy()
            return (audio_np * 32767).astype(np.int16).tobytes()

    def generate_audio(self, text: str, output_path: str) -> bool:
        """Generate audio via Orpheus streaming tokens → SNAC decode → WAV."""
        if not self._load_snac():
            print("[Orpheus] SNAC no disponible, abortando")
            return False

        prompt = f"<|audio|>{self.voice}: {text}<|eot_id|>"
        print(f"[Orpheus] Generando {len(text)} chars con voz '{self.voice}'...")

        try:
            response = requests.post(
                f"{self.ollama_url}/v1/completions",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "max_tokens": 2000,
                    "temperature": 0.6,
                    "top_p": 0.9,
                    "stream": True,
                },
                stream=True,
                timeout=300,
            )
        except Exception as e:
            print(f"[Orpheus] Error de conexión: {e}")
            return False

        if response.status_code != 200:
            print(f"[Orpheus] Error HTTP {response.status_code}: {response.text[:200]}")
            return False

        buffer = []
        count = 0
        audio_chunks = []

        for raw_line in response.iter_lines():
            if not raw_line:
                continue
            line = raw_line.decode("utf-8", errors="ignore")
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str.strip() == "[DONE]":
                break
            try:
                token_text = json.loads(data_str)["choices"][0]["text"]
            except Exception:
                continue

            # Each SSE chunk may contain one or more "<custom_token_N>" strings
            for part in token_text.split(">"):
                if not part:
                    continue
                token_id = self._turn_token_into_id(part + ">", count)
                if token_id is not None and token_id > 0:
                    buffer.append(token_id)
                    count += 1
                    # Decode every 7 tokens (one SNAC frame), using a 28-token window
                    if count % 7 == 0:
                        window = buffer[-28:] if len(buffer) >= 28 else buffer
                        audio_bytes = self._convert_to_audio(window)
                        if audio_bytes:
                            audio_chunks.append(audio_bytes)

        # Flush any remaining tokens
        if len(buffer) >= 7:
            audio_bytes = self._convert_to_audio(buffer)
            if audio_bytes:
                audio_chunks.append(audio_bytes)

        if not audio_chunks:
            print(f"[Orpheus] No se generaron tokens de audio válidos (tokens totales: {count})")
            return False

        all_audio = b"".join(audio_chunks)
        with wave.open(output_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit PCM
            wf.setframerate(ORPHEUS_SAMPLE_RATE)
            wf.writeframes(all_audio)

        duration = len(all_audio) // 2 / ORPHEUS_SAMPLE_RATE
        print(f"[Orpheus] WAV guardado: {output_path} ({duration:.1f}s, {count} tokens)")
        return True


class KokoroTTSEngine(TTSEngine):
    """TTS engine using Kokoro ONNX (from HuggingFace)."""

    def __init__(self, voice: str = "af_heart"):
        self.voice = voice
        self.pipeline = None

    def _load_pipeline(self):
        if self.pipeline is None:
            try:
                from kokoro import KPipeline
                self.pipeline = KPipeline(lang_code="a")
            except Exception as e:
                print(f"Failed to load Kokoro: {e}")
                return False
        return True

    def is_available(self) -> bool:
        return self._load_pipeline()

    def generate_audio(self, text: str, output_path: str) -> bool:
        try:
            if not self._load_pipeline():
                return False

            import soundfile as sf
            import numpy as np

            generator = self.pipeline(text, voice=self.voice)
            audio_chunks = []
            sample_rate = 24000

            for _gs, _ps, audio in generator:
                audio_chunks.append(audio)

            if not audio_chunks:
                print("No audio generated by Kokoro")
                return False

            full_audio = np.concatenate(audio_chunks)
            sf.write(output_path, full_audio, sample_rate)
            return True

        except Exception as e:
            print(f"Error in KokoroTTSEngine: {e}")
            return False


class EdgeTTSEngine(TTSEngine):
    """Microsoft Edge TTS — voces neurales en español de alta calidad, requiere internet."""

    # Voces recomendadas para español
    SPANISH_VOICES = [
        "es-ES-AlvaroNeural",   # España - masculino (recomendado)
        "es-ES-ElviraNeural",   # España - femenino
        "es-MX-JorgeNeural",    # México - masculino
        "es-MX-DaliaNeural",    # México - femenino
        "es-AR-TomasNeural",    # Argentina - masculino
        "es-CO-GonzaloNeural",  # Colombia - masculino
    ]

    def __init__(self, voice: str = "es-ES-AlvaroNeural"):
        self.voice = voice

    def is_available(self) -> bool:
        try:
            import edge_tts  # noqa: F401
            return True
        except ImportError:
            return False

    def generate_audio(self, text: str, output_path: str) -> bool:
        try:
            import asyncio
            import edge_tts

            async def _run():
                communicate = edge_tts.Communicate(text, self.voice)
                await communicate.save(output_path)

            asyncio.run(_run())
            print(f"[EdgeTTS] Guardado: {output_path} ({self.voice})")
            return True
        except Exception as e:
            print(f"[EdgeTTS] Error: {e}")
            return False


def get_tts_engine(engine_type: str, **kwargs) -> TTSEngine:
    """Factory function to get the appropriate TTS engine."""
    if engine_type == "ollama":
        return OllamaTTSEngine(
            ollama_url=kwargs.get("ollama_url", "http://localhost:11434"),
            model=kwargs.get("model", "legraphista/Orpheus:latest"),
            voice=kwargs.get("voice", "tara"),
        )
    elif engine_type == "edge_tts":
        return EdgeTTSEngine(voice=kwargs.get("voice", "es-ES-AlvaroNeural"))
    elif engine_type == "kokoro":
        return KokoroTTSEngine(voice=kwargs.get("voice", "af_heart"))
    else:
        return KokoroTTSEngine()
