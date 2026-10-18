"""Boot the production WSGI server and check an authenticated HTTP flow over a real socket."""

import http.cookiejar
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path


class LiveServerTests(unittest.TestCase):
    def test_gunicorn_boot_login_create_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            base = f"http://127.0.0.1:{port}"
            env = {
                **os.environ,
                "APP_PASSWORD": "live-test-only-password",
                "APP_ENV": "local",
                "APP_PASSWORD_HASH": "",
                "APP_ORIGIN": "",
                "DATABASE_PATH": str(Path(directory) / "live.sqlite3"),
                "OPENAI_API_KEY": "",
            }
            command = [
                sys.executable,
                "-m",
                "gunicorn",
                "--bind",
                f"127.0.0.1:{port}",
                "--workers",
                "1",
                "--threads",
                "2",
                "shopee_workbench.app:create_app()",
            ]

            def launch():
                process = subprocess.Popen(
                    command, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
                )
                for _ in range(100):
                    try:
                        with urllib.request.urlopen(
                            base + "/api/health", timeout=1
                        ) as response:
                            if response.status == 200:
                                return process
                    except (urllib.error.URLError, TimeoutError):
                        pass
                    if process.poll() is not None:
                        raise AssertionError(process.stderr.read().decode())
                    time.sleep(0.05)
                process.terminate()
                process.wait(timeout=5)
                raise AssertionError("server did not start")

            server = launch()
            try:
                jar = http.cookiejar.CookieJar()
                opener = urllib.request.build_opener(
                    urllib.request.HTTPCookieProcessor(jar)
                )

                def call(path, body=None, csrf=None):
                    headers = {"Content-Type": "application/json"}
                    if csrf:
                        headers["X-CSRF-Token"] = csrf
                    request = urllib.request.Request(
                        base + path,
                        data=json.dumps(body).encode() if body is not None else None,
                        headers=headers,
                    )
                    with opener.open(request, timeout=5) as response:
                        return response.status, response.read(), response.headers

                status, root, _ = call("/")
                self.assertEqual(status, 200)
                self.assertIn(b"app.js", root)
                for asset in ["/assets/app.js", "/assets/styles.css"]:
                    self.assertEqual(call(asset)[0], 200)
                csrf = json.loads(call("/api/session")[1])["csrf"]
                result = json.loads(
                    call("/api/login", {"password": env["APP_PASSWORD"]}, csrf)[1]
                )
                csrf = result["csrf"]
                self.assertTrue(result["authenticated"])
                self.assertEqual(json.loads(call("/api/bootstrap")[1])["products"], [])
                saved = json.loads(
                    call(
                        "/api/products",
                        {"name": "Live test notebook", "market": "SG"},
                        csrf,
                    )[1]
                )
                self.assertIn("id", saved)
                self.assertEqual(
                    len(json.loads(call("/api/bootstrap")[1])["products"]), 1
                )
                server.terminate()
                server.wait(timeout=10)
                server.stderr.close()
                server = launch()
                # Both product data and the opaque login session survive process restart.
                loaded = json.loads(call("/api/bootstrap")[1])
                self.assertEqual(loaded["products"][0]["id"], saved["id"])
            finally:
                server.terminate()
                server.wait(timeout=10)
                server.stderr.close()
