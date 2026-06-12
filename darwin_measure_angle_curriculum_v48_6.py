from __future__ import annotations
"""
DARWIN v48.6 — Currículo explícito de medidas e ângulos

Uso:
    py darwin_measure_angle_curriculum_v48_6.py

Tabela:
    geometry_measure_curriculum_v48_6
"""

import json, math, random, sqlite3, time, tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from tkinter import ttk

DB = Path("darwin_home") / "darwin.db"
TABLE = "geometry_measure_curriculum_v48_6"

def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds")
def js(x): return json.dumps(x, ensure_ascii=False, sort_keys=True)
def suf(r):
    abc = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(r.choice(abc) for _ in range(5))

class Memory:
    def __init__(self):
        self.enabled = True
        try:
            DB.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(DB) as c:
                c.execute(f"""CREATE TABLE IF NOT EXISTS {TABLE}(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    scenario_id TEXT NOT NULL DEFAULT '',
                    action_kind TEXT NOT NULL,
                    case_id TEXT NOT NULL DEFAULT '',
                    concept_key TEXT NOT NULL DEFAULT '',
                    measurement_kind TEXT NOT NULL DEFAULT '',
                    piece_family TEXT NOT NULL DEFAULT '',
                    hole_family TEXT NOT NULL DEFAULT '',
                    piece_value REAL NOT NULL DEFAULT 0,
                    hole_value REAL NOT NULL DEFAULT 0,
                    delta REAL NOT NULL DEFAULT 0,
                    tolerance REAL NOT NULL DEFAULT 0,
                    angle_value REAL NOT NULL DEFAULT 0,
                    target_angle REAL NOT NULL DEFAULT 0,
                    symmetry_deg REAL NOT NULL DEFAULT 0,
                    relation TEXT NOT NULL DEFAULT '',
                    verdict TEXT NOT NULL DEFAULT '',
                    note TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                )""")
                c.commit()
        except Exception:
            self.enabled = False

    def log(self, sid, kind, case=None, result=None, note="", payload=None):
        if not self.enabled: return
        case = case or {}
        result = result or {}
        payload = payload or {}
        payload = {"case": case, "result": result, **payload}
        try:
            with sqlite3.connect(DB) as c:
                c.execute(f"""INSERT INTO {TABLE}
                (timestamp, scenario_id, action_kind, case_id, concept_key, measurement_kind,
                 piece_family, hole_family, piece_value, hole_value, delta, tolerance,
                 angle_value, target_angle, symmetry_deg, relation, verdict, note, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    now(), sid, kind,
                    case.get("case_id", result.get("case_id", "")),
                    case.get("concept_key", result.get("concept_key", "")),
                    case.get("measurement_kind", result.get("measurement_kind", "")),
                    case.get("piece_family", ""), case.get("hole_family", ""),
                    float(case.get("piece_value", 0)), float(case.get("hole_value", 0)),
                    float(result.get("delta", 0)),
                    float(case.get("tolerance", result.get("tolerance", 0))),
                    float(case.get("angle_value", 0)),
                    float(case.get("target_angle", 0)),
                    float(case.get("symmetry_deg", 0)),
                    result.get("relation", ""), result.get("verdict", ""), note, js(payload)
                ))
                c.commit()
        except Exception:
            self.enabled = False

class Tutor:
    def __init__(self, mem):
        self.mem = mem
        self.learned = set()

    @staticmethod
    def minrot(angle, target, symmetry):
        d = (target - angle) % symmetry
        if d > symmetry / 2: d -= symmetry
        return round(d, 3)

    def eval(self, c):
        kind = c["measurement_kind"]
        if kind == "size":
            delta = round(c["piece_value"] - c["hole_value"], 3)
            if abs(delta) <= c["tolerance"]:
                rel, ver, exp = "within_tolerance", "accept", "diferença pequena cabe na tolerância"
            elif delta > 0:
                rel, ver, exp = "larger_than", "reject_size", "peça maior que abertura além da tolerância"
            else:
                rel, ver, exp = "smaller_than", "accept", "peça menor que abertura"
        elif kind == "depth":
            delta = round(c["piece_value"] - c["hole_value"], 3)
            if delta > c["tolerance"]:
                rel, ver, exp = "deeper_than", "reject_depth", "peça profunda demais"
            else:
                rel, ver, exp = "shallower_or_equal", "accept", "profundidade cabe"
        elif kind == "angle":
            delta = self.minrot(c["angle_value"], c["target_angle"], c["symmetry_deg"])
            if abs(delta) <= c["tolerance"]:
                rel, ver, exp = "aligned", "accept", "orientação dentro da tolerância angular"
            else:
                rel, ver, exp = "rotation_needed", "rotate", f"girar {delta:+.1f}° para alinhar"
        else:
            delta = round(c["piece_value"] - c["hole_value"], 3)
            same = c["piece_family"] == c["hole_family"]
            if not same:
                rel, ver, exp = "different_shape", "reject_shape", "forma diferente não é escala nem orientação"
            elif abs(c["angle_value"] - c["target_angle"]) > c["tolerance"]:
                rel, ver, exp = "same_shape_different_orientation", "rotate", "mesma forma, orientação diferente"
            elif abs(delta) > c["tolerance"]:
                rel, ver, exp = "same_shape_different_scale", "compare_scale", "mesma forma, escala diferente"
            else:
                rel, ver, exp = "same_shape_same_scale", "accept", "forma, escala e orientação compatíveis"
        return {
            "case_id": c["case_id"], "concept_key": c["concept_key"], "measurement_kind": kind,
            "relation": rel, "verdict": ver, "delta": delta, "tolerance": c["tolerance"], "explanation": exp
        }

    def learn(self, sid, c):
        self.mem.log(sid, "measure_observe", case=c, note="observar valores")
        r = self.eval(c)
        self.mem.log(sid, "measure_compare", case=c, result=r, note=r["relation"])
        ok = r["relation"] == c["expected_relation"] and r["verdict"] == c["expected_verdict"]
        self.mem.log(sid, "concept_learned", case=c, result=r, note=c["concept_key"],
                     payload={"passed_expectation": ok, "expected_relation": c["expected_relation"], "expected_verdict": c["expected_verdict"]})
        self.learned.add(c["concept_key"])
        return r

class App:
    BG="#eef4fb"; TEXT="#172b44"; MUTED="#60758e"; BLUE="#3977e3"; GREEN="#2dbe78"; BAD="#d9534f"
    def __init__(self, root):
        self.root=root; root.title("DARWIN v48.6 — medidas e ângulos"); root.geometry("1240x780"); root.configure(bg=self.BG)
        self.mem=Memory(); self.tutor=Tutor(self.mem)
        self.cv=tk.Canvas(root,width=815,height=735,bg=self.BG,highlightthickness=0); self.cv.pack(side="left",padx=12,pady=12)
        side=tk.Frame(root,bg=self.BG); side.pack(side="right",fill="both",expand=True,padx=(0,12),pady=12)
        bar=tk.Frame(side,bg=self.BG); bar.pack(fill="x")
        ttk.Button(bar,text="Iniciar Auto",command=self.start).grid(row=0,column=0,padx=4,pady=4,sticky="ew")
        ttk.Button(bar,text="Pausar",command=self.pause).grid(row=0,column=1,padx=4,pady=4,sticky="ew")
        ttk.Button(bar,text="Passo",command=self.step).grid(row=0,column=2,padx=4,pady=4,sticky="ew")
        ttk.Button(bar,text="Novo currículo",command=self.new).grid(row=0,column=3,padx=4,pady=4,sticky="ew")
        for i in range(4): bar.grid_columnconfigure(i,weight=1)
        self.status=tk.StringVar(value="Pronto. Darwin vai registrar conceitos quantitativos.")
        tk.Label(side,textvariable=self.status,bg="white",fg=self.TEXT,wraplength=395,justify="left",anchor="w",padx=10,pady=8,relief="solid",bd=1).pack(fill="x",pady=(8,8))
        self.logic=tk.Text(side,height=18,wrap="word",bg="white",fg=self.TEXT,relief="solid",bd=1); self.logic.pack(fill="x",pady=(0,8)); self.logic.config(state="disabled")
        self.hist=tk.Text(side,height=20,wrap="word",bg="#0d3b66",fg="#eaf7ff",relief="solid",bd=1); self.hist.pack(fill="both",expand=True); self.hist.config(state="disabled")
        self.auto=False; self.stage=0; self.case=None; self.result=None; self.count=0; self.flash=""; self.flash_n=0; self.face="neutral"
        self.setup(int(time.time()) % 10000000); self.write("v48.6: currículo explícito de medidas e ângulos.\n"); self.loop()

    def setup(self, seed):
        self.tutor.learned.clear(); self.stage=0; self.case=None; self.result=None; self.face="neutral"
        r=random.Random(seed); self.sid=f"V486-{seed}-{suf(r)}"
        hs=r.randint(78,88); tol=round(r.uniform(3.0,5.5),1); large=hs+tol+r.randint(8,15); within=round(hs+r.uniform(.5,tol-.5),2)
        hd=round(r.uniform(1.25,1.55),2); deep=round(hd+r.uniform(.45,.85),2); shallow=round(hd-r.uniform(.2,.4),2)
        ang=r.choice([17,29,37,53,61]); minrot=Tutor.minrot(ang,0,90)
        def case(cid, ck, mk, pf, hf, pv, hv, to, av, ta, sy, er, ev):
            return {"case_id":cid,"concept_key":ck,"measurement_kind":mk,"piece_family":pf,"hole_family":hf,"piece_value":float(pv),"hole_value":float(hv),"tolerance":float(to),"angle_value":float(av),"target_angle":float(ta),"symmetry_deg":float(sy),"expected_relation":er,"expected_verdict":ev}
        self.curr=[
            case("case_size_larger","larger_smaller","size","circle","circle",large,hs,tol,0,0,0,"larger_than","reject_size"),
            case("case_size_tolerance","tolerance","size","circle","circle",within,hs,tol,0,0,0,"within_tolerance","accept"),
            case("case_depth_deeper","deep_shallow","depth","square","square",deep,hd,.05,0,0,0,"deeper_than","reject_depth"),
            case("case_depth_shallow","deep_shallow","depth","square","square",shallow,hd,.05,0,0,0,"shallower_or_equal","accept"),
            case("case_angle_rotation","angle_rotation_minimum","angle","square","square",0,0,3,ang,0,90,"rotation_needed","rotate"),
            case("case_same_shape_orientation","shape_vs_orientation","shape_orientation_scale","triangle","triangle",80,80,3,40,0,120,"same_shape_different_orientation","rotate"),
            case("case_same_shape_scale","shape_vs_scale","shape_orientation_scale","square","square",96,82,4,0,0,90,"same_shape_different_scale","compare_scale"),
            case("case_different_shape","shape_not_scale_or_orientation","shape_orientation_scale","triangle","circle",78,82,4,0,0,0,"different_shape","reject_shape"),
        ]
        self.mem.log(self.sid,"curriculum_init",note="measure_angle_curriculum",payload={"seed":seed,"size_hole":hs,"size_large":large,"size_within":within,"size_tolerance":tol,"depth_hole":hd,"depth_deep":deep,"depth_shallow":shallow,"angle":ang,"minimal_rotation":minrot,"cases":self.curr})

    def new(self): self.auto=False; self.setup(int(time.time())%10000000); self.log(f"NOVO CURRÍCULO: {self.sid}"); self.write(f"Novo currículo: {self.sid}\n")
    def start(self): self.auto=True; self.log("AUTO: iniciado.")
    def pause(self): self.auto=False; self.log("AUTO: pausado.")
    def step(self):
        if self.count<=0: self.advance()

    def advance(self):
        if self.stage>=len(self.curr):
            self.auto=False; self.face="happy"; self.status.set("Concluído. Darwin registrou conceitos de medidas e ângulos.")
            self.mem.log(self.sid,"curriculum_complete",note="measure_angle_curriculum_complete",payload={"learned_concepts":sorted(self.tutor.learned)})
            self.write("Final v48.6:\n- maior/menor ✔\n- tolerância ✔\n- profundo/raso ✔\n- ângulo e rotação mínima ✔\n- forma vs orientação ✔\n- forma vs escala ✔\n")
            self.log("SUCESSO: currículo v48.6 concluído."); return
        self.case=self.curr[self.stage]; self.stage+=1; self.result=self.tutor.learn(self.sid,self.case)
        self.count=42; self.face="thinking"; self.flash=self.result["verdict"]; self.flash_n=38
        self.status.set(f"Darwin medindo: {self.case['concept_key']}.")
        self.log(f"MEDIR[{self.case['concept_key']}]: {self.case['measurement_kind']} | relation={self.result['relation']} | verdict={self.result['verdict']}")
        self.write(self.text())

    def text(self):
        c=self.case; r=self.result; rot=""
        if c["measurement_kind"]=="angle":
            rot=f"\nÂngulo atual: {c['angle_value']:.1f}°\nAlvo: {c['target_angle']:.1f}°\nSimetria: {c['symmetry_deg']:.1f}°\nRotação mínima: {r['delta']:+.1f}°\n"
        return (f"Caso: {c['case_id']}\nConceito: {c['concept_key']}\nTipo: {c['measurement_kind']}\n\n"
                f"Família peça: {c['piece_family']}\nFamília buraco: {c['hole_family']}\n"
                f"Valor peça: {c['piece_value']:.3f}\nValor buraco: {c['hole_value']:.3f}\nTolerância: {c['tolerance']:.3f}\nDelta: {r['delta']:+.3f}\n{rot}\n"
                f"Relação: {r['relation']}\nVeredito: {r['verdict']}\nExplicação: {r['explanation']}\n")

    def loop(self):
        if self.flash_n>0: self.flash_n-=1
        if self.count>0: self.count-=1
        if self.auto and self.count<=0: self.advance()
        self.draw(); self.root.after(25,self.loop)

    def write(self,t): self.logic.config(state="normal"); self.logic.delete("1.0","end"); self.logic.insert("1.0",t); self.logic.config(state="disabled")
    def log(self,t): self.hist.config(state="normal"); self.hist.insert("end",t+"\n"); self.hist.see("end"); self.hist.config(state="disabled")
    def rr(self,x1,y1,x2,y2,r=18,**kw):
        pts=[x1+r,y1,x2-r,y1,x2,y1,x2,y1+r,x2,y2-r,x2,y2,x2-r,y2,x1+r,y2,x1,y2,x1,y2-r,x1,y1+r,x1,y1]
        return self.cv.create_polygon(pts,smooth=True,splinesteps=24,**kw)

    def draw(self):
        c=self.cv; c.delete("all")
        self.rr(15,15,800,720,26,fill="#f8fbff",outline="#cbd8e8",width=2)
        c.create_text(35,38,anchor="w",text="DARWIN v48.6 — medidas e ângulos",font=("Segoe UI",18,"bold"),fill=self.TEXT)
        c.create_text(35,66,anchor="w",text=f"Currículo: {self.sid}",font=("Segoe UI",10),fill=self.MUTED)
        self.robot(135,225); self.map(35,105); self.panel(450,115)
        c.create_text(35,700,anchor="w",text=f"Etapa: {self.stage}/{len(self.curr)} | conceitos: {len(self.tutor.learned)} | SQLite: {'ON' if self.mem.enabled else 'OFF'}",font=("Segoe UI",10,"bold"),fill=self.TEXT)
        if self.flash_n>0 and self.flash:
            col=self.GREEN if self.flash in ("accept","rotate","compare_scale") else self.BAD
            self.rr(460,610,785,660,14,fill="white",outline=col,width=3); c.create_text(622,635,text=self.flash,font=("Segoe UI",15,"bold"),fill=col)

    def robot(self,cx,cy):
        c=self.cv
        c.create_oval(cx-65,cy-85,cx+65,cy+45,fill="#f8fbff",outline="#b9c8da",width=3)
        c.create_oval(cx-50,cy-58,cx+50,cy+15,fill="#192638",outline="#30465f",width=2)
        c.create_oval(cx-30,cy-35,cx-10,cy-15,fill="#8bdbff",outline=""); c.create_oval(cx+10,cy-35,cx+30,cy-15,fill="#8bdbff",outline="")
        c.create_text(cx,cy,text="∑" if self.face=="thinking" else ("✓" if self.face=="happy" else "?"),font=("Segoe UI",18,"bold"),fill="#8bdbff")
        c.create_oval(cx-18,cy+28,cx+18,cy+64,fill="#ddf5ff",outline="#6ec6ff",width=3)
        c.create_text(cx,cy+83,text="DARWIN",font=("Segoe UI",9,"bold"),fill="#355574")
        c.create_line(cx+55,cy+40,cx+110,cy+85,fill="#a8b7c9",width=8); c.create_oval(cx+104,cy+78,cx+120,cy+94,fill="white",outline="#8fa2b8",width=2)

    def map(self,x,y):
        self.rr(x,y,x+390,y+145,14,fill="white",outline="#d6e2f1",width=2)
        items=[("maior","menor"),("tolerância","±"),("profundo","raso"),("ângulo","θ"),("rotação","↻"),("forma","≠ escala")]
        for i,(a,b) in enumerate(items):
            px=x+18+(i%3)*125; py=y+28+(i//3)*62
            self.cv.create_text(px,py,anchor="w",text=a,font=("Segoe UI",10,"bold"),fill="#22507c")
            self.cv.create_text(px,py+25,anchor="w",text=b,font=("Segoe UI",10),fill=self.MUTED)

    def panel(self,x,y):
        self.rr(x,y,x+330,y+455,18,fill="white",outline="#d6e2f1",width=2)
        self.cv.create_text(x+20,y+25,anchor="w",text="Painel de medida",font=("Segoe UI",14,"bold"),fill=self.TEXT)
        if not self.case or not self.result:
            self.cv.create_text(x+20,y+70,anchor="w",text="Aguardando medição...",font=("Segoe UI",11),fill=self.MUTED); return
        c=self.case; r=self.result
        self.cv.create_text(x+20,y+62,anchor="w",text=c["concept_key"],font=("Segoe UI",12,"bold"),fill=self.BLUE)
        self.cv.create_text(x+20,y+92,anchor="w",text=f"medida: {c['measurement_kind']}",font=("Segoe UI",10),fill=self.MUTED)
        by=y+145; mx=max(c["piece_value"],c["hole_value"],1); pl=min(225,225*c["piece_value"]/mx); hl=min(225,225*c["hole_value"]/mx)
        self.cv.create_text(x+20,by-25,anchor="w",text="peça",font=("Segoe UI",9,"bold"),fill=self.TEXT)
        self.cv.create_rectangle(x+80,by-36,x+80+pl,by-14,fill=self.BLUE,outline=""); self.cv.create_text(x+80+pl+8,by-25,anchor="w",text=f"{c['piece_value']:.2f}",font=("Segoe UI",9),fill=self.MUTED)
        self.cv.create_text(x+20,by+20,anchor="w",text="buraco",font=("Segoe UI",9,"bold"),fill=self.TEXT)
        self.cv.create_rectangle(x+80,by+9,x+80+hl,by+31,fill=self.GREEN,outline=""); self.cv.create_text(x+80+hl+8,by+20,anchor="w",text=f"{c['hole_value']:.2f}",font=("Segoe UI",9),fill=self.MUTED)
        self.cv.create_text(x+20,by+70,anchor="w",text=f"delta: {r['delta']:+.3f}",font=("Segoe UI",11,"bold"),fill=self.TEXT)
        self.cv.create_text(x+20,by+100,anchor="w",text=f"tolerância: {c['tolerance']:.3f}",font=("Segoe UI",10),fill=self.MUTED)
        if c["measurement_kind"]=="angle":
            cx,cy=x+165,by+195
            self.cv.create_oval(cx-55,cy-55,cx+55,cy+55,outline="#c9d8e8",width=2)
            self.cv.create_line(cx,cy,cx+55,cy,fill=self.GREEN,width=3)
            a=math.radians(c["angle_value"]); self.cv.create_line(cx,cy,cx+55*math.cos(a),cy-55*math.sin(a),fill=self.BLUE,width=3,arrow="last")
            self.cv.create_text(cx,cy+75,text=f"rot. mínima {r['delta']:+.1f}°",font=("Segoe UI",11,"bold"),fill=self.TEXT)
        self.cv.create_text(x+20,y+405,anchor="w",text=f"relação: {r['relation']}",font=("Segoe UI",11,"bold"),fill=self.TEXT)
        self.cv.create_text(x+20,y+432,anchor="w",text=f"veredito: {r['verdict']}",font=("Segoe UI",11,"bold"),fill=self.BLUE)

if __name__=="__main__":
    root=tk.Tk()
    try:
        from ctypes import windll; windll.shcore.SetProcessDpiAwareness(1)
    except Exception: pass
    try: ttk.Style().theme_use("vista")
    except Exception: pass
    App(root); root.mainloop()
