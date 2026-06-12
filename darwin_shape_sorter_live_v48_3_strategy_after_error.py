from __future__ import annotations
"""
DARWIN v48.3 — Shape Sorter ao vivo: estratégia após erro

Uso:
    py darwin_shape_sorter_live_v48_3_strategy_after_error.py

O que demonstra:
- hipótese fraca controlada
- colisão
- memória do erro
- seleção de estratégia conforme tipo de falha
- execução da estratégia
- rotação ativa ainda funcionando
- resolução do brinquedo

Tabela:
    geometry_live_actions_v48_3
"""

import json, math, random, sqlite3, tkinter as tk
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from tkinter import ttk

DB_PATH = Path("darwin_home") / "darwin.db"
TABLE = "geometry_live_actions_v48_3"


def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds")
def j(x): return json.dumps(x, ensure_ascii=False, sort_keys=True)


@dataclass
class Piece:
    id: str; family: str; x: float; y: float; hx: float; hy: float
    size: float; depth: float; angle: float; color: str
    placed: bool = False; attempts: int = 0


@dataclass
class Hole:
    id: str; family: str; x: float; y: float; size: float; depth: float
    angle: float = 0.0; tol: float = 5.0; filled: bool = False; by: str = ""


@dataclass
class Eval:
    piece_id: str; hole_id: str
    contour: bool; size_ok: bool; depth_ok: bool; rot_ok: bool
    fit: bool; collision: bool; score: float; reason: str; explanation: str


@dataclass
class Strategy:
    failure_reason: str; recommendation: str; piece_id: str; failed_hole_id: str; explanation: str


class Memory:
    def __init__(self):
        self.enabled = True
        try:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(DB_PATH) as c:
                c.execute(f"""CREATE TABLE IF NOT EXISTS {TABLE}(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    action_kind TEXT NOT NULL,
                    piece_id TEXT NOT NULL DEFAULT '',
                    hole_id TEXT NOT NULL DEFAULT '',
                    score REAL NOT NULL DEFAULT 0,
                    outcome TEXT NOT NULL DEFAULT '',
                    note TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                )""")
                c.commit()
        except Exception:
            self.enabled = False

    def log(self, kind, piece="", hole="", score=0.0, outcome="", note="", payload=None):
        if not self.enabled: return
        try:
            with sqlite3.connect(DB_PATH) as c:
                c.execute(f"""INSERT INTO {TABLE}
                    (timestamp, action_kind, piece_id, hole_id, score, outcome, note, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (now(), kind, piece, hole, score, outcome, note, j(payload or {})))
                c.commit()
        except Exception:
            self.enabled = False


class Darwin:
    def __init__(self, mem: Memory):
        self.mem = mem
        self.failed = set()
        self.explored = False
        self.pending: Strategy | None = None

    def rot_ok(self, p: Piece, h: Hole) -> bool:
        if p.family == "circle": return True
        sym = 90 if p.family == "square" else 120
        d = abs((p.angle - h.angle) % 360)
        if d > 180: d = 360 - d
        r = min(d % sym, sym - (d % sym))
        return r <= 3

    def eval(self, p: Piece, h: Hole) -> Eval:
        contour = p.family == h.family
        size_ok = p.size <= h.size + h.tol
        depth_ok = p.depth <= h.depth
        rot_ok = self.rot_ok(p, h)
        fit = contour and size_ok and depth_ok and rot_ok
        score = (0.42 if contour else 0) + (0.22 if size_ok else 0) + (0.20 if depth_ok else 0) + (0.16 if rot_ok else 0)
        if fit:
            reason, exp = "", "compatível: inserir"
        elif not contour:
            reason, exp = "contour_mismatch", "forma errada: estratégia natural é tentar outro buraco"
        elif not size_ok:
            reason, exp = "size_mismatch", "tamanho incompatível: rejeitar par"
        elif not depth_ok:
            reason, exp = "depth_mismatch", "profundidade incompatível: rejeitar inserção completa"
        elif not rot_ok:
            reason, exp = "rotation_mismatch", "orientação incompatível: tentar girar"
        else:
            reason, exp = "uncertain_failure", "falha incerta: explorar com cautela"
        return Eval(p.id, h.id, contour, size_ok, depth_ok, rot_ok, fit, not fit, round(score, 3), reason, exp)

    def strategy(self, ev: Eval) -> Strategy:
        mapping = {
            "contour_mismatch": ("try_alternate_hole", "tentar outro buraco para a mesma peça"),
            "rotation_mismatch": ("rotate_piece", "girar a peça antes de desistir"),
            "size_mismatch": ("reject_pair_size", "não repetir par grande demais"),
            "depth_mismatch": ("reject_pair_depth", "não insistir em inserção profunda"),
        }
        rec, exp = mapping.get(ev.reason, ("cautious_exploration", "explorar com cautela"))
        return Strategy(ev.reason, rec, ev.piece_id, ev.hole_id, exp)

    def remember_error(self, ev: Eval):
        self.failed.add((ev.piece_id, ev.hole_id))
        self.mem.log("error_memory_write", ev.piece_id, ev.hole_id, ev.score, "stored",
                     "erro físico memorizado", {"failed_pairs": list(map(list, self.failed)), "evaluation": asdict(ev)})
        st = self.strategy(ev)
        self.pending = st
        self.mem.log("strategy_select", ev.piece_id, ev.hole_id, ev.score, "selected",
                     st.recommendation, asdict(st) | {"source_error": asdict(ev)})
        return st

    def choose_pending(self, pieces, holes):
        if not self.pending: return None
        st = self.pending
        p = next((x for x in pieces if x.id == st.piece_id and not x.placed), None)
        if not p:
            self.pending = None; return None
        if st.recommendation == "try_alternate_hole":
            opts = []
            for h in holes:
                if h.filled or h.id == st.failed_hole_id or (p.id, h.id) in self.failed: continue
                ev = self.eval(p, h)
                opts.append((ev.score, p, h, ev))
            if opts:
                opts.sort(key=lambda x: x[0], reverse=True)
                _, p, h, ev = opts[0]
                self.pending = None
                self.mem.log("strategy_execute", p.id, h.id, ev.score, "executed",
                             "try_alternate_hole", {"strategy": asdict(st), "chosen": asdict(ev)})
                return "think", p, h, ev, "estratégia: tentar outro buraco"
        self.pending = None
        return None

    def choose(self, pieces, holes):
        a = self.choose_pending(pieces, holes)
        if a: return a
        ps = [p for p in pieces if not p.placed]
        hs = [h for h in holes if not h.filled]
        if not ps or not hs: return None
        ranked, weak = [], []
        for p in ps:
            for h in hs:
                ev = self.eval(p, h)
                sc = ev.score - (0.45 if (p.id, h.id) in self.failed else 0) - min(0.05*p.attempts, .15)
                ranked.append((sc, p, h, ev))
                if (not self.explored and not ev.fit and 0.45 <= ev.score <= 0.70 and ev.size_ok and ev.depth_ok and (p.id, h.id) not in self.failed):
                    weak.append((sc, p, h, ev))
        if weak:
            weak.sort(key=lambda x: x[0], reverse=True)
            _, p, h, ev = weak[0]
            self.explored = True
            self.mem.log("controlled_explore_choose", p.id, h.id, ev.score, "chosen",
                         "hipótese fraca para gerar estratégia", asdict(ev))
            return "think", p, h, ev, "exploração controlada"
        ranked.sort(key=lambda x: x[0], reverse=True)
        _, p, h, ev = ranked[0]
        if self.failed and (p.id, h.id) not in self.failed:
            self.mem.log("avoid_repeat", p.id, h.id, ev.score, "selected_non_failed_pair",
                         f"par(es) falho(s) ignorado(s): {sorted(self.failed)}",
                         {"failed_pairs": list(map(list, self.failed)), "selected": asdict(ev)})
        self.mem.log("choose", p.id, h.id, ev.score, "chosen", "melhor hipótese atual", asdict(ev))
        return "think", p, h, ev, "melhor hipótese atual"


class App:
    BG = "#eef4fb"; TEXT = "#172b44"; MUTED = "#60758e"
    BLUE = "#3977e3"; YELLOW = "#f2c94c"; RED = "#eb5757"; WOOD = "#dbb789"; DARK = "#7d593a"
    GREEN = "#2dbe78"; BAD = "#d9534f"

    def __init__(self, root):
        self.root = root
        root.title("DARWIN v48.3 — estratégia após erro")
        root.geometry("1220x780")
        root.configure(bg=self.BG)

        self.mem = Memory()
        self.agent = Darwin(self.mem)
        self.cv = tk.Canvas(root, width=790, height=740, bg=self.BG, highlightthickness=0)
        self.cv.pack(side="left", padx=12, pady=12)

        side = tk.Frame(root, bg=self.BG); side.pack(side="right", fill="both", expand=True, padx=(0,12), pady=12)
        bar = tk.Frame(side, bg=self.BG); bar.pack(fill="x")
        ttk.Button(bar, text="Iniciar Auto", command=self.start).grid(row=0, column=0, padx=4, pady=4, sticky="ew")
        ttk.Button(bar, text="Pausar", command=self.pause).grid(row=0, column=1, padx=4, pady=4, sticky="ew")
        ttk.Button(bar, text="Passo", command=self.step).grid(row=0, column=2, padx=4, pady=4, sticky="ew")
        ttk.Button(bar, text="Resetar", command=self.reset).grid(row=0, column=3, padx=4, pady=4, sticky="ew")
        for i in range(4): bar.grid_columnconfigure(i, weight=1)

        self.status = tk.StringVar(value="Pronto. Darwin vai errar, classificar e escolher estratégia.")
        tk.Label(side, textvariable=self.status, bg="white", fg=self.TEXT, wraplength=380, justify="left",
                 padx=10, pady=8, relief="solid", bd=1).pack(fill="x", pady=(8,8))
        self.logic = tk.Text(side, height=16, wrap="word", bg="white", fg=self.TEXT, relief="solid", bd=1)
        self.logic.pack(fill="x", pady=(0,8)); self.logic.config(state="disabled")
        self.hist = tk.Text(side, height=18, wrap="word", bg="#0d3b66", fg="#eaf7ff", relief="solid", bd=1)
        self.hist.pack(fill="both", expand=True); self.hist.config(state="disabled")

        self.auto = False; self.phase = "idle"; self.action = None; self.count = 0
        self.t = 0.0; self.start_xy = None; self.back_xy = None; self.face = "neutral"; self.flash = ""; self.flash_n = 0
        random.seed(483)
        self.setup()
        self.write_logic("v48.3: erro → memória → estratégia → execução.\n")
        self.loop()

    def setup(self):
        self.holes = [
            Hole("hole_square","square",470,360,82,1.5),
            Hole("hole_triangle","triangle",590,360,86,1.5),
            Hole("hole_circle","circle",710,360,82,1.5),
        ]
        self.pieces = [
            Piece("piece_square_rotated","square",120,590,120,590,74,1.0,45,self.BLUE),
            Piece("piece_triangle","triangle",240,590,240,590,78,1.0,0,self.YELLOW),
            Piece("piece_circle","circle",360,590,360,590,74,1.0,0,self.RED),
            Piece("piece_circle_large","circle",120,685,120,685,104,1.0,0,"#f07c7c"),
            Piece("piece_square_deep","square",250,685,250,685,74,2.4,0,"#77a7f2"),
        ]
        self.agent.failed.clear(); self.agent.pending = None; self.agent.explored = False
        self.phase = "idle"; self.action = None; self.face = "neutral"

    def start(self): self.auto=True; self.log("AUTO: iniciado.")
    def pause(self): self.auto=False; self.log("AUTO: pausado.")
    def step(self):
        if self.phase == "idle": self.plan()
    def reset(self):
        self.auto=False; self.setup(); self.log("RESET."); self.write_logic("Resetado.\n")

    def piece(self, pid): return next(p for p in self.pieces if p.id == pid)
    def hole(self, hid): return next(h for h in self.holes if h.id == hid)
    def solved(self): return all(h.filled for h in self.holes)

    def plan(self):
        if self.solved():
            self.auto=False; self.face="happy"
            self.status.set("Concluído: Darwin classificou erro, escolheu estratégia e resolveu.")
            self.write_logic("Final:\n- erro controlado ✔\n- estratégia selecionada ✔\n- estratégia executada ✔\n- rotação ativa ✔\n- resolvido ✔")
            self.log("SUCESSO: ciclo v48.3 concluído.")
            return
        chosen = self.agent.choose(self.pieces, self.holes)
        if not chosen:
            self.auto=False; return
        kind,p,h,ev,note = chosen
        self.action = [kind,p.id,h.id,ev,note]
        self.phase = "thinking"; self.count=26; self.face="thinking"
        tag = "ESTRATÉGIA" if note.startswith("estratégia") else ("EXPLORAÇÃO" if "exploração" in note else "PENSAR")
        self.status.set(f"Darwin avaliando {p.family} → {h.family}.")
        self.log(f"{tag}: {p.id} -> {h.id} | score={ev.score:.2f} | {ev.reason or 'success'}")
        self.write_logic(self.eval_text("AVALIAR", p, h, ev, note))

    def eval_text(self, title,p,h,ev,note):
        return (f"Ação: {title}\nPolítica: {note}\n\nPeça: {p.id}\nBuraco: {h.id}\n\n"
                f"contorno={ev.contour} tamanho={ev.size_ok} profundidade={ev.depth_ok} orientação={ev.rot_ok}\n"
                f"score={ev.score:.2f}\nresultado={'encaixa' if ev.fit else 'não encaixa'}\n"
                f"motivo={ev.reason or 'compatível'}\n{ev.explanation}\n")

    def after_think(self):
        _,pid,hid,_,note = self.action
        p,h = self.piece(pid), self.hole(hid)
        ev = self.agent.eval(p,h)
        if ev.fit:
            self.phase="move_insert"; self.t=0; self.start_xy=(p.x,p.y); self.back_xy=(p.hx,p.hy); self.face="focus"
            self.mem.log("insert_start", p.id,h.id,ev.score,"started","inserção",asdict(ev))
            self.log(f"INSERIR: {p.id} -> {h.id}")
        elif ev.reason == "rotation_mismatch" and ev.contour and ev.size_ok and ev.depth_ok:
            self.phase="rotate"; self.face="thinking"
            self.mem.log("rotate_start", p.id,h.id,ev.score,"started","estratégia rotate_piece",asdict(ev))
            self.log(f"GIRAR: {p.id} de {p.angle:.0f}° para {h.angle:.0f}°")
            self.write_logic(self.eval_text("ESTRATÉGIA: GIRAR", p,h,ev,"rotation_mismatch → rotate_piece"))
        else:
            self.phase="move_collision"; self.t=0; self.start_xy=(p.x,p.y); self.back_xy=(p.hx,p.hy); self.face="focus"
            self.mem.log("controlled_collision_start", p.id,h.id,ev.score,"started","teste seguro",asdict(ev))
            self.log(f"TESTE CONTROLADO: {p.id} -> {h.id}")

    def animate(self):
        if self.flash_n>0: self.flash_n-=1
        if self.phase=="idle" or not self.action: return
        _,pid,hid,_,note = self.action
        p,h = self.piece(pid), self.hole(hid)

        if self.phase=="thinking":
            self.count-=1
            if self.count<=0: self.after_think()
        elif self.phase=="rotate":
            delta = (h.angle - p.angle) % 360
            if delta>180: delta-=360
            step = 5.5 if delta>0 else -5.5
            if abs(delta)<=5.5:
                p.angle=h.angle
                ev = self.agent.eval(p,h)
                self.mem.log("rotate_success",p.id,h.id,ev.score,"success","rotação resolveu",asdict(ev))
                self.log(f"ROTAÇÃO RESOLVEU: {p.id} -> {h.id}")
                self.phase="move_insert"; self.t=0; self.start_xy=(p.x,p.y); self.back_xy=(p.hx,p.hy)
            else:
                p.angle=(p.angle+step)%360
        elif self.phase in ("move_insert","move_collision"):
            sx,sy = self.start_xy
            self.t = min(1, self.t+0.04)
            t = 1-(1-self.t)*(1-self.t)
            p.x = sx + (h.x-sx)*t
            p.y = sy + (h.y-105-sy)*t - 20*math.sin(math.pi*t)
            if self.t>=1:
                ev = self.agent.eval(p,h); p.attempts += 1
                if self.phase=="move_insert" and ev.fit:
                    p.x,p.y=h.x,h.y; p.placed=True; h.filled=True; h.by=p.id
                    self.mem.log("insert_success",p.id,h.id,ev.score,"success","encaixe correto",asdict(ev))
                    self.log(f"SUCESSO: {p.id} -> {h.id}")
                    self.phase="idle"; self.action=None; self.face="happy"; self.flash="encaixe correto"; self.flash_n=35
                else:
                    st = self.agent.remember_error(ev)
                    self.mem.log("controlled_collision",p.id,h.id,ev.score,"collision",ev.reason,asdict(ev))
                    self.log(f"COLISÃO: {p.id} -> {h.id} | {ev.reason}")
                    self.log(f"ESTRATÉGIA: {ev.reason} -> {st.recommendation}")
                    self.write_logic(self.eval_text("COLISÃO / ESTRATÉGIA",p,h,ev,"classificar falha")+f"\nEstratégia: {st.recommendation}\n{st.explanation}\n")
                    self.phase="return"; self.t=0; self.start_xy=(p.x,p.y); self.face="sad"; self.flash=ev.reason; self.flash_n=40
        elif self.phase=="return":
            sx,sy = self.start_xy; tx,ty = self.back_xy
            self.t = min(1,self.t+0.06); t=1-(1-self.t)*(1-self.t)
            p.x=sx+(tx-sx)*t; p.y=sy+(ty-sy)*t
            if self.t>=1:
                self.log(f"RECUO: {p.id} voltou ao ponto seguro.")
                self.phase="idle"; self.action=None; self.face="neutral"

    def loop(self):
        if self.auto and self.phase=="idle": self.plan()
        self.animate(); self.draw()
        self.root.after(25,self.loop)

    def write_logic(self, text):
        self.logic.config(state="normal"); self.logic.delete("1.0","end"); self.logic.insert("1.0",text); self.logic.config(state="disabled")
    def log(self,text):
        self.hist.config(state="normal"); self.hist.insert("end",text+"\n"); self.hist.see("end"); self.hist.config(state="disabled")

    def rr(self,x1,y1,x2,y2,r=18,**kw):
        pts=[x1+r,y1,x2-r,y1,x2,y1,x2,y1+r,x2,y2-r,x2,y2,x2-r,y2,x1+r,y2,x1,y2,x1,y2-r,x1,y1+r,x1,y1]
        return self.cv.create_polygon(pts,smooth=True,splinesteps=24,**kw)

    def draw(self):
        c=self.cv; c.delete("all")
        self.rr(15,15,775,725,26,fill="#f8fbff",outline="#cbd8e8",width=2)
        c.create_text(35,38,anchor="w",text="DARWIN v48.3 — estratégia após erro",font=("Segoe UI",17,"bold"),fill=self.TEXT)
        c.create_text(35,65,anchor="w",text="Erro → classificar → escolher estratégia → executar",font=("Segoe UI",10),fill=self.MUTED)
        self.draw_robot(140,220); self.draw_policy(35,105); self.draw_board()
        for p in self.pieces:
            if not p.placed: self.draw_piece(p)
        if self.action: self.draw_link()
        if self.flash_n>0 and self.flash:
            col=self.GREEN if "correto" in self.flash else self.BAD
            self.rr(455,120,750,165,14,fill="white",outline=col,width=3)
            c.create_text(602,142,text=self.flash,font=("Segoe UI",14,"bold"),fill=col)
        c.create_text(35,705,anchor="w",text=f"Progresso: {sum(h.filled for h in self.holes)}/3 | Estratégia pendente: {self.agent.pending.recommendation if self.agent.pending else 'nenhuma'} | SQLite: {'ON' if self.mem.enabled else 'OFF'}",font=("Segoe UI",10,"bold"),fill=self.TEXT)

    def draw_policy(self,x,y):
        self.rr(x,y,x+390,y+105,14,fill="white",outline="#d6e2f1",width=2)
        for i,(a,b) in enumerate([("contorno","outro buraco"),("orientação","girar"),("tamanho","rejeitar"),("profundidade","rejeitar")]):
            px=x+18+i*92
            self.cv.create_text(px,y+22,anchor="w",text=a,font=("Segoe UI",9,"bold"),fill="#22507c")
            self.cv.create_text(px,y+50,anchor="w",text="↓",font=("Segoe UI",16,"bold"),fill=self.BLUE)
            self.cv.create_text(px,y+78,anchor="w",text=b,font=("Segoe UI",9),fill=self.MUTED)

    def draw_robot(self,cx,cy):
        c=self.cv
        c.create_oval(cx-65,cy-85,cx+65,cy+45,fill="#f8fbff",outline="#b9c8da",width=3)
        c.create_oval(cx-50,cy-58,cx+50,cy+15,fill="#192638",outline="#30465f",width=2)
        c.create_oval(cx-30,cy-35,cx-10,cy-15,fill="#8bdbff",outline="")
        c.create_oval(cx+10,cy-35,cx+30,cy-15,fill="#8bdbff",outline="")
        if self.face=="thinking": c.create_text(cx,cy,text="...",font=("Segoe UI",14,"bold"),fill="#8bdbff")
        elif self.face=="sad": c.create_arc(cx-18,cy+10,cx+18,cy+30,start=0,extent=180,outline="#8bdbff",width=3,style="arc")
        else: c.create_arc(cx-18,cy+0,cx+18,cy+18,start=180,extent=180,outline="#8bdbff",width=3,style="arc")
        c.create_oval(cx-18,cy+28,cx+18,cy+64,fill="#ddf5ff",outline="#6ec6ff",width=3)
        c.create_text(cx,cy+83,text="DARWIN",font=("Segoe UI",9,"bold"),fill="#355574")
        c.create_line(cx+55,cy+40,cx+110,cy+85,fill="#a8b7c9",width=8)
        c.create_oval(cx+104,cy+78,cx+120,cy+94,fill="white",outline="#8fa2b8",width=2)

    def draw_board(self):
        self.rr(425,300,760,540,20,fill=self.WOOD,outline="#be9569",width=2)
        for h in self.holes: self.draw_hole(h)

    def draw_hole(self,h):
        c=self.cv; f=self.DARK; o="#62482f"
        if h.family=="square":
            c.create_rectangle(h.x-40,h.y-40,h.x+40,h.y+40,fill=f,outline=o,width=3)
            if h.filled: c.create_rectangle(h.x-35,h.y-35,h.x+35,h.y+35,fill=self.piece(h.by).color,outline="")
        elif h.family=="triangle":
            pts=[h.x,h.y-45,h.x-45,h.y+36,h.x+45,h.y+36]
            c.create_polygon(pts,fill=f,outline=o,width=3)
            if h.filled: c.create_polygon([h.x,h.y-38,h.x-37,h.y+30,h.x+37,h.y+30],fill=self.piece(h.by).color,outline="")
        else:
            c.create_oval(h.x-40,h.y-40,h.x+40,h.y+40,fill=f,outline=o,width=3)
            if h.filled: c.create_oval(h.x-35,h.y-35,h.x+35,h.y+35,fill=self.piece(h.by).color,outline="")

    def rot(self,pts,a,cx,cy):
        r=math.radians(a)
        return [(cx+(x-cx)*math.cos(r)-(y-cy)*math.sin(r), cy+(x-cx)*math.sin(r)+(y-cy)*math.cos(r)) for x,y in pts]

    def draw_piece(self,p):
        c=self.cv
        if self.action and self.action[1]==p.id: c.create_oval(p.x-52,p.y-52,p.x+52,p.y+52,outline="#aee8ff",width=3)
        if p.family=="square":
            s=p.size/2; pts=self.rot([(p.x-s,p.y-s),(p.x+s,p.y-s),(p.x+s,p.y+s),(p.x-s,p.y+s)],p.angle,p.x,p.y)
            c.create_polygon([v for pt in pts for v in pt],fill=p.color,outline="#2458b8",width=2)
            c.create_text(p.x,p.y+s+17,text=f"{p.angle:.0f}°",font=("Segoe UI",9,"bold"),fill=self.MUTED)
        elif p.family=="triangle":
            s=p.size/2; pts=self.rot([(p.x,p.y-s),(p.x-s,p.y+s*.84),(p.x+s,p.y+s*.84)],p.angle,p.x,p.y)
            c.create_polygon([v for pt in pts for v in pt],fill=p.color,outline="#a98013",width=2)
        else:
            r=p.size/2; c.create_oval(p.x-r,p.y-r,p.x+r,p.y+r,fill=p.color,outline="#b43b3b",width=2)
        if "large" in p.id: c.create_text(p.x,p.y+p.size/2+17,text="grande",font=("Segoe UI",8),fill=self.MUTED)
        if "deep" in p.id: c.create_text(p.x,p.y+p.size/2+17,text="profundo",font=("Segoe UI",8),fill=self.MUTED)

    def draw_link(self):
        _,pid,hid,_,_=self.action
        p,h=self.piece(pid),self.hole(hid)
        self.cv.create_line(p.x,p.y-55,h.x,h.y-68,fill="#6ec6ff",width=3,dash=(7,5),arrow="last")


if __name__ == "__main__":
    root=tk.Tk()
    try:
        from ctypes import windll; windll.shcore.SetProcessDpiAwareness(1)
    except Exception: pass
    try: ttk.Style().theme_use("vista")
    except Exception: pass
    App(root)
    root.mainloop()
