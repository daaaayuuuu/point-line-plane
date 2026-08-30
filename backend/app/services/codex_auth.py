from __future__ import annotations

import base64
import binascii
import json
import os
import queue
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4


class CodexAuthError(RuntimeError):
    """Raised when the local Codex app-server cannot complete an auth request."""


@dataclass(frozen=True, slots=True)
class CodexAccount:
    email: str
    plan_type: str | None
    display_name: str | None = None


@dataclass(frozen=True, slots=True)
class CodexLoginAttempt:
    attempt_id: str
    status: str
    auth_url: str | None = None
    account: CodexAccount | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class CodexTurnResult:
    thread_id: str
    turn_id: str
    text: str


@dataclass(slots=True)
class _AttemptState:
    login_id: str
    expires_at: float
    error: str | None = None


class CodexAuthBridge:
    """Small synchronous JSON-RPC client for the official Codex app-server.

    The bridge is intentionally local-only for the MVP: one app-server process
    owns one isolated CODEX_HOME, while the browser receives only the official
    authorization URL and an opaque attempt id.
    """

    def __init__(
        self,
        *,
        command: str,
        auth_root: Path,
        request_timeout_seconds: float = 15.0,
        login_timeout_seconds: float = 600.0,
        turn_timeout_seconds: float = 180.0,
    ) -> None:
        self.command = command
        self.auth_root = auth_root
        self.request_timeout_seconds = request_timeout_seconds
        self.login_timeout_seconds = login_timeout_seconds
        self.turn_timeout_seconds = turn_timeout_seconds
        self._process: subprocess.Popen[str] | None = None
        self._reader: threading.Thread | None = None
        self._stderr_reader: threading.Thread | None = None
        self._write_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._next_id = 1
        self._pending: dict[int, queue.Queue[dict[str, Any]]] = {}
        self._attempts: dict[str, _AttemptState] = {}
        self._login_attempts: dict[str, str] = {}
        self._thread_streams: dict[str, list[queue.Queue[dict[str, Any]]]] = {}
        self._thread_locks: dict[str, threading.Lock] = {}
        self._stopping = False

    def start_login(self) -> CodexLoginAttempt:
        account = self.read_account(refresh_token=False)
        if account:
            return CodexLoginAttempt(
                attempt_id=str(uuid4()),
                status="authenticated",
                account=account,
            )

        result = self._request(
            "account/login/start",
            {
                "type": "chatgpt",
                "useHostedLoginSuccessPage": True,
                "appBrand": "chatgpt",
            },
            timeout_seconds=30.0,
        )
        auth_url = result.get("authUrl")
        login_id = result.get("loginId")
        if not isinstance(auth_url, str) or not auth_url.startswith("https://"):
            raise CodexAuthError("官方授权地址无效。")
        if not isinstance(login_id, str) or not login_id:
            raise CodexAuthError("官方登录流程未返回登录 ID。")

        attempt_id = str(uuid4())
        with self._state_lock:
            self._attempts[attempt_id] = _AttemptState(
                login_id=login_id,
                expires_at=time.monotonic() + self.login_timeout_seconds,
            )
            self._login_attempts[login_id] = attempt_id
        return CodexLoginAttempt(
            attempt_id=attempt_id,
            status="pending",
            auth_url=auth_url,
        )

    def login_status(self, attempt_id: str) -> CodexLoginAttempt:
        with self._state_lock:
            state = self._attempts.get(attempt_id)
            if state is None:
                raise CodexAuthError("登录请求不存在或已过期。")
            expired = time.monotonic() >= state.expires_at
            error = state.error
        if error:
            return CodexLoginAttempt(attempt_id=attempt_id, status="failed", error=error)
        if expired:
            self._forget_attempt(attempt_id)
            return CodexLoginAttempt(
                attempt_id=attempt_id,
                status="failed",
                error="官方授权已超时，请重新登录。",
            )

        account = self.read_account(refresh_token=False)
        if account:
            self._forget_attempt(attempt_id)
            return CodexLoginAttempt(
                attempt_id=attempt_id,
                status="authenticated",
                account=account,
            )
        return CodexLoginAttempt(attempt_id=attempt_id, status="pending")

    def read_account(self, *, refresh_token: bool) -> CodexAccount | None:
        identity_claim = self._read_identity_claim()
        result = self._request(
            "account/read",
            {"refreshToken": refresh_token},
            timeout_seconds=30.0 if refresh_token else None,
        )
        account = result.get("account")
        if not isinstance(account, dict) or account.get("type") != "chatgpt":
            return None
        email = account.get("email")
        if not isinstance(email, str) or not email.strip():
            raise CodexAuthError("该 ChatGPT 账号没有可用邮箱，暂时无法创建本地用户。")
        plan_type = account.get("planType")
        normalized_email = email.strip().lower()
        claimed_name = (
            identity_claim[1]
            if identity_claim and identity_claim[0] == normalized_email
            else self._read_display_name(expected_email=normalized_email)
        )
        return CodexAccount(
            email=normalized_email,
            plan_type=plan_type if isinstance(plan_type, str) else None,
            display_name=claimed_name,
        )

    def _read_identity_claim(self) -> tuple[str, str] | None:
        """Read optional display claims before app-server migrates the auth file."""
        try:
            auth_data = json.loads((self.auth_root / "auth.json").read_text(encoding="utf-8"))
            tokens = auth_data.get("tokens")
            id_token = tokens.get("id_token") if isinstance(tokens, dict) else None
            if not isinstance(id_token, str):
                return None
            segments = id_token.split(".")
            if len(segments) != 3:
                return None
            encoded_payload = segments[1] + "=" * (-len(segments[1]) % 4)
            claims = json.loads(base64.urlsafe_b64decode(encoded_payload).decode("utf-8"))
        except (OSError, ValueError, TypeError, binascii.Error):
            return None
        claim_email = claims.get("email") if isinstance(claims, dict) else None
        name = claims.get("name")
        if not isinstance(claim_email, str) or not isinstance(name, str):
            return None
        normalized_email = claim_email.strip().lower()
        normalized_name = " ".join(name.split())
        if not normalized_email or not normalized_name:
            return None
        return normalized_email, normalized_name[:80]

    def _read_display_name(self, *, expected_email: str) -> str | None:
        identity_claim = self._read_identity_claim()
        if not identity_claim or identity_claim[0] != expected_email:
            return None
        return identity_claim[1]

    def logout(self) -> None:
        try:
            self._request("account/logout", {}, timeout_seconds=30.0)
        except CodexAuthError:
            # The product session still needs to be invalidated even when the
            # local app-server is already stopped or its auth is gone.
            pass
        with self._state_lock:
            self._attempts.clear()
            self._login_attempts.clear()

    def start_thread(
        self,
        *,
        cwd: Path,
        developer_instructions: str,
    ) -> str:
        if self.read_account(refresh_token=False) is None:
            raise CodexAuthError("Codex 账号未登录，请重新完成官方授权。")
        result = self._request(
            "thread/start",
            {
                "cwd": str(cwd.resolve()),
                "approvalPolicy": "never",
                "sandbox": "read-only",
                "developerInstructions": developer_instructions,
                "serviceName": "product_factory",
                "personality": "friendly",
            },
            timeout_seconds=30.0,
        )
        thread = result.get("thread")
        thread_id = thread.get("id") if isinstance(thread, dict) else None
        if not isinstance(thread_id, str) or not thread_id:
            raise CodexAuthError("Codex 未返回有效会话 ID。")
        return thread_id

    def resume_thread(
        self,
        thread_id: str,
        *,
        cwd: Path,
        developer_instructions: str,
    ) -> None:
        self._request(
            "thread/resume",
            {
                "threadId": thread_id,
                "cwd": str(cwd.resolve()),
                "approvalPolicy": "never",
                "sandbox": "read-only",
                "developerInstructions": developer_instructions,
                "personality": "friendly",
            },
            timeout_seconds=30.0,
        )

    def run_turn(
        self,
        thread_id: str,
        message: str,
        *,
        output_schema: dict[str, Any] | None = None,
        on_reasoning_summary: Callable[[str], None] | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
    ) -> CodexTurnResult:
        with self._state_lock:
            turn_lock = self._thread_locks.setdefault(thread_id, threading.Lock())
        with turn_lock:
            event_queue: queue.Queue[dict[str, Any]] = queue.Queue()
            with self._state_lock:
                self._thread_streams.setdefault(thread_id, []).append(event_queue)
            try:
                params: dict[str, Any] = {
                    "threadId": thread_id,
                    "input": [{"type": "text", "text": message}],
                    "summary": "detailed",
                }
                if model is not None:
                    params["model"] = model
                if reasoning_effort is not None:
                    params["effort"] = reasoning_effort
                if output_schema is not None:
                    params["outputSchema"] = output_schema
                result = self._request("turn/start", params, timeout_seconds=30.0)
                turn = result.get("turn")
                turn_id = turn.get("id") if isinstance(turn, dict) else None
                if not isinstance(turn_id, str) or not turn_id:
                    raise CodexAuthError("Codex 未返回有效执行 ID。")

                completed_text = ""
                reasoning_summary_text = ""
                deadline = time.monotonic() + self.turn_timeout_seconds
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise CodexAuthError("Codex 回复超时，请稍后重试。")
                    try:
                        event = event_queue.get(timeout=remaining)
                    except queue.Empty as exc:
                        raise CodexAuthError("Codex 回复超时，请稍后重试。") from exc
                    method = event.get("method")
                    event_params = event.get("params")
                    if not isinstance(event_params, dict):
                        continue
                    if method == "bridge/error":
                        raw_error = event_params.get("error")
                        detail = raw_error.get("message") if isinstance(raw_error, dict) else None
                        raise CodexAuthError(
                            detail if isinstance(detail, str) and detail else "本地 Codex 服务已停止。"
                        )
                    event_turn_id = event_params.get("turnId")
                    event_turn = event_params.get("turn")
                    if isinstance(event_turn, dict):
                        event_turn_id = event_turn.get("id")
                    if event_turn_id != turn_id:
                        continue
                    if method == "item/reasoning/summaryTextDelta":
                        delta = event_params.get("delta")
                        if on_reasoning_summary is not None and isinstance(delta, str) and delta:
                            reasoning_summary_text += delta
                            on_reasoning_summary(delta)
                    elif method == "item/reasoning/summaryPartAdded":
                        if on_reasoning_summary is not None and reasoning_summary_text:
                            reasoning_summary_text += "\n"
                            on_reasoning_summary("\n")
                    elif method == "item/completed":
                        item = event_params.get("item")
                        if isinstance(item, dict):
                            if item.get("type") == "agentMessage":
                                text = item.get("text")
                                if isinstance(text, str) and text.strip():
                                    completed_text = text
                            elif item.get("type") == "reasoning" and not reasoning_summary_text:
                                summary = item.get("summary")
                                if isinstance(summary, list):
                                    completed_summary = "\n".join(
                                        part for part in summary if isinstance(part, str) and part
                                    )
                                    if completed_summary and on_reasoning_summary is not None:
                                        reasoning_summary_text = completed_summary
                                        on_reasoning_summary(completed_summary)
                    elif method == "error" and event_params.get("willRetry") is not True:
                        raw_error = event_params.get("error")
                        detail = raw_error.get("message") if isinstance(raw_error, dict) else None
                        raise CodexAuthError(
                            detail if isinstance(detail, str) and detail else "Codex 执行失败，请重试。"
                        )
                    elif method == "turn/completed":
                        status = event_turn.get("status") if isinstance(event_turn, dict) else None
                        if status != "completed":
                            raise CodexAuthError(f"Codex 执行未完成：{status or 'unknown'}")
                        if not completed_text.strip():
                            raise CodexAuthError("Codex 没有返回可用内容。")
                        return CodexTurnResult(
                            thread_id=thread_id,
                            turn_id=turn_id,
                            text=completed_text,
                        )
            finally:
                with self._state_lock:
                    streams = self._thread_streams.get(thread_id, [])
                    if event_queue in streams:
                        streams.remove(event_queue)
                    if not streams:
                        self._thread_streams.pop(thread_id, None)

    def shutdown(self) -> None:
        with self._state_lock:
            self._stopping = True
            process = self._process
            self._process = None
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        self._fail_pending("本地 Codex 服务已停止。")

    def _ensure_started(self) -> None:
        with self._state_lock:
            if self._process is not None and self._process.poll() is None:
                return
            self._stopping = False
            executable = self.command
            if os.path.sep not in executable:
                resolved = shutil.which(executable)
                if not resolved:
                    raise CodexAuthError(
                        "未找到 Codex CLI，请先安装并确认 CODEX_COMMAND 配置正确。"
                    )
                executable = resolved
            elif not Path(executable).is_file():
                raise CodexAuthError("CODEX_COMMAND 指向的文件不存在。")

            self.auth_root.mkdir(parents=True, exist_ok=True)
            try:
                self.auth_root.chmod(0o700)
            except OSError:
                pass
            env = os.environ.copy()
            env["CODEX_HOME"] = str(self.auth_root)
            env["OPENAI_API_KEY"] = ""
            try:
                process = subprocess.Popen(
                    [executable, "app-server", "--stdio"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    bufsize=1,
                    env=env,
                )
            except OSError as exc:
                raise CodexAuthError("无法启动本地 Codex App Server。") from exc
            self._process = process
            self._reader = threading.Thread(
                target=self._read_stdout,
                args=(process,),
                name="codex-auth-stdout",
                daemon=True,
            )
            self._stderr_reader = threading.Thread(
                target=self._drain_stderr,
                args=(process,),
                name="codex-auth-stderr",
                daemon=True,
            )
            self._reader.start()
            self._stderr_reader.start()

        self._request(
            "initialize",
            {
                "clientInfo": {
                    "name": "product_factory",
                    "title": "点线面",
                    "version": "0.1.0",
                }
            },
        )
        self._notify("initialized", {})

    def _request(
        self,
        method: str,
        params: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        if method != "initialize":
            self._ensure_started()
        elif self._process is None:
            raise CodexAuthError("本地 Codex App Server 未启动。")

        with self._state_lock:
            request_id = self._next_id
            self._next_id += 1
            result_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
            self._pending[request_id] = result_queue
        try:
            self._write({"method": method, "id": request_id, "params": params})
            wait_seconds = timeout_seconds or self.request_timeout_seconds
            try:
                message = result_queue.get(timeout=wait_seconds)
            except queue.Empty as exc:
                raise CodexAuthError(f"Codex 请求超时：{method}") from exc
            error = message.get("error")
            if isinstance(error, dict):
                detail = error.get("message")
                raise CodexAuthError(
                    detail if isinstance(detail, str) and detail else f"Codex 请求失败：{method}"
                )
            result = message.get("result")
            if not isinstance(result, dict):
                raise CodexAuthError(f"Codex 返回了无效结果：{method}")
            return result
        finally:
            with self._state_lock:
                self._pending.pop(request_id, None)

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        self._write({"method": method, "params": params})

    def _write(self, message: dict[str, Any]) -> None:
        process = self._process
        if process is None or process.poll() is not None or process.stdin is None:
            raise CodexAuthError("本地 Codex App Server 不可用。")
        encoded = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        try:
            with self._write_lock:
                process.stdin.write(encoded + "\n")
                process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise CodexAuthError("本地 Codex App Server 连接已断开。") from exc

    def _read_stdout(self, process: subprocess.Popen[str]) -> None:
        if process.stdout is None:
            return
        try:
            for line in process.stdout:
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(message, dict):
                    continue
                request_id = message.get("id")
                if isinstance(request_id, int):
                    with self._state_lock:
                        result_queue = self._pending.get(request_id)
                    if result_queue is not None:
                        try:
                            result_queue.put_nowait(message)
                        except queue.Full:
                            pass
                    continue
                self._handle_notification(message)
        finally:
            if not self._stopping:
                self._fail_pending("本地 Codex App Server 意外退出。")

    def _handle_notification(self, message: dict[str, Any]) -> None:
        params = message.get("params")
        if not isinstance(params, dict):
            return
        thread_id = params.get("threadId")
        if isinstance(thread_id, str):
            with self._state_lock:
                streams = list(self._thread_streams.get(thread_id, []))
            for event_queue in streams:
                event_queue.put_nowait(message)

        if message.get("method") != "account/login/completed":
            return
        login_id = params.get("loginId")
        if not isinstance(login_id, str):
            return
        with self._state_lock:
            attempt_id = self._login_attempts.get(login_id)
            state = self._attempts.get(attempt_id) if attempt_id else None
            if state is not None and params.get("success") is not True:
                raw_error = params.get("error")
                state.error = (
                    raw_error
                    if isinstance(raw_error, str) and raw_error
                    else "官方授权未完成，请重试。"
                )

    def _forget_attempt(self, attempt_id: str) -> None:
        with self._state_lock:
            state = self._attempts.pop(attempt_id, None)
            if state is not None:
                self._login_attempts.pop(state.login_id, None)

    def _fail_pending(self, message: str) -> None:
        error_message = {"error": {"code": -32000, "message": message}}
        stream_message = {
            "method": "bridge/error",
            "params": {
                "threadId": "",
                "turnId": "",
                "willRetry": False,
                "error": {"message": message},
            },
        }
        with self._state_lock:
            queues = list(self._pending.values())
            stream_queues = [item for streams in self._thread_streams.values() for item in streams]
        for result_queue in queues:
            try:
                result_queue.put_nowait(error_message)
            except queue.Full:
                pass
        for event_queue in stream_queues:
            event_queue.put_nowait(stream_message)

    @staticmethod
    def _drain_stderr(process: subprocess.Popen[str]) -> None:
        if process.stderr is None:
            return
        # Drain without logging: auth URLs and provider diagnostics may contain
        # sensitive state that should not end up in application logs.
        for _line in process.stderr:
            pass
