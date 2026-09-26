#!/usr/bin/env python3
r"""Live UART dashboard for the GT-King PRO <-> ESP32-C3 bridge.

    py -3.14 lineage/scripts/uart-dashboard.py           ->  http://localhost:8080/

Shows, for every pad of the box's UART header, whether the wire is really connected, whether bytes
are arriving (pad 2 = box TX) and whether the box answers what we send (pad 3 = box RX), plus a live
console with a corruption-tolerant "cleaned" view. Buttons run the Ctrl-C break and the repair.

The serial port is owned by a single worker thread; the HTTP handlers only queue actions.
"""
import html, importlib.util, json, os, queue, subprocess, sys, threading, time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "out"))

spec = importlib.util.spec_from_file_location("esp32bridge", os.path.join(HERE, "esp32-bridge.py"))
eb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eb)

PORT_HTTP = 8080
RX_PIN, TX_PIN, BAUD = 2, 3, 115200

# ---------------------------------------------------------------- text repair
PRINTABLE_SCORE = {}
for _b in range(256):
    _c = chr(_b)
    if _c in "etaoinshrdlu ":
        PRINTABLE_SCORE[_b] = 5
    elif _c.islower():
        PRINTABLE_SCORE[_b] = 4
    elif _c.isdigit() or _c.isupper():
        PRINTABLE_SCORE[_b] = 3
    elif _c in ".,:;-_/#>=()[]*+'\"$%":
        PRINTABLE_SCORE[_b] = 2
    elif _b in (10, 13):
        PRINTABLE_SCORE[_b] = 5
    else:
        PRINTABLE_SCORE[_b] = 0

CLEAN = bytearray(256)
for _b in range(256):
    best, best_score = _b, PRINTABLE_SCORE[_b] * 3
    for _k in range(8):                       # clearing one wrongly-set bit
        _c = _b & ~(1 << _k)
        s = PRINTABLE_SCORE[_c] * 2
        if s > best_score:
            best, best_score = _c, s
    for _k in range(8):                       # or two
        for _m in range(_k + 1, 8):
            _c = _b & ~(1 << _k) & ~(1 << _m)
            s = PRINTABLE_SCORE[_c]
            if s > best_score:
                best, best_score = _c, s
    CLEAN[_b] = best if best_score else 0x2E   # '.'


def clean_text(data):
    return bytes(CLEAN[b] for b in data).decode("ascii", "replace")


# ---------------------------------------------------------------- worker
class Worker(threading.Thread):
    daemon = True

    def __init__(self):
        super().__init__()
        self.q = queue.Queue()
        self.lock = threading.Lock()
        self.link = None
        self.state = {
            "port": None, "mode": "starting", "busy": "", "since": time.time(),
            "rx_total": 0, "rx_rate": 0.0, "rx_last": 0.0, "printable": 0.0,
            "tx_sent": 0, "tx_proof": None, "tx_proof_at": 0,
            "prompt": False, "prompt_at": 0, "markers": {}, "pads": {},
            "events": deque(maxlen=60), "error": "",
            "auto": True, "auto_note": "czekam na dobry sygnał (masa podłączona)",
            "adapter": "", "adapter_mode": "",
        }
        self.raw_tail = deque(maxlen=16000)
        self.window = deque(maxlen=200)          # (timestamp, nbytes)

    # -- helpers ---------------------------------------------------------
    def ev(self, msg):
        with self.lock:
            self.state["events"].appendleft(f"{time.strftime('%H:%M:%S')}  {msg}")
        print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)

    # Anything the ESP32 itself prints on the same USB console (a panic, the ROM banner, the
    # MicroPython greeting) must never be counted as data from the box - otherwise a crash dump
    # looks like a perfectly clean 97%-readable "console".
    ESP_NOISE = (b"Guru Meditation", b"ESP-ROM:esp32", b"MicroPython v", b"rst:0x",
                 b"A fatal error occurred", b"Core  0 register dump", b"<<BRIDGE-", b"<<MON-")

    def note_rx(self, data):
        if not data:
            return
        probe = bytes(self.raw_tail)[-200:] + data
        for m in self.ESP_NOISE:
            if m in probe:
                self.ev(f"to nie box, tylko ESP32: {m.decode()} - restartuję mostek")
                self.link.bridging = False
                self.raw_tail.clear(); self.window.clear()
                with self.lock:
                    self.state["rx_rate"] = 0.0; self.state["printable"] = 0.0
                    self.state["esp_restarts"] = self.state.get("esp_restarts", 0) + 1
                return
        now = time.time()
        with self.lock:
            self.state["rx_total"] += len(data)
            self.state["rx_last"] = now
        self.raw_tail.extend(data)
        self.window.append((now, len(data)))

    def recompute(self):
        now = time.time()
        recent = [(t, n) for t, n in self.window if now - t < 5]
        rate = sum(n for _, n in recent) / 5.0
        tail = bytes(self.raw_tail)[-4000:]
        printable = (sum(1 for b in tail if 32 <= b < 127) / len(tail)) if tail else 0.0
        marks = {}
        big = bytes(self.raw_tail)
        for m in ("U-Boot 20", "MMC:   aml_priv->desc_buf", "Net:   dwmac", "g12b_w400_v1#",
                  "g12b_s922x_galilei", "Saving Environment", "store read"):
            h, a = eb.tol_find(big, m, 2.4)
            if h:
                marks[m] = {"hits": h, "added": a}
        with self.lock:
            self.state["rx_rate"] = rate
            self.state["printable"] = printable
            self.state["markers"] = marks

    # -- actions ---------------------------------------------------------
    def do_diag(self):
        if getattr(self, "adapter_mode", "bridge") == "direct":
            self.ev("adapter USB-TTL nie mierzy padów - diagnostyka jest tylko dla ESP32")
            return
        self.ev("diagnostyka padów: test ciągłości i pomiar impulsów (ok. 20 s)")
        res = {}
        try:
            for gpio, (lo, hi, verdict) in self.link.pintest((RX_PIN, TX_PIN, 4)).items():
                res[gpio] = {"ciaglosc": verdict, "pulldown": lo, "pullup": hi}
                self.ev(f"GPIO{gpio}: {verdict}")
        except Exception as e:
            self.ev(f"test ciągłości nieudany: {e}")
        try:
            code = ("PINS = %r\n" % ((RX_PIN, TX_PIN, 4),)) + (eb.PROBE % 2000)
            out = self.link.exec_raw(code, b"<<PROBE-DONE>>", 22)
            for ln in out.decode("ascii", "replace").splitlines():
                if ln.startswith("PROBE "):
                    n, rest = ln[6:].split(" ", 1)
                    r = eval(rest)
                    if r[0] == "ERR":
                        res[int(n)] = {"verdict": "błąd: " + r[1]}
                        continue
                    (lo, hi, mean, cnt, low), (_, _, pd, _, _), (_, _, pu, _, _), (npulse, hist) = r
                    d = res.setdefault(int(n), {})
                    hd = dict(hist)
                    bits = sum(hd.get(b, 0) for b in (9, 17, 26, 35))
                    d.update({
                        "float_mV": mean, "pulses": npulse, "bitlike": bits,
                        "verdict": ("dane UART 115200 (impulsy o szerokości bitu)" if bits > 20
                                    else "brak impulsów o szerokości bitu"),
                    })
        except Exception as e:
            self.ev(f"diagnostyka nieudana: {e}")
        with self.lock:
            self.state["pads"] = res
        self.ev("diagnostyka zakończona")

    def do_break(self, seconds=60):
        """Ctrl-C storm with listening pauses; proves pad 3 when the box answers."""
        self.ev(f"salwa Ctrl-C przez {seconds} s (przerwanie pętli bootloop)")
        end = time.time() + seconds
        seen = deque(maxlen=40)
        while time.time() < end:
            hammer_end = time.time() + 0.8
            got = b""
            while time.time() < hammer_end:
                self.link.wr(b"\x03" * 8)
                with self.lock:
                    self.state["tx_sent"] += 8
                got += self.link.raw(0.1)
            pause = self.link.raw(1.2)
            self.note_rx(got + pause)
            self.recompute()
            seen.append((time.time(), len(got) + len(pause)))
            contact = sum(n for t, n in seen if time.time() - t < 12) > 300
            if contact and not pause:
                self.ev("box milczy w przerwie - test promptu")
                if self.check_prompt():
                    return True
        self.ev("nie udało się złapać promptu")
        return False

    def check_prompt(self):
        self.link.raw(0.3)
        self.link.wr(b"\r\n"); a = self.link.raw(0.5)
        self.link.wr(b"echo AAAAAAAA\r\n"); b = self.link.raw(0.9)
        with self.lock:
            self.state["tx_sent"] += 18
        self.note_rx(a + b)
        hits, added = eb.tol_find(b, "AAAAAAAA", 1.2)
        ok = len(b) >= 12 and (hits > 0 or len(b) >= 24)
        with self.lock:
            self.state["tx_proof"] = bool(ok)
            self.state["tx_proof_at"] = time.time()
            self.state["prompt"] = bool(ok)
            if ok:
                self.state["prompt_at"] = time.time()
        self.ev(f"test promptu: odpowiedź {len(b)} B, dopasowań 'AAAAAAAA' = {hits} -> "
                + ("PROMPT U-BOOT" if ok else "brak odpowiedzi"))
        return ok

    def do_send(self, text):
        self.link.wr(text.encode("ascii", "replace") + b"\r\n")
        with self.lock:
            self.state["tx_sent"] += len(text) + 2
        got = self.link.raw(1.2)
        self.note_rx(got)
        self.ev(f"wysłano: {text!r} -> odpowiedź {len(got)} B")
        if got:
            with self.lock:
                self.state["tx_proof"] = True
                self.state["tx_proof_at"] = time.time()

    def do_burn(self):
        """One short command over the flaky wire, then the reliable USB channel does the repair."""
        self.ev("wysyłam 'update' (tryb USB burn), dalej idzie przez kabel USB A-A")
        self.link.wr(b"update\r\n")
        self.link.raw(1.0)
        self.link.stop_bridge()
        bl33 = os.path.join(OUT, "bl33-v2.img")
        cmd = [sys.executable, os.path.join(HERE, "catch-burn.py"), "--wait", "90"]
        if os.path.exists(bl33):
            cmd += ["--bl33", bl33]
        self.ev("uruchamiam catch-burn.py " + " ".join(cmd[2:]))
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            for ln in (r.stdout or "").splitlines()[-25:]:
                self.ev("catch-burn: " + ln)
            self.ev(f"catch-burn.py zakończony kodem {r.returncode}")
        except Exception as e:
            self.ev(f"catch-burn.py błąd: {e}")
        self.link.start_bridge(BAUD, TX_PIN, RX_PIN, "none")

    def do_fix_hook(self):
        self.ev("wpisuję warunkowy hook preboot przez konsolę")
        for p in eb.HOOK_PARTS:
            self.do_send(p)
        self.do_send("setenv upgrade_step 2")
        self.do_send("saveenv")

    def maybe_autobreak(self):
        """Once the link becomes clean (that happens the moment a real ground is connected),
        start the Ctrl-C storm on its own - the operator has both hands on the wires."""
        with self.lock:
            if not self.state["auto"] or self.state["prompt"] or self.state["busy"]:
                return
            rate, printable = self.state["rx_rate"], self.state["printable"]
        # With a real common ground the console is essentially perfect ASCII; anything below that
        # means the return path is still parasitic and Ctrl-C will not reach the box either.
        good = rate > 400 and printable > 0.90
        note = (f"sygnał czysty ({printable:.0%} czytelnych) - startuję salwę Ctrl-C" if good
                else f"czekam na czysty sygnał (potrzeba >90 % czytelnych): teraz {printable:.0%} "
                     f"przy {rate:.0f} B/s" + ("" if rate else " - brak danych"))
        with self.lock:
            self.state["auto_note"] = note
        if good and time.time() - getattr(self, "_last_auto", 0) > 30:
            self._last_auto = time.time()
            self.ev(f"automat: {printable:.0%} czytelnych znaków - przerywam bootloop")
            self.q.put(("break", 75))

    def ensure_bridge(self):
        try:
            ok = self.link.start_bridge(BAUD, TX_PIN, RX_PIN, "none")
        except Exception as e:
            ok = False
            self.ev(f"start mostka nieudany: {e}")
        with self.lock:
            self.state["mode"] = (("konsola 115200 (adapter USB-TTL)" if getattr(self, "adapter_mode", "") == "direct"
                                   else "mostek UART 115200") if ok else "mostek nie wystartował - ponawiam")
        if ok:
            if getattr(self, "adapter_mode", "bridge") == "direct":
                self.ev("konsola gotowa: RXD adaptera <- pad 2 (TX boxa), TXD adaptera -> pad 3 (RX boxa)")
            else:
                self.ev(f"mostek gotowy: RX=GPIO{RX_PIN} (pad 2), TX=GPIO{TX_PIN} (pad 3)")
        return ok

    # -- main loop --------------------------------------------------------
    def run(self):
        while True:
            ads = eb.list_adapters()
            if ads:
                break
            with self.lock:
                self.state["mode"] = "brak adaptera - podłącz USB-TTL (CH340/CP2102/FTDI) albo ESP32"
                self.state["error"] = "żaden port szeregowy USB nie jest widoczny"
            time.sleep(3)
        port = eb.detect_port()
        self.adapter_mode = next((m for d, m, _ in ads if d == port), "direct")
        desc = next((x for d, m, x in ads if d == port), "")
        self.ev(f"adapter: {port} = {desc} (tryb {self.adapter_mode})")
        with self.lock:
            self.state["adapter"] = f"{port} - {desc}"
        logpath = os.path.join(OUT, f"serial-{port}.log")
        # after a forced kill the C3's USB stack can stay wedged for a few seconds ("device attached
        # to the system is not functioning"), so keep retrying instead of giving up
        for attempt in range(40):
            try:
                self.link = eb.Link(port, logpath, mode=self.adapter_mode, baud=BAUD)
                break
            except Exception as e:
                with self.lock:
                    self.state["mode"] = f"czekam na ESP32 ({attempt + 1})"
                    self.state["error"] = str(e)[-70:]
                time.sleep(2)
        else:
            with self.lock:
                self.state["mode"] = "nie udało się otworzyć portu - przepnij kabel ESP32"
            return
        with self.lock:
            self.state["error"] = ""
        with self.lock:
            self.state["port"] = port
        self.ev(f"port {port} otwarty, log -> {logpath}")
        self.ensure_bridge()
        last_recompute = 0
        last_bridge_check = time.time()
        while True:
            if not self.link.bridging and time.time() - last_bridge_check > 10:
                last_bridge_check = time.time()
                self.ensure_bridge()
            try:
                action = self.q.get_nowait()
            except queue.Empty:
                action = None
            if action:
                kind, arg = action
                with self.lock:
                    self.state["busy"] = kind
                try:
                    if kind == "diag":
                        self.do_diag()
                        self.link.start_bridge(BAUD, TX_PIN, RX_PIN, "none")
                    elif kind == "break":
                        self.do_break(int(arg or 60))
                    elif kind == "prompt":
                        self.check_prompt()
                    elif kind == "send":
                        self.do_send(arg)
                    elif kind == "burn":
                        self.do_burn()
                    elif kind == "fixhook":
                        self.do_fix_hook()
                    elif kind == "reset":
                        self.do_send("reset")
                except Exception as e:
                    self.ev(f"błąd akcji {kind}: {e}")
                    self.ensure_bridge()
                with self.lock:
                    self.state["busy"] = ""
                continue
            try:
                self.note_rx(self.link.raw(0.25))
            except Exception as e:
                self.ev(f"port padł ({e}) - wznawiam")
                time.sleep(1.0)
                self.ensure_bridge()
            self.maybe_autobreak()
            if time.time() - last_recompute > 1.0:
                self.recompute()
                last_recompute = time.time()

    # -- snapshot for the UI ---------------------------------------------
    def snapshot(self):
        with self.lock:
            s = dict(self.state)
            s["events"] = list(self.state["events"])
        now = time.time()
        rx_live = (now - s["rx_last"]) < 3 and s["rx_rate"] > 5
        tail = bytes(self.raw_tail)[-2500:]
        s["console_raw"] = tail.decode("ascii", "replace")[-2200:]
        s["console_clean"] = clean_text(tail)[-2200:]
        s["rx_live"] = rx_live
        s["tx_ok"] = bool(s["tx_proof"]) and (now - s["tx_proof_at"] < 600)
        # The ground wire cannot be probed directly, and data DOES arrive without it through a
        # parasitic return path (power supplies, Ethernet) - only badly corrupted. So judge the
        # ground by signal quality and never claim it from the mere presence of traffic.
        pr = s["printable"]
        if not rx_live:
            gnd_txt, gnd_ok = "nie wiadomo - brak danych do oceny", False
        elif pr >= 0.95:
            gnd_txt, gnd_ok = f"prawdopodobnie podłączona - sygnał czysty ({pr:.0%} czytelnych)", True
        elif pr < 0.85:
            gnd_txt, gnd_ok = (f"BRAK wspólnej masy - dane przychodzą przekłamane "
                               f"(tylko {pr:.0%} czytelnych, zera zamieniają się w jedynki)"), False
        else:
            gnd_txt, gnd_ok = f"niepewna - {pr:.0%} czytelnych, powinno być ponad 95 %", False
        s["pads_ui"] = [
            {"pad": 4, "gpio": "GND", "rola": "GND (nie da się zmierzyć wprost)",
             "stan": gnd_txt, "ok": gnd_ok},
            {"pad": 3, "gpio": (f"GPIO{TX_PIN}" if getattr(self, "adapter_mode", "") != "direct" else "TX adaptera"),
             "rola": "RX boxa (my nadajemy)",
             "stan": "potwierdzony - box odpowiedział" if s["tx_ok"] else "niepotwierdzony - box nie odpowiedział",
             "ok": s["tx_ok"]},
            {"pad": 2, "gpio": (f"GPIO{RX_PIN}" if getattr(self, "adapter_mode", "") != "direct" else "RX adaptera"),
             "rola": "TX boxa (my odbieramy)",
             "stan": (f"dane płyną: {s['rx_rate']:.0f} B/s, {pr:.0%} czytelnych" if rx_live
                      else "cisza - brak styku albo box wyłączony"),
             "ok": rx_live},
            {"pad": 1, "gpio": "-", "rola": "3V3 (kwadratowy pad)",
             "stan": "ma pozostać niepodłączony", "ok": True},
        ]
        return s


WORKER = Worker()

PAGE = """<!doctype html><html lang=pl><head><meta charset=utf-8>
<title>Beelink GT-King PRO - UART</title><meta name=viewport content="width=device-width,initial-scale=1">
<style>
:root{--bg:#0e1117;--card:#161b22;--line:#30363d;--fg:#e6edf3;--dim:#8b949e;--ok:#3fb950;--bad:#f85149;--warn:#d29922;--acc:#58a6ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 ui-monospace,Consolas,monospace}
header{padding:14px 18px;border-bottom:1px solid var(--line);display:flex;gap:16px;align-items:baseline;flex-wrap:wrap}
h1{font-size:16px;margin:0;font-weight:600}.dim{color:var(--dim)}
main{padding:16px;display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));max-width:1500px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px}
.card h2{font-size:13px;margin:0 0 10px;color:var(--dim);text-transform:uppercase;letter-spacing:.06em}
table{width:100%;border-collapse:collapse}td{padding:6px 4px;border-bottom:1px solid var(--line);vertical-align:top}
tr:last-child td{border-bottom:0}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:7px}
.on{background:var(--ok);box-shadow:0 0 7px var(--ok)}.off{background:var(--bad)}.idle{background:var(--dim)}
.big{font-size:26px;font-weight:600}
button{background:#21262d;color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:8px 12px;cursor:pointer;font:inherit;margin:3px 3px 0 0}
button:hover{border-color:var(--acc)}button.p{background:#1f6feb33;border-color:var(--acc)}
button:disabled{opacity:.45;cursor:not-allowed}
pre{background:#0d1117;border:1px solid var(--line);border-radius:6px;padding:10px;max-height:270px;overflow:auto;white-space:pre-wrap;word-break:break-all;font-size:12px;margin:0}
input{background:#0d1117;color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:8px;font:inherit;width:60%}
.ev{font-size:12px;max-height:230px;overflow:auto}.ev div{padding:2px 0;border-bottom:1px solid #21262d}
.wide{grid-column:1/-1}
</style></head><body>
<header><h1>Beelink GT-King PRO &mdash; konsola UART przez ESP32-C3</h1>
<span class=dim id=hdr>...</span></header>
<main>
 <div class=card><h2>Piny / pady</h2><table id=pads></table>
   <div class=dim style="margin-top:8px;font-size:12px">Pad 1 = kwadratowy (dolny). Dioda na ESP32 miga, gdy dane naprawdę docierają.</div></div>
 <div class=card><h2>Odbiór (pad 2)</h2>
   <div class=big id=rate>0 B/s</div>
   <table><tr><td>odebrane łącznie</td><td id=total>0</td></tr>
   <tr><td>znaki czytelne</td><td id=printable>0%</td></tr>
   <tr><td>ostatnie dane</td><td id=lastrx>nigdy</td></tr></table></div>
 <div class=card><h2>Nadawanie (pad 3)</h2>
   <div class=big id=txs>0 B</div>
   <table><tr><td>dowód odpowiedzi</td><td id=txproof>brak</td></tr>
   <tr><td>prompt u-boot</td><td id=prompt>nie</td></tr></table>
   <button onclick="act('prompt')">Test odpowiedzi</button>
   <button class=p onclick="act('break')">Przerwij bootloop (Ctrl-C, 60 s)</button></div>
 <div class=card><h2>Rozpoznane napisy u-boota</h2><table id=marks></table>
   <div class=dim style="margin-top:8px;font-size:12px">Dopasowanie odporne na przekłamania: liczy tylko bity zamienione z 0 na 1.</div></div>
 <div class=card><h2>Akcje</h2>
   <button onclick="act('diag')">Diagnostyka padów (15 s)</button>
   <button class=p onclick="act('burn')">Napraw: update + USB</button>
   <button onclick="act('fixhook')">Wpisz hook przez konsolę</button>
   <button onclick="act('reset')">reset</button>
   <button id=autob onclick="act('auto')">Automat</button>
   <div class=dim id=autonote style="margin-top:8px"></div>
   <div style="margin-top:10px"><input id=cmd placeholder="komenda u-boot, np. printenv preboot">
   <button onclick="sendCmd()">Wyślij</button></div>
   <div class=dim id=busy style="margin-top:8px"></div></div>
 <div class=card><h2>Pomiary padów</h2><table id=diag><tr><td class=dim>uruchom diagnostykę</td></tr></table></div>
 <div class="card wide"><h2>Konsola &mdash; odczyt naprawiony</h2><pre id=clean></pre></div>
 <div class="card wide"><h2>Konsola &mdash; surowe bajty</h2><pre id=raw></pre></div>
 <div class="card wide"><h2>Zdarzenia</h2><div class=ev id=events></div></div>
</main>
<script>
const $=i=>document.getElementById(i);
function dot(ok){return '<span class="dot '+(ok?'on':'off')+'"></span>'}
async function act(k){await fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:k})});tick()}
async function sendCmd(){const v=$('cmd').value;if(!v)return;await fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'send',arg:v})});$('cmd').value='';tick()}
$('cmd')&&$('cmd').addEventListener('keydown',e=>{if(e.key==='Enter')sendCmd()});
async function tick(){
 let s;try{s=await (await fetch('/api/state')).json()}catch(e){return}
 $('hdr').textContent=(s.adapter||s.port||'brak adaptera')+' | '+s.mode+(s.error?' | '+s.error:'');
 $('pads').innerHTML=s.pads_ui.map(p=>`<tr><td>${dot(p.ok)}pad ${p.pad}</td><td>${p.gpio}</td><td>${p.rola}</td><td class=dim>${p.stan}</td></tr>`).join('');
 $('rate').textContent=Math.round(s.rx_rate)+' B/s';
 $('rate').style.color=s.rx_live?'var(--ok)':'var(--bad)';
 $('total').textContent=s.rx_total.toLocaleString('pl');
 $('printable').textContent=Math.round(s.printable*100)+'%';
 $('lastrx').textContent=s.rx_last?new Date(s.rx_last*1000).toLocaleTimeString('pl'):'nigdy';
 $('txs').textContent=s.tx_sent.toLocaleString('pl')+' B';
 $('txproof').innerHTML=dot(s.tx_ok)+(s.tx_ok?'box odpowiedział':'brak odpowiedzi');
 $('prompt').innerHTML=dot(s.prompt)+(s.prompt?'TAK':'nie');
 const mk=Object.entries(s.markers||{});
 $('marks').innerHTML=mk.length?mk.map(([k,v])=>`<tr><td>${k}</td><td>${v.hits}&times;</td><td class=dim>+${v.added} bitów</td></tr>`).join(''):'<tr><td class=dim>nic jeszcze nie rozpoznano</td></tr>';
 const pd=Object.entries(s.pads||{});
 $('diag').innerHTML=pd.length?pd.map(([k,v])=>`<tr><td>GPIO${k}<br><span class=dim>${k==2?'pad 2':(k==3?'pad 3':'wolny')}</span></td><td>${v.ciaglosc||''}`+
   (v.verdict?`<br><span class=dim>${v.verdict}, impulsów ${v.pulses}, bitowych ${v.bitlike}</span>`:'')+`</td></tr>`).join(''):'<tr><td class=dim>uruchom diagnostykę</td></tr>';
 $('busy').textContent=s.busy?('trwa: '+s.busy):'';
 $('autonote').innerHTML=dot(!!s.auto)+(s.auto_note||'');
 $('autob').className=s.auto?'p':'';
 document.querySelectorAll('button').forEach(b=>{if(b.id!=='autob')b.disabled=!!s.busy});
 $('clean').textContent=s.console_clean;$('raw').textContent=s.console_raw;
 $('events').innerHTML=(s.events||[]).map(e=>`<div>${e.replace(/</g,'&lt;')}</div>`).join('');
}
tick();setInterval(tick,800);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/api/state"):
            s = WORKER.snapshot()
            s.pop("events_deque", None)
            self._send(200, json.dumps(s, default=str))
        elif self.path == "/" or self.path.startswith("/index"):
            self._send(200, PAGE, "text/html; charset=utf-8")
        else:
            self._send(404, "{}")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            body = {}
        a = body.get("action", "")
        if a == "auto":
            with WORKER.lock:
                WORKER.state["auto"] = not WORKER.state["auto"]
                on = WORKER.state["auto"]
            WORKER.ev("automat " + ("włączony" if on else "wyłączony"))
            self._send(200, json.dumps({"auto": on}))
        elif a in ("diag", "break", "prompt", "send", "burn", "fixhook", "reset"):
            WORKER.q.put((a, body.get("arg")))
            self._send(200, json.dumps({"queued": a}))
        else:
            self._send(400, json.dumps({"error": "unknown action"}))


def main():
    # Windows lets two sockets share a port when SO_REUSEADDR is on, which silently splits requests
    # between an old and a new dashboard; refuse to start instead.
    ThreadingHTTPServer.allow_reuse_address = False
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PORT_HTTP), Handler)
    except OSError as e:
        print(f"port {PORT_HTTP} jest zajęty przez inny panel ({e}) - zamknij go najpierw")
        return 1
    WORKER.start()
    print(f"dashboard: http://localhost:{PORT_HTTP}/   (Ctrl-C kończy)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
