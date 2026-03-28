"""
Run the public miniapp tunnel + miniapp_server + bot.

When the tunnel drops, reconnect and restart the bot so Telegram uses the
latest MINI_APP_URL from .env.
"""

import json
import os
import re
import signal
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(BASE_DIR, ".env")
SSH_EXE = shutil.which("ssh") or r"C:\Program Files\Git\usr\bin\ssh.exe"
PYTHON_EXE = sys.executable

WATCHDOG_INTERVAL_SECONDS = 45
WATCHDOG_GRACE_SECONDS = 75
WATCHDOG_FAILURE_THRESHOLD = 4
WATCHDOG_REQUIRED_STABLE_SECONDS = 120
WATCHDOG_COLD_START_TIMEOUT_SECONDS = WATCHDOG_GRACE_SECONDS + WATCHDOG_REQUIRED_STABLE_SECONDS
SERVER_WATCHDOG_INTERVAL_SECONDS = 6
SERVER_WATCHDOG_FAILURE_THRESHOLD = 3
SERVER_WATCHDOG_STARTUP_GRACE_SECONDS = 15

bot_proc = None
tunnel_proc = None
miniapp_proc = None
stop_flag = threading.Event()
current_url = None
current_tunnel_name = None
current_url_ready_at = 0.0
last_tunnel_ok_at = 0.0
current_url_started_at = 0.0
last_miniapp_restart_at = 0.0


def log(msg: str) -> None:
    print(f"[start_miniapp] {msg}", flush=True)


def update_env_url(new_url: str) -> None:
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    if re.search(r"(?m)^MINI_APP_URL=", content):
        content = re.sub(r"(?m)^MINI_APP_URL=.*$", f"MINI_APP_URL={new_url}", content)
    else:
        content = content.rstrip("\r\n") + f"\nMINI_APP_URL={new_url}\n"

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write(content)

    log(f"Updated MINI_APP_URL={new_url}")


def kill_proc(proc, name: str = "") -> None:
    if proc and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        if name:
            log(f"{name} stopped")


def _find_listener_pid(port: int) -> int | None:
    try:
        result = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return None

    needle = f":{port}"
    for line in result.stdout.splitlines():
        line = line.strip()
        if "LISTENING" not in line or needle not in line:
            continue
        parts = line.split()
        if len(parts) >= 5:
            try:
                return int(parts[-1])
            except ValueError:
                continue
    return None


def _process_command_line(pid: int) -> str:
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-CimInstance Win32_Process -Filter \"ProcessId = {pid}\").CommandLine",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return ""
    return (result.stdout or "").strip()


def _terminate_pid(pid: int, name: str) -> bool:
    try:
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return False

    if result.returncode == 0:
        log(f"{name} stopped (PID {pid})")
        return True
    return False


def start_bot() -> None:
    global bot_proc
    kill_proc(bot_proc, "bot")

    import tempfile

    lock = os.path.join(tempfile.gettempdir(), "buyer_bot.lock")
    for attempt in range(8):
        try:
            os.remove(lock)
            break
        except FileNotFoundError:
            break
        except PermissionError:
            if attempt == 0:
                try:
                    with open(lock, "r", encoding="utf-8") as f:
                        pid = int(f.read().strip())
                    log(f"Found running bot from lock (PID {pid}); stopping it before restart")
                    subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
                except Exception:
                    pass
            time.sleep(0.5)

    log("Starting bot...")
    bot_proc = subprocess.Popen([PYTHON_EXE, "main.py"], cwd=BASE_DIR)
    log(f"Bot started (PID {bot_proc.pid})")


def start_miniapp_server():
    global miniapp_proc, last_miniapp_restart_at

    listener_pid = _find_listener_pid(8080)
    if listener_pid:
        cmd = _process_command_line(listener_pid).lower()
        if "miniapp_server.py" in cmd:
            log(f"Found stale miniapp_server on :8080 (PID {listener_pid}); restarting it")
            _terminate_pid(listener_pid, "miniapp_server")
            time.sleep(1)
        else:
            log(f"Port :8080 is already used by PID {listener_pid}; leaving it untouched")
            return None

    if miniapp_proc and miniapp_proc.poll() is None:
        log(
            "Tracked miniapp_server process is still running without serving "
            f":8080 (PID {miniapp_proc.pid}); restarting it"
        )
        kill_proc(miniapp_proc, "miniapp_server")
        time.sleep(1)

    log("Starting miniapp_server...")
    miniapp_proc = subprocess.Popen([PYTHON_EXE, "miniapp_server.py"], cwd=BASE_DIR)
    last_miniapp_restart_at = time.monotonic()
    log(f"miniapp_server started (PID {miniapp_proc.pid})")
    return miniapp_proc


def build_tunnel_provider() -> dict[str, object] | None:
    if not os.path.exists(SSH_EXE):
        return None

    return {
        "name": "localhost.run",
        "command": [
            SSH_EXE,
            "-T",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "ServerAliveInterval=30",
            "-o",
            "ServerAliveCountMax=3",
            "-o",
            "ExitOnForwardFailure=yes",
            "-R",
            "80:127.0.0.1:8080",
            "nokey@localhost.run",
        ],
        "url_pattern": r"https://[\w\-]+\.lhr\.life",
    }


def _request_status(url: str, timeout: int = 10):
    proxy_handler = urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(proxy_handler)
    req = urllib.request.Request(url, headers={"User-Agent": "watchdog/1.0"})
    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.status, resp.read(512)
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(512)
        except Exception:
            body = b""
        return exc.code, body
    except Exception:
        return None, b""


def tunnel_is_alive(url: str) -> bool:
    """Check that the public tunnel serves the miniapp, not just SSH."""
    status, body = _request_status(url + "/api/health")
    if status == 200:
        try:
            payload = json.loads(body.decode("utf-8"))
            if payload.get("ok") is True:
                return True
        except Exception:
            pass

    status, _body = _request_status(url + "/")
    return status is not None and status < 500


def server_has_active_requests() -> bool:
    """Check whether miniapp_server is currently handling heavy work."""
    status, body = _request_status("http://127.0.0.1:8080/api/health", timeout=3)
    if status != 200:
        return False

    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        return False

    return payload.get("active_requests", 0) > 0


def local_server_is_alive() -> bool:
    """Check that miniapp_server is reachable on the local port."""
    status, body = _request_status("http://127.0.0.1:8080/api/health", timeout=3)
    if status != 200:
        return False
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        return False
    return payload.get("ok") is True


def server_watchdog() -> None:
    """Restart the local miniapp server if it exits or stops answering health checks."""
    global current_url_ready_at

    fail_count = 0
    time.sleep(10)

    while not stop_flag.is_set():
        now = time.monotonic()
        within_startup_grace = (
            last_miniapp_restart_at
            and (now - last_miniapp_restart_at) < SERVER_WATCHDOG_STARTUP_GRACE_SECONDS
        )
        if within_startup_grace:
            stop_flag.wait(timeout=SERVER_WATCHDOG_INTERVAL_SECONDS)
            continue

        proc_exited = miniapp_proc is not None and miniapp_proc.poll() is not None

        if local_server_is_alive():
            fail_count = 0
        else:
            fail_count += 1
            if proc_exited or fail_count >= SERVER_WATCHDOG_FAILURE_THRESHOLD:
                if proc_exited:
                    exit_code = miniapp_proc.poll()
                    log(
                        "Server watchdog: miniapp_server exited "
                        f"(code {exit_code}); restarting..."
                    )
                else:
                    log(
                        "Server watchdog: local /api/health failed "
                        f"{fail_count} times; restarting miniapp_server..."
                    )

                kill_proc(miniapp_proc, "miniapp_server")
                start_miniapp_server()
                current_url_ready_at = max(
                    current_url_ready_at,
                    time.monotonic() + SERVER_WATCHDOG_STARTUP_GRACE_SECONDS,
                )
                fail_count = 0
            else:
                log(
                    "Server watchdog: local /api/health failed "
                    f"({fail_count}/{SERVER_WATCHDOG_FAILURE_THRESHOLD}); waiting..."
                )

        stop_flag.wait(timeout=SERVER_WATCHDOG_INTERVAL_SECONDS)


def watchdog() -> None:
    """Probe the current public URL and only recycle the tunnel after repeated failures."""
    global tunnel_proc, current_url, current_url_ready_at, last_tunnel_ok_at, current_url_started_at

    fail_count = 0
    last_checked_url = None
    time.sleep(30)

    while not stop_flag.is_set():
        url = current_url
        if url and tunnel_proc and tunnel_proc.poll() is None:
            if url != last_checked_url:
                last_checked_url = url
                fail_count = 0
                last_tunnel_ok_at = 0.0

            now = time.monotonic()
            if current_url_ready_at and now < current_url_ready_at:
                stop_flag.wait(timeout=min(WATCHDOG_INTERVAL_SECONDS, current_url_ready_at - now))
                continue

            if tunnel_is_alive(url):
                fail_count = 0
                last_tunnel_ok_at = now
            else:
                fail_count += 1
                stable_enough = last_tunnel_ok_at and (now - last_tunnel_ok_at) >= WATCHDOG_REQUIRED_STABLE_SECONDS
                cold_start_timed_out = (
                    not last_tunnel_ok_at
                    and current_url_started_at
                    and (now - current_url_started_at) >= WATCHDOG_COLD_START_TIMEOUT_SECONDS
                )

                if fail_count >= WATCHDOG_FAILURE_THRESHOLD:
                    if server_has_active_requests():
                        log("Watchdog: tunnel check failed, but miniapp_server has active requests; waiting...")
                        fail_count = WATCHDOG_FAILURE_THRESHOLD - 1
                    elif cold_start_timed_out:
                        log(
                            f"Watchdog: tunnel {url} never became healthy after "
                            f"{WATCHDOG_COLD_START_TIMEOUT_SECONDS}s; reconnecting..."
                        )
                        kill_proc(tunnel_proc, "tunnel (watchdog)")
                        fail_count = 0
                    elif not stable_enough:
                        log(
                            "Watchdog: tunnel is still warming up or edge is unstable "
                            f"({fail_count}/{WATCHDOG_FAILURE_THRESHOLD}); not recycling yet."
                        )
                    else:
                        log(
                            f"Watchdog: tunnel {url} failed "
                            f"{WATCHDOG_FAILURE_THRESHOLD} checks; reconnecting..."
                        )
                        kill_proc(tunnel_proc, "tunnel (watchdog)")
                        fail_count = 0
                else:
                    log(
                        "Watchdog: tunnel check failed "
                        f"({fail_count}/{WATCHDOG_FAILURE_THRESHOLD}); waiting for the next probe..."
                    )

        stop_flag.wait(timeout=WATCHDOG_INTERVAL_SECONDS)


def run_tunnel() -> None:
    """Run the localhost.run tunnel and refresh the bot whenever a new URL appears."""
    global tunnel_proc, current_url, current_tunnel_name
    global current_url_ready_at, last_tunnel_ok_at, current_url_started_at

    provider = build_tunnel_provider()
    if not provider:
        log("Git SSH not found. Install Git for Windows to use localhost.run.")
        stop_flag.set()
        return

    while not stop_flag.is_set():
        current_tunnel_name = str(provider["name"])
        log(f"Connecting via {current_tunnel_name}...")

        try:
            tunnel_proc = subprocess.Popen(
                provider["command"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError:
            log(f"{current_tunnel_name} executable not found.")
            stop_flag.set()
            return

        bot_started = False
        assert tunnel_proc.stdout is not None
        for line in tunnel_proc.stdout:
            if stop_flag.is_set():
                break

            line = line.rstrip()
            if line:
                print(f"  [tunnel] {line}", flush=True)

            match = re.search(str(provider["url_pattern"]), line)
            if not match:
                continue

            new_url = match.group(0)
            if new_url != current_url:
                current_url = new_url
                current_url_started_at = time.monotonic()
                current_url_ready_at = time.monotonic() + WATCHDOG_GRACE_SECONDS
                last_tunnel_ok_at = 0.0
                update_env_url(new_url)
                start_bot()
                bot_started = True
            elif not bot_started:
                start_bot()
                bot_started = True

        tunnel_proc.wait()
        provider_was_healthy = bool(last_tunnel_ok_at)
        previous_provider = current_tunnel_name

        current_url = None
        current_tunnel_name = None
        current_url_started_at = 0.0
        current_url_ready_at = 0.0
        last_tunnel_ok_at = 0.0

        if not stop_flag.is_set():
            if not provider_was_healthy:
                log(f"{previous_provider} disconnected before health confirmation. Reconnecting in 3 seconds...")
            else:
                log(f"{previous_provider} disconnected. Reconnecting in 3 seconds...")
            time.sleep(3)


def on_exit(_signum, _frame) -> None:
    log("Shutting down...")
    stop_flag.set()
    kill_proc(tunnel_proc, "tunnel")
    kill_proc(bot_proc, "bot")
    kill_proc(miniapp_proc, "miniapp_server")
    raise SystemExit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, on_exit)
    signal.signal(signal.SIGTERM, on_exit)

    log("=== Starting miniapp + bot + tunnel ===")
    start_miniapp_server()

    tunnel_thread = threading.Thread(target=run_tunnel, daemon=True)
    tunnel_thread.start()

    watchdog_thread = threading.Thread(target=watchdog, daemon=True)
    watchdog_thread.start()

    server_watchdog_thread = threading.Thread(target=server_watchdog, daemon=True)
    server_watchdog_thread.start()

    try:
        while tunnel_thread.is_alive():
            tunnel_thread.join(timeout=1)
    except KeyboardInterrupt:
        on_exit(None, None)
