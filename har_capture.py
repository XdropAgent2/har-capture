#!/usr/bin/env python3
"""
HAR Capture Tool — XDROP
Pakai Chrome/Edge yang udah ada di laptop. Zero Chromium bundling.
"""

import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import json
import time
import datetime
import os
import sys

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    os.system(f'"{sys.executable}" -m pip install playwright')
    from playwright.sync_api import sync_playwright


class HARBuilder:
    def __init__(self):
        self._req = {}
        self._resp = {}
        self._body = {}

    def add_request(self, rid, method, url, headers, post_data=""):
        self._req[rid] = {
            "method": method, "url": url,
            "headers": dict(headers) if headers else {},
            "postData": post_data or "", "ts": time.time(),
        }

    def add_response(self, rid, status, headers, mime="", body=""):
        if rid in self._req:
            self._resp[rid] = {
                "status": status, "headers": dict(headers) if headers else {},
                "mimeType": mime, "ts": time.time(),
            }
            if body:
                self._body[rid] = body

    def build(self):
        from urllib.parse import urlparse, parse_qs
        entries = []
        for rid, req in self._req.items():
            resp = self._resp.get(rid, {})
            elapsed = max((resp.get("ts", req["ts"]) - req["ts"]) * 1000, 0)
            try:
                qs = [{"name": k, "value": v[0]} for k, v in parse_qs(urlparse(req["url"]).query).items()]
            except Exception:
                qs = []
            entries.append({
                "startedDateTime": datetime.datetime.fromtimestamp(req["ts"], tz=datetime.timezone.utc).isoformat(),
                "time": round(elapsed, 2),
                "request": {
                    "method": req["method"], "url": req["url"], "httpVersion": "HTTP/1.1",
                    "headers": [{"name": k, "value": str(v)} for k, v in req["headers"].items()],
                    "queryString": qs, "headersSize": -1, "bodySize": len(req["postData"]),
                    "postData": {"text": req["postData"]} if req["postData"] else None, "cookies": [],
                },
                "response": {
                    "status": resp.get("status", 0), "statusText": "", "httpVersion": "HTTP/1.1",
                    "headers": [{"name": k, "value": str(v)} for k, v in resp.get("headers", {}).items()],
                    "content": {"size": len(self._body.get(rid, "")), "mimeType": resp.get("mimeType", ""), "text": self._body.get(rid, "")},
                    "cookies": [], "redirectURL": "", "headersSize": -1, "bodySize": len(self._body.get(rid, "")),
                },
                "cache": {}, "timings": {"send": 0, "wait": round(elapsed, 2), "receive": 0},
            })
        return {"log": {"version": "1.2", "creator": {"name": "XDROP HAR Capture", "version": "2.0"}, "entries": entries}}

    @property
    def count(self):
        return len(self._req)


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("⚡ XDROP HAR Capture v2")
        self.root.geometry("500x460")
        self.root.resizable(False, False)
        self.root.configure(bg="#0d1117")

        self.har = HARBuilder()
        self.pw = None
        self.browser = None
        self.page = None
        self.capturing = False
        self._detect_browsers()
        self._ui()

    def _detect_browsers(self):
        self.available = []
        paths = [
            ("Chrome", r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            ("Chrome", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
            ("Edge", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
            ("Edge", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        ]
        seen = set()
        for name, path in paths:
            if os.path.exists(path) and name not in seen:
                self.available.append((name, path))
                seen.add(name)

    def _ui(self):
        bg, fg, accent, card = "#0d1117", "#c9d1d9", "#3fb950", "#161b22"
        red = "#f85149"

        tk.Label(self.root, text="⚡ XDROP HAR Capture", font=("Consolas", 20, "bold"), bg=bg, fg=accent).pack(pady=(20, 2))
        tk.Label(self.root, text="Pakai browser lo sendiri. Ringan. No Chromium bundling.", font=("Consolas", 9), bg=bg, fg="#8b949e").pack()

        # Browser selector
        bf = tk.Frame(self.root, bg=card, padx=12, pady=10)
        bf.pack(pady=(15, 0), padx=20, fill="x")
        tk.Label(bf, text="Browser", font=("Consolas", 9, "bold"), bg=card, fg="#8b949e").pack(anchor="w")
        self.browser_var = tk.StringVar()
        if self.available:
            self.browser_var.set(self.available[0][0])
            for name, _ in self.available:
                tk.Radiobutton(bf, text=name, variable=self.browser_var, value=name,
                               font=("Consolas", 10), bg=card, fg=accent, selectcolor=bg,
                               activebackground=card, activeforeground=accent).pack(side="left", padx=8)
        else:
            tk.Label(bf, text="❌ Chrome/Edge not found", font=("Consolas", 10), bg=card, fg=red).pack()

        # URL
        uf = tk.Frame(self.root, bg=card, padx=12, pady=10)
        uf.pack(pady=(10, 0), padx=20, fill="x")
        tk.Label(uf, text="Target URL", font=("Consolas", 9, "bold"), bg=card, fg="#8b949e").pack(anchor="w")
        self.url_var = tk.StringVar(value="https://www.getmerlin.in/pricing?plan=monthly")
        tk.Entry(uf, textvariable=self.url_var, font=("Consolas", 10), bg=bg, fg=accent,
                 insertbackground=accent, relief="flat", bd=2).pack(fill="x", pady=(4, 0))

        # Buttons
        btnf = tk.Frame(self.root, bg=bg)
        btnf.pack(pady=16)
        self.start_btn = tk.Button(btnf, text="▶  START", font=("Consolas", 14, "bold"),
                                   bg="#238636", fg="white", activebackground="#2ea043",
                                   relief="flat", padx=20, pady=8, cursor="hand2", command=self._start)
        self.start_btn.pack(side="left", padx=6)
        self.stop_btn = tk.Button(btnf, text="⏹  STOP & SAVE", font=("Consolas", 14, "bold"),
                                  bg="#da3633", fg="white", activebackground="#f85149",
                                  relief="flat", padx=20, pady=8, cursor="hand2",
                                  state="disabled", command=self._stop)
        self.stop_btn.pack(side="left", padx=6)

        # Status
        self.status = tk.StringVar(value="Ready.")
        tk.Label(self.root, textvariable=self.status, font=("Consolas", 11), bg=bg, fg="#8b949e").pack(pady=(8, 2))
        self.counter = tk.StringVar(value="Requests: 0")
        tk.Label(self.root, textvariable=self.counter, font=("Consolas", 10), bg=bg, fg="#484f58").pack()
        self.file_lbl = tk.Label(self.root, text="", font=("Consolas", 9), bg=bg, fg="#8b949e")
        self.file_lbl.pack(pady=(4, 0))

        self._tick()

    def _tick(self):
        if self.capturing:
            self.counter.set(f"Requests captured: {self.har.count}")
        self.root.after(400, self._tick)

    def _start(self):
        if not self.available:
            messagebox.showerror("Error", "Chrome/Edge not found!")
            return
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.status.set("🟡 Opening browser...")
        self.capturing = True
        self.har = HARBuilder()
        self.file_lbl.config(text="")
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            self.pw = sync_playwright().start()

            # Find selected browser path
            selected = self.browser_var.get()
            exe = None
            for name, path in self.available:
                if name == selected:
                    exe = path
                    break

            self.browser = self.pw.chromium.launch(
                headless=False,
                executable_path=exe,
                args=["--disable-blink-features=AutomationControlled", "--no-first-run"],
            )
            ctx = self.browser.new_context(ignore_https_errors=True)
            self.page = ctx.new_page()

            # CDP
            cdp = ctx.new_cdp_session(self.page)
            cdp.send("Network.enable")
            cdp.on("Network.requestWillBeSent", lambda p: self.har.add_request(
                p.get("requestId", ""), p.get("request", {}).get("method", "GET"),
                p.get("request", {}).get("url", ""), p.get("request", {}).get("headers", {}),
                p.get("request", {}).get("postData", "")
            ))
            cdp.on("Network.responseReceived", lambda p: self.har.add_response(
                p.get("requestId", ""), p.get("response", {}).get("status", 0),
                p.get("response", {}).get("headers", {}), p.get("response", {}).get("mimeType", "")
            ))

            # PW backup
            self.page.on("request", lambda r: self.har.add_request(f"pw_{id(r)}", r.method, r.url, r.headers, r.post_data or ""))
            self.page.on("response", lambda r: self.har.add_response(f"pw_{id(r.request)}", r.status, r.headers, r.headers.get("content-type", "")))

            self.page.goto(self.url_var.get(), wait_until="domcontentloaded", timeout=30000)
            self._set_status("🟢 Recording... Close browser atau STOP")

            while self.capturing:
                try:
                    self.page.evaluate("1")
                except Exception:
                    break
                time.sleep(0.3)
        except Exception as e:
            self._set_status(f"❌ {e}")
        finally:
            if self.capturing:
                self.root.after(0, self._stop)

    def _set_status(self, t):
        self.root.after(0, lambda: self.status.set(t))

    def _stop(self):
        self.capturing = False
        self._set_status("⏳ Saving...")
        self.root.update()

        har = self.har.build()
        n = len(har["log"]["entries"])
        if n == 0:
            self._set_status("⚠️ No requests captured.")
            self._reset()
            return

        fp = filedialog.asksaveasfilename(
            defaultextension=".har", filetypes=[("HAR", "*.har")],
            initialfile=f"merlin_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.har"
        )
        if fp:
            with open(fp, "w", encoding="utf-8") as f:
                json.dump(har, f, indent=2, ensure_ascii=False)
            self._set_status(f"✅ Saved {n} requests!")
            self.file_lbl.config(text=f"📁 {fp}")
        else:
            self._set_status(f"Cancelled. {n} requests lost.")

        try:
            if self.browser: self.browser.close()
        except: pass
        try:
            if self.pw: self.pw.stop()
        except: pass
        self._reset()

    def _reset(self):
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", lambda: (setattr(self, 'capturing', False), self.root.destroy()))
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
