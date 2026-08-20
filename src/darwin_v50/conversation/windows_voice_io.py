"""Windows microphone and speech synthesis adapters without dialogue logic."""

from __future__ import annotations

from dataclasses import dataclass
import os
import subprocess
import threading
import time
from typing import Callable

from ..models import ValidationError, require_text


@dataclass(frozen=True, slots=True)
class RecognizedSpeech:
    text: str
    confidence: float
    culture: str


class WindowsSpeechListener:
    """Streams local Windows speech-recognition results to callbacks."""

    def __init__(
        self,
        on_ready: Callable[[str, str], None],
        on_result: Callable[[RecognizedSpeech], None],
        on_low_confidence: Callable[[RecognizedSpeech], None],
        on_error: Callable[[str], None],
        *,
        culture: str = "pt-BR",
        minimum_confidence: float = 0.25,
        listener_role: str = "DarwinV50VoiceHost",
    ) -> None:
        if not all(
            callable(callback)
            for callback in (on_ready, on_result, on_low_confidence, on_error)
        ):
            raise ValidationError("voice listener callbacks must be callable")
        require_text(culture, "voice recognition culture")
        if isinstance(minimum_confidence, bool) or not isinstance(
            minimum_confidence,
            (int, float),
        ):
            raise ValidationError("voice confidence threshold must be numeric")
        threshold = float(minimum_confidence)
        if not 0.0 <= threshold <= 1.0:
            raise ValidationError("voice confidence threshold must be from 0 to 1")
        self.on_ready = on_ready
        self.on_result = on_result
        self.on_low_confidence = on_low_confidence
        self.on_error = on_error
        self.culture = culture
        self.minimum_confidence = threshold
        self.listener_role = (
            "".join(character for character in listener_role if character.isalnum())
            or "DarwinV50VoiceHost"
        )
        self.process: subprocess.Popen[str] | None = None
        self.thread: threading.Thread | None = None
        self.stop_requested = False
        self.paused = False
        self.current_culture = ""

    def start(self) -> None:
        if os.name != "nt":
            self.on_error("voice_listener_requires_windows")
            return
        if self.thread is not None and self.thread.is_alive():
            return
        self.stop_requested = False
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_requested = True
        process = self.process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass
        self.process = None

    def set_paused(self, paused: bool) -> None:
        self.paused = bool(paused)

    def _powershell_script(self) -> str:
        return rf"""
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$darwinListenerRole = '{self.listener_role}'
$preferred = '{self.culture}'
$minimumConfidence = {self.minimum_confidence:.3f}
$recognizer = $null

Add-Type -AssemblyName System.Speech
try {{
    $culture = [System.Globalization.CultureInfo]::GetCultureInfo($preferred)
    $recognizer = New-Object System.Speech.Recognition.SpeechRecognitionEngine($culture)
}} catch {{
    $recognizer = $null
}}
if ($recognizer -eq $null) {{
    $infos = [System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers()
    foreach ($info in $infos) {{
        if ($info.Enabled) {{
            $recognizer = New-Object System.Speech.Recognition.SpeechRecognitionEngine($info)
            break
        }}
    }}
}}
if ($recognizer -ne $null) {{
    $grammar = New-Object System.Speech.Recognition.DictationGrammar
    $grammar.Name = 'DarwinV50Dictation'
    $recognizer.LoadGrammar($grammar)
    $recognizer.SetInputToDefaultAudioDevice()
    $recognizer.BabbleTimeout = [TimeSpan]::FromSeconds(1.5)
    $recognizer.InitialSilenceTimeout = [TimeSpan]::FromSeconds(7)
    $recognizer.EndSilenceTimeout = [TimeSpan]::FromMilliseconds(900)
    [Console]::Out.WriteLine("READY|$($recognizer.RecognizerInfo.Culture.Name)|$($recognizer.RecognizerInfo.Name)")
    [Console]::Out.Flush()
    while ($true) {{
        try {{
            $result = $recognizer.Recognize([TimeSpan]::FromSeconds(8))
            if ($result -ne $null) {{
                $text = ($result.Text -replace '\r?\n', ' ').Trim()
                $confidence = [double]$result.Confidence
                if ($text.Length -gt 0 -and $confidence -ge $minimumConfidence) {{
                    [Console]::Out.WriteLine(("RESULT|{{0:N3}}|{{1}}" -f $confidence, $text))
                }} elseif ($text.Length -gt 0) {{
                    [Console]::Out.WriteLine(("LOWCONF|{{0:N3}}|{{1}}" -f $confidence, $text))
                }}
                [Console]::Out.Flush()
            }}
        }} catch {{
            $message = $_.Exception.Message -replace '\r?\n', ' '
            [Console]::Out.WriteLine("ERROR|RECOGNIZE|$message")
            [Console]::Out.Flush()
            Start-Sleep -Milliseconds 500
        }}
    }}
}}

Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Media.SpeechRecognition.SpeechRecognizer, Windows.Media.SpeechRecognition, ContentType=WindowsRuntime] | Out-Null
[Windows.Globalization.Language, Windows.Globalization, ContentType=WindowsRuntime] | Out-Null

function Wait-WinRtOperation {{
    param($Operation, [Type]$ResultType)
    $method = [System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object {{
            $_.Name -eq 'AsTask' -and
            $_.IsGenericMethod -and
            $_.GetParameters().Count -eq 1
        }} |
        Select-Object -First 1
    $task = $method.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    $task.Wait()
    return $task.Result
}}

try {{
    $language = New-Object Windows.Globalization.Language($preferred)
    $probe = New-Object Windows.Media.SpeechRecognition.SpeechRecognizer($language)
    $compiled = Wait-WinRtOperation ($probe.CompileConstraintsAsync()) ([Windows.Media.SpeechRecognition.SpeechRecognitionCompilationResult])
    if ($compiled.Status.ToString() -ne 'Success') {{
        throw "WinRT speech compilation failed: $($compiled.Status)"
    }}
    $probe.Dispose()
    [Console]::Out.WriteLine("READY|$preferred|Windows Media SpeechRecognizer")
    [Console]::Out.Flush()
    while ($true) {{
        $turnRecognizer = $null
        try {{
            $turnRecognizer = New-Object Windows.Media.SpeechRecognition.SpeechRecognizer($language)
            $turnCompiled = Wait-WinRtOperation ($turnRecognizer.CompileConstraintsAsync()) ([Windows.Media.SpeechRecognition.SpeechRecognitionCompilationResult])
            if ($turnCompiled.Status.ToString() -ne 'Success') {{
                throw "WinRT turn preparation failed: $($turnCompiled.Status)"
            }}
            $result = Wait-WinRtOperation ($turnRecognizer.RecognizeAsync()) ([Windows.Media.SpeechRecognition.SpeechRecognitionResult])
            $text = ($result.Text -replace '\r?\n', ' ').Trim()
            $confidence = switch ($result.Confidence.ToString()) {{
                'High' {{ 0.92 }}
                'Medium' {{ 0.72 }}
                'Low' {{ 0.48 }}
                default {{ 0.25 }}
            }}
            if ($text.Length -gt 0 -and $confidence -ge $minimumConfidence) {{
                [Console]::Out.WriteLine(("RESULT|{{0:N3}}|{{1}}" -f $confidence, $text))
            }} elseif ($text.Length -gt 0) {{
                [Console]::Out.WriteLine(("LOWCONF|{{0:N3}}|{{1}}" -f $confidence, $text))
            }}
            [Console]::Out.Flush()
        }} catch {{
            $message = $_.Exception.Message -replace '\r?\n', ' '
            [Console]::Out.WriteLine("ERROR|WINRT_RECOGNIZE|$message")
            [Console]::Out.Flush()
            Start-Sleep -Milliseconds 500
        }} finally {{
            if ($turnRecognizer -ne $null) {{
                $turnRecognizer.Dispose()
            }}
        }}
    }}
}} catch {{
    $message = $_.Exception.Message -replace '\r?\n', ' '
    [Console]::Out.WriteLine("ERROR|NO_RECOGNIZER|$message")
    [Console]::Out.Flush()
    exit 2
}}
"""

    def _worker(self) -> None:
        try:
            self.process = subprocess.Popen(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    self._powershell_script(),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, ValueError) as exc:
            self.on_error(f"voice_listener_start_failed:{type(exc).__name__}")
            return
        assert self.process.stdout is not None
        while not self.stop_requested:
            line = self.process.stdout.readline()
            if not line:
                if self.process.poll() is not None:
                    break
                time.sleep(0.05)
                continue
            self._handle_line(line.strip())
        if not self.stop_requested:
            self.on_error(f"voice_listener_stopped:{self.process.poll()}")

    def _handle_line(self, line: str) -> None:
        if not line:
            return
        parts = line.split("|", 2)
        kind = parts[0]
        if kind == "READY" and len(parts) == 3:
            self.current_culture = parts[1]
            self.on_ready(parts[1], parts[2])
            return
        if kind in {"RESULT", "LOWCONF"} and len(parts) == 3:
            try:
                confidence = float(parts[1].replace(",", "."))
            except ValueError:
                confidence = 0.0
            speech = RecognizedSpeech(
                text=parts[2],
                confidence=confidence,
                culture=self.current_culture or self.culture,
            )
            if self.paused:
                return
            if kind == "RESULT":
                self.on_result(speech)
            else:
                self.on_low_confidence(speech)
            return
        if kind == "ERROR":
            self.on_error(parts[-1])
            return
        self.on_error(f"voice_listener_protocol_error:{line[:120]}")


class WindowsSpeechSynthesizer:
    """Speaks only caller-supplied text and retains no transcript."""

    def __init__(
        self,
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
        on_error: Callable[[str], None],
    ) -> None:
        if not all(callable(callback) for callback in (on_start, on_stop, on_error)):
            raise ValidationError("speech synthesizer callbacks must be callable")
        self.on_start = on_start
        self.on_stop = on_stop
        self.on_error = on_error
        self.process: subprocess.Popen[str] | None = None
        self.thread: threading.Thread | None = None

    def speak(self, text: str) -> None:
        spoken_text = require_text(text, "speech synthesis text")
        self.stop()
        self.thread = threading.Thread(
            target=self._worker,
            args=(spoken_text,),
            daemon=True,
        )
        self.thread.start()

    def stop(self) -> None:
        process = self.process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass
        self.process = None

    def _worker(self, text: str) -> None:
        self.on_start()
        try:
            command = (
                "Add-Type -AssemblyName System.Speech; "
                "$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                "$speaker.Rate = -1; $speaker.Volume = 100; "
                "$text = [Console]::In.ReadToEnd(); $speaker.Speak($text);"
            )
            self.process = subprocess.Popen(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    command,
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            assert self.process.stdin is not None
            self.process.stdin.write(text)
            self.process.stdin.close()
            self.process.wait()
        except (OSError, ValueError) as exc:
            self.on_error(f"speech_synthesis_failed:{type(exc).__name__}")
        finally:
            self.process = None
            self.on_stop()
