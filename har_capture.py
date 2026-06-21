#!/usr/bin/env python3
"""
HAR Capture Tool — XDROP
Double-click .exe → browser opens → registrasi/payment → Stop → HAR saved.
"""

import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import json
import time
import datetime
import os
import sys
import traceback

# PyInstaller-friendly imports
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright"])
    subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
    from playwright.sync_api import sync_playwright


class HARBuilder:
    """Builds HAR 1.2 from captured network events."""

    def __init__(self):
        self.entries = []
        self._req = {}
        self._resp = {}
        self._body = {}

    def add_request(self, rid, method, url, headers, post_data=""):
        self._req[rid] = {
            "method": method,
            "url": url,
            "headers": dict(headers) if headers else {},
            "postData": post_data or "",
            "ts": time.time(),
        }

    def add_response(self, rid, status, status_text, headers, mime="", body=""):
        if rid in self._req:
            self._resp[rid] = {
                "status": status,
                "statusText": status_text,
                "headers": dict(headers) if headers else {},
                "mimeType": mime,
                "ts": time.time(),
            }
            if body:
                self._body[rid] = body

    def build(self):
        entries = []
        for rid, req in self._req.items():
            resp = self._resp.get(rid, {})
            started = req["ts"]
            ended = resp.get("ts", started)
            elapsed = max((ended - started) * 1000, 0)

            req_headers = [{"name": k, "value": str(v)} for k, v in req["headers"].items()]
            resp_headers = [{"name": k, "value": str(v)} for k, v in resp.get("headers", {}).items()]

            entry = {
                "startedDateTime": datetime.datetime.fromtimestamp(
                    started, tz=datetime.timezone.utc
                ).isoformat(),
                "time": round(elapsed, 2),
                "request": {
                    "method": req["method"],
                    "url": req["url"],
                    "httpVersion": "HTTP/1.1",
                    "headers": req_headers,
                    "queryString": self._parse_query(req["url"]),
                    "headersSize": -1,
                    "bodySize": len(req["postData"]),
                    "postData": {"text": req["postData"]} if req["postData"] else None,
                    "cookies": [],
                },
                "response": {
                    "status": resp.get("status", 0),
                    "statusText": resp.get("statusText", ""),
                    "httpVersion": "HTTP/1.1",
                    "headers": resp_headers,
                    "content": {
                        "size": len(self._body.get(rid, "")),
                        "mimeType": resp.get("mimeType", ""),
                        "text": self._body.get(rid, ""),
                    },
                    "cookies": [],
                    "redirectURL": "",
                    "headersSize": -1,
                    "bodySize": len(self._body.get(rid, "")),
                },
                "cache": {},
                "timings": {"send": 0, "wait": round(elapsed, 2), "receive": 0},
            }
            entries.append(entry)

        return {
            "log": {
                "version": "1.2",
                "creator": {"name": "XDROP HAR Capture", "version": "1.0"},
                "entries": entries,
            }
        }

    def _parse_query(self, url):
        from urllib.parse import urlparse, parse_qs
        try:
            parsed = urlparse(url)
            return [{"name": k, "value": v[0]} for k, v in parse_qs(parsed.query).items()]
        except Exception:
            return []

    @property
    def count(self):
        return len(self._req)


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("⚡ XDROP HAR Capture")
        self.root.geometry("480x420")
        self.root.resizable(False, False)
        self.root.configure(bg="#0d1117")

        self.har = HARBuilder()
        self.pw_instance = None
        self.browser = None
        self.page = None
        self.capturing = False
        self._thread = None
        self._saved_path = None

        self._ui()

    def _ui(self):
        bg = "#0d1117"
        fg = "#c9d1d9"
        accent = "#3fb950"
        red = "#f85149"
        card_bg = "#161b22"

        # Header
        tk.Label(
            self.root, text="⚡ XDROP HAR Capture",
            font=("Consolas", 20, "bold"), bg=bg, fg=accent
        ).pack(pady=(25, 2))

        tk.Label(
            self.root, text="Start → registrasi & payment → Stop → HAR auto-saved",
            font=("Consolas", 9), bg=bg, fg="#8b949e"
        ).pack()

        # URL card
        card = tk.Frame(self.root, bg=card_bg, padx=12, pady=10)
        card.pack(pady=(18, 0), padx=20, fill="x")

        tk.Label(card, text="Target URL", font=("Consolas", 9, "bold"),
                 bg=card_bg, fg="#8b949e").pack(anchor="w")
        self.url_var = tk.StringVar(value="https://www.getmerlin.in/pricing?plan=monthly")
        tk.Entry(
            card, textvariable=self.url_var, font=("Consolas", 10),
            bg="#0d1117", fg=accent, insertbackground=accent,
            relief="flat", bd=2
        ).pack(fill="x", pady=(4, 0))

        # Buttons
        btn_frame = tk.Frame(self.root, bg=bg)
        btn_frame.pack(pady=18)

        self.start_btn = tk.Button(
            btn_frame, text="▶  START CAPTURE", font=("Consolas", 14, "bold"),
            bg="#238636", fg="white", activebackground="#2ea043",
            activeforeground="white", relief="flat", padx=24, pady=10,
            cursor="hand2", command=self._start
        )
        self.start_btn.pack(side="left", padx=6)

        self.stop_btn = tk.Button(
            btn_frame, text="⏹  STOP & SAVE", font=("Consolas", 14, "bold"),
            bg="#da3633", fg="white", activebackground="#f85149",
            activeforeground="white", relief="flat", padx=24, pady=10,
            cursor="hand2", state="disabled", command=self._stop
        )
        self.stop_btn.pack(side="left", padx=6)

        # Status
        self.status = tk.StringVar(value="Ready. Klik START untuk mulai.")
        tk.Label(
            self.root, textvariable=self.status,
            font=("Consolas", 11), bg=bg, fg="#8b949e"
        ).pack(pady=(8, 2))

        # Counter
        self.counter = tk.StringVar(value="Requests: 0")
        tk.Label(
            self.root, textvariable=self.counter,
            font=("Consolas", 10), bg=bg, fg="#484f58"
        ).pack()

        # File saved
        self.file_label = tk.Label(
            self.root, text="", font=("Consolas", 9),
            bg=bg, fg="#8b949e", cursor="hand2"
        )
        self.file_label.pack(pady=(4, 0))

        self._tick()

    def _tick(self):
        if self.capturing:
            self.counter.set(f"Requests captured: {self.har.count}")
        self.root.after(400, self._tick)

    def _start(self):
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.url_entry_state("disabled")
        self.status.set("🟡 Opening browser...")
        self.capturing = True
        self.har = HARBuilder()
        self._saved_path = None
        self.file_label.config(text="")

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def url_entry_state(self, state):
        for widget in self.root.winfo_children():
            if isinstance(widget, tk.Frame):
                for child in widget.winfo_children():
                    if isinstance(child, tk.Entry):
                        child.config(state=state)

    def _run(self):
        try:
            self.pw_instance = sync_playwright().start()

            # Use bundled chromium or system chrome
            try:
                self.browser = self.pw_instance.chromium.launch(
                    headless=False,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-first-run",
                        "--no-default-browser-check",
                    ]
                )
            except Exception as e:
                self._set_status(f"❌ Browser error: {e}")
                return

            self.context = self.browser.new_context(
                ignore_https_errors=True,
            )
            self.page = self.context.new_page()

            # CDP for full network capture
            cdp = self.context.new_cdp_session(self.page)
            cdp.send("Network.enable")
            cdp.on("Network.requestWillBeSent", self._on_cdp_req)
            cdp.on("Network.responseReceived", self._on_cdp_resp)

            # Playwright events as backup
            self.page.on("request", self._on_pw_req)
            self.page.on("response", self._on_pw_resp)

            # Navigate
            url = self.url_var.get()
            self.page.goto(url, wait_until="domcontentloaded", timeout=30000)

            self._set_status("🟢 Recording... Close browser atau klik STOP")

            # Keep alive until browser closes or stop
            while self.capturing:
                try:
                    self.page.evaluate("1")
                except Exception:
                    break
                time.sleep(0.3)

        except Exception as e:
            self._set_status(f"❌ Error: {e}")
        finally:
            if self.capturing:
                self.root.after(0, self._stop)

    def _on_cdp_req(self, params):
        req = params.get("request", {})
        rid = params.get("requestId", "")
        self.har.add_request(
            rid, req.get("method", "GET"), req.get("url", ""),
            req.get("headers", {}), req.get("postData", "")
        )

    def _on_cdp_resp(self, params):
        rid = params.get("requestId", "")
        resp = params.get("response", {})
        body = ""
        try:
            result = self.page.context.new_cdp_session(self.page).send(
                "Network.getResponseBody", {"requestId": rid}
            )
            body = result.get("body", "")
        except Exception:
            pass
        self.har.add_response(
            rid, resp.get("status", 0), resp.get("statusText", ""),
            resp.get("headers", {}), resp.get("mimeType", ""), body
        )

    def _on_pw_req(self, req):
        rid = f"pw_{id(req)}"
        self.har.add_request(rid, req.method, req.url, req.headers, req.post_data or "")

    def _on_pw_resp(self, resp):
        rid = f"pw_{id(resp.request)}"
        if rid in self.har._req:
            body = ""
            try:
                body = resp.text()
            except Exception:
                pass
            self.har.add_response(
                rid, resp.status, "", resp.headers,
                resp.headers.get("content-type", ""), body
            )

    def _set_status(self, text):
        self.root.after(0, lambda: self.status.set(text))

    def _stop(self):
        self.capturing = False
        self._set_status("⏳ Saving HAR...")
        self.root.update()

        har_data = self.har.build()
        count = len(har_data["log"]["entries"])

        if count == 0:
            self._set_status("⚠️ No requests captured. Coba lagi.")
            self._reset_ui()
            return

        # Ask save location
        default_name = f"merlin_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.har"
        filepath = filedialog.asksaveasfilename(
            defaultextension=".har",
            filetypes=[("HAR files", "*.har"), ("All files", "*.*")],
            initialfile=default_name,
            title="Save HAR File"
        )

        if filepath:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(har_data, f, indent=2, ensure_ascii=False)
            self._set_status(f"✅ Saved {count} requests!")
            self._saved_path = filepath
            self.file_label.config(text=f"📁 {filepath}")
        else:
            self._set_status(f"Cancelled. {count} requests not saved.")

        # Close browser
        self._close_browser()
        self._reset_ui()

    def _close_browser(self):
        try:
            if self.browser:
                self.browser.close()
        except Exception:
            pass
        try:
            if self.pw_instance:
                self.pw_instance.stop()
        except Exception:
            pass

    def _reset_ui(self):
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.url_entry_state("normal")

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        self.capturing = False
        self._close_browser()
        self.root.destroy()


def main():
    # Playwright install check (for first run / .exe)
    try:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        pw.chromium.launch(headless=True).close()
        pw.stop()
    except Exception:
        print("First run — installing browser engine...")
        os.system(f'"{sys.executable}" -m playwright install chromium')

    app = App()
    app.run()


if __name__ == "__main__":
    main()
