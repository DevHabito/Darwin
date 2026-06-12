from __future__ import annotations

"""
DARWIN Voice Orb v49.6

Janela simples para conversar com Darwin.
Um circulo central pulsa e se move enquanto a fala esta ativa.

Uso:
    py darwin_voice_orb_v49_6.py

Tambem pode ser aberto pelo arquivo:
    Abrir_Darwin_Orb.bat
"""

import math
import sqlite3
import subprocess
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk
from typing import Any


DB = Path("darwin_home") / "darwin.db"


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


@dataclass
class DarwinStatus:
    sigma: float = 0.0
    energy: float = 0.0
    latency: float = 0.0
    v49_5: str = ""
    v49_4: str = ""
    v49_3: str = ""


def latest_scenario(conn: sqlite3.Connection, table: str, complete_phase: str) -> str:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    if not row:
        return ""
    got = conn.execute(
        f"""
        SELECT scenario_id
        FROM {table}
        WHERE phase=?
        ORDER BY id DESC
        LIMIT 1
        """,
        (complete_phase,),
    ).fetchone()
    return str(got["scenario_id"]) if got else ""


def load_status() -> DarwinStatus:
    if not DB.exists():
        return DarwinStatus()
    try:
        with sqlite3.connect(DB) as conn:
            conn.row_factory = sqlite3.Row
            state = conn.execute("SELECT * FROM current_state WHERE id=1").fetchone()
            status = DarwinStatus()
            if state:
                status.sigma = safe_float(state["sigma"])
                status.energy = safe_float(state["energy"])
                status.latency = safe_float(state["latency"])
            status.v49_5 = latest_scenario(conn, "rzs_plasticity_cycles_v49_5", "plasticity_complete")
            status.v49_4 = latest_scenario(conn, "brain_rzs_governed_cycles_v49_4", "governed_cycle_complete")
            status.v49_3 = latest_scenario(conn, "rzs_stress_tests_v49_3", "scenario_complete")
            return status
    except Exception:
        return DarwinStatus()


def compose_reply(user_text: str) -> str:
    text = user_text.strip().lower()
    status = load_status()
    if not text:
        return "Estou aqui. Meu nucleo esta ativo no notebook."

    if any(word in text for word in ("status", "estado", "como voce esta", "como esta")):
        if status.sigma:
            return (
                "Estado atual do Darwin. "
                f"Sigma {status.sigma:.2f}. Energia {status.energy:.2f}. "
                f"Latencia {status.latency:.2f}. "
                "RZS formal, governanca e plasticidade ja tem cenarios validados."
            )
        return "Ainda nao consegui ler meu banco local, mas a interface esta ativa."

    if any(word in text for word in ("rzs", "romero", "estabilidade")):
        return (
            "O RZS esta funcionando como meu sistema nervoso regulatorio. "
            "Ele mede tensao relacional, prediz risco, decide quando seguir, estreitar foco, "
            "fazer replay, consolidar ou pausar."
        )

    if any(word in text for word in ("oi", "ola", "bom dia", "boa tarde", "boa noite")):
        return "Oi, Felipe. Estou aqui. Posso te responder e mover este circulo enquanto falo."

    if any(word in text for word in ("proximo", "marco", "passo")):
        return (
            "O proximo passo natural e ligar esta presenca visual ao loop cognitivo real: "
            "quando eu tomar uma decisao, o circulo deve refletir sigma, energia e acao escolhida."
        )

    return (
        "Eu ouvi sua mensagem. Ainda sou um prototipo local, mas ja tenho um nucleo com RZS, "
        "metacognicao, governanca e plasticidade. Posso usar isso como base para responder melhor."
    )


class SpeechEngine:
    def __init__(self, on_start, on_stop) -> None:
        self.on_start = on_start
        self.on_stop = on_stop
        self.proc: subprocess.Popen[str] | None = None
        self.lock = threading.Lock()

    def speak(self, text: str) -> None:
        with self.lock:
            self.stop()
            t = threading.Thread(target=self._speak_worker, args=(text,), daemon=True)
            t.start()

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass
        self.proc = None

    def _speak_worker(self, text: str) -> None:
        self.on_start(text)
        try:
            command = (
                "Add-Type -AssemblyName System.Speech; "
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                "$s.Rate = -1; "
                "$s.Volume = 100; "
                "$text = [Console]::In.ReadToEnd(); "
                "$s.Speak($text);"
            )
            self.proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            assert self.proc.stdin is not None
            self.proc.stdin.write(text)
            self.proc.stdin.close()
            self.proc.wait()
        except Exception:
            # Fallback: keep animation alive for the estimated speech time.
            time.sleep(max(1.2, min(12.0, len(text) / 15.0)))
        finally:
            self.on_stop()


class DarwinOrbApp:
    BG = "#0b1118"
    PANEL = "#101b26"
    INK = "#e9f2f7"
    MUTED = "#8aa1b3"
    BLUE = "#55a7ff"
    GREEN = "#6ee7a8"
    ORANGE = "#f0a35e"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Darwin Orb")
        self.root.geometry("900x680")
        self.root.minsize(760, 580)
        self.root.configure(bg=self.BG)

        self.speaking = False
        self.speech_text = ""
        self.tick = 0.0
        self.level = 0.0
        self.last_text_index = 0
        self.speech = SpeechEngine(self.start_speaking, self.stop_speaking)

        self.canvas = tk.Canvas(root, bg=self.BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        controls = tk.Frame(root, bg=self.PANEL)
        controls.pack(fill="x", padx=0, pady=0)

        self.entry = tk.Entry(
            controls,
            bg="#162534",
            fg=self.INK,
            insertbackground=self.INK,
            relief="flat",
            font=("Segoe UI", 12),
        )
        self.entry.pack(side="left", fill="x", expand=True, padx=14, pady=12, ipady=8)
        self.entry.bind("<Return>", lambda _event: self.send())

        ttk.Button(controls, text="Falar", command=self.send).pack(side="left", padx=(0, 8), pady=12)
        ttk.Button(controls, text="Status", command=self.say_status).pack(side="left", padx=(0, 8), pady=12)
        ttk.Button(controls, text="Parar", command=self.stop_all).pack(side="left", padx=(0, 14), pady=12)

        self.transcript = tk.Text(
            root,
            height=8,
            bg="#081019",
            fg=self.INK,
            insertbackground=self.INK,
            relief="flat",
            wrap="word",
            font=("Segoe UI", 10),
        )
        self.transcript.pack(fill="x", padx=0, pady=0)
        self.transcript.config(state="disabled")

        self.write("Darwin", "Interface iniciada. Escreva algo e aperte Enter.")
        self.root.after(350, self.greeting)
        self.animate()

    def greeting(self) -> None:
        self.say("Oi, Felipe. Eu sou o Darwin local. Este circulo se move enquanto eu falo.")

    def write(self, who: str, text: str) -> None:
        self.transcript.config(state="normal")
        self.transcript.insert("end", f"{who}: {text}\n")
        self.transcript.see("end")
        self.transcript.config(state="disabled")

    def send(self) -> None:
        user_text = self.entry.get().strip()
        self.entry.delete(0, "end")
        if user_text:
            self.write("Voce", user_text)
        reply = compose_reply(user_text)
        self.write("Darwin", reply)
        self.say(reply)

    def say_status(self) -> None:
        reply = compose_reply("status")
        self.write("Darwin", reply)
        self.say(reply)

    def say(self, text: str) -> None:
        self.speech.speak(text)

    def stop_all(self) -> None:
        self.speech.stop()
        self.stop_speaking()

    def start_speaking(self, text: str) -> None:
        self.speaking = True
        self.speech_text = text
        self.last_text_index = 0

    def stop_speaking(self) -> None:
        self.speaking = False
        self.level = 0.0

    def speech_energy(self) -> float:
        if not self.speaking or not self.speech_text:
            return 0.0
        idx = int((self.tick * 7.5) % max(1, len(self.speech_text)))
        ch = self.speech_text[idx]
        if ch.lower() in "aeiou":
            return 1.0
        if ch.isalpha():
            return 0.62
        if ch in ".,;:":
            return 0.18
        return 0.35

    def animate(self) -> None:
        self.tick += 0.075
        target = self.speech_energy()
        self.level = self.level * 0.78 + target * 0.22
        self.draw()
        self.root.after(16, self.animate)

    def draw(self) -> None:
        c = self.canvas
        w = max(1, c.winfo_width())
        h = max(1, c.winfo_height())
        c.delete("all")

        cx = w / 2
        cy = h / 2 - 20
        wobble = 1.0 if self.speaking else 0.20
        x = cx + math.sin(self.tick * 2.2) * 26 * self.level * wobble
        y = cy + math.cos(self.tick * 1.8) * 18 * self.level * wobble
        radius = 78 + 34 * self.level

        # Soft halo.
        for i in range(7, 0, -1):
            rr = radius + i * 18
            shade = 18 + i * 7
            color = f"#{shade:02x}{min(90, shade + 20):02x}{min(130, shade + 50):02x}"
            c.create_oval(x - rr, y - rr, x + rr, y + rr, outline="", fill=color)

        fill = self.BLUE if self.speaking else "#244159"
        outline = self.GREEN if self.speaking else "#45647c"
        c.create_oval(x - radius, y - radius, x + radius, y + radius, fill=fill, outline=outline, width=4)

        inner = radius * (0.35 + self.level * 0.10)
        c.create_oval(x - inner, y - inner, x + inner, y + inner, fill="#d8f6ff", outline="")

        status = "falando" if self.speaking else "ouvindo"
        status_color = self.GREEN if self.speaking else self.MUTED
        c.create_text(cx, 42, text="DARWIN ORB", fill=self.INK, font=("Segoe UI", 22, "bold"))
        c.create_text(cx, 76, text=status, fill=status_color, font=("Segoe UI", 12))

        st = load_status()
        if st.sigma:
            footer = f"sigma {st.sigma:.2f}   energia {st.energy:.2f}   latencia {st.latency:.2f}"
        else:
            footer = "darwin.db nao encontrado ou estado indisponivel"
        c.create_text(cx, h - 34, text=footer, fill=self.MUTED, font=("Segoe UI", 10))


def main() -> int:
    root = tk.Tk()
    DarwinOrbApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
