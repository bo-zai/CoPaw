# -*- coding: utf-8 -*-
"""Safe JSON session with filename sanitization for cross-platform
compatibility.

Windows filenames cannot contain: \\ / : * ? " < > |
This module wraps agentscope's SessionBase so that session_id and user_id
are sanitized before being used as filenames.
"""

import asyncio
import errno
import json
import logging
import os
import re
import threading
import tempfile

from contextlib import asynccontextmanager
from contextvars import ContextVar, Token
from types import MappingProxyType
from typing import Any, AsyncIterator, Callable, Mapping, Sequence, Union

from agentscope.session import SessionBase

from swe.app.runner.session_lock import (
    AsyncSessionFileLock,
    SessionLockTimeout,
    get_session_lock_path,
)
from swe.runtime_workers import run_runtime_state_work

logger = logging.getLogger(__name__)
SESSION_SKILL_SNAPSHOT_STATE_KEY = "session_skill_snapshot"
_SESSION_WRITE_LOCKS: dict[
    tuple[asyncio.AbstractEventLoop, str],
    asyncio.Lock,
] = {}
_SESSION_WRITE_LOCKS_GUARD = threading.Lock()
_EMPTY_ACTIVE_SESSION_EXECUTIONS: Mapping[str, "SessionExecution"] = (
    MappingProxyType({})
)
_ACTIVE_SESSION_EXECUTIONS: ContextVar[Mapping[str, "SessionExecution"]] = (
    ContextVar(
        "active_session_executions",
        default=_EMPTY_ACTIVE_SESSION_EXECUTIONS,
    )
)


# Characters forbidden in Windows filenames
_UNSAFE_FILENAME_RE = re.compile(r'[\\/:*?"<>|]')
_ALLOWED_MESSAGE_ROLES = {"user", "assistant", "system"}


def sanitize_filename(name: str) -> str:
    """Replace characters that are illegal in Windows filenames with ``--``.

    >>> sanitize_filename('discord:dm:12345')
    'discord--dm--12345'
    >>> sanitize_filename('normal-name')
    'normal-name'
    """
    return _UNSAFE_FILENAME_RE.sub("--", name)


def _normalize_state_for_load(value):
    """在反序列化前把旧角色单向迁移到 AgentScope 可接受角色。"""
    if isinstance(value, list):
        return [_normalize_state_for_load(item) for item in value]

    if not isinstance(value, dict):
        return value

    normalized = {
        key: _normalize_state_for_load(item) for key, item in value.items()
    }
    role = normalized.get("role")
    if (
        isinstance(role, str)
        and role not in _ALLOWED_MESSAGE_ROLES
        and "name" in normalized
        and "content" in normalized
    ):
        normalized["role"] = "system"
    return normalized


def _get_session_write_lock(file_path: str) -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    normalized_path = os.path.normcase(os.path.abspath(file_path))
    lock_key = (loop, normalized_path)
    with _SESSION_WRITE_LOCKS_GUARD:
        lock = _SESSION_WRITE_LOCKS.get(lock_key)
        if lock is None:
            lock = asyncio.Lock()
            _SESSION_WRITE_LOCKS[lock_key] = lock
        return lock


def _get_normalized_session_path(file_path: str) -> str:
    return os.path.normcase(os.path.abspath(file_path))


def _reject_short_lock_during_execution(session_save_path: str) -> None:
    normalized_path = _get_normalized_session_path(session_save_path)
    execution = _ACTIVE_SESSION_EXECUTIONS.get().get(normalized_path)
    if execution is not None and execution.is_active:
        raise RuntimeError(
            "cannot use a short-lock API during an active session execution; "
            "use its transaction instead",
        )


@asynccontextmanager
async def _session_write_scope(
    session_save_path: str,
    *,
    timeout_seconds: float | None = None,
) -> AsyncIterator[None]:
    _reject_short_lock_during_execution(session_save_path)
    lock = _get_session_write_lock(session_save_path)
    if timeout_seconds is None:
        await lock.acquire()
    else:
        await asyncio.wait_for(lock.acquire(), timeout=timeout_seconds)
    try:
        try:
            async with AsyncSessionFileLock(
                get_session_lock_path(session_save_path),
                timeout_seconds=timeout_seconds,
            ):
                yield
        except SessionLockTimeout as exc:
            raise TimeoutError(str(exc)) from exc
    finally:
        lock.release()


def _write_json_text(file_path: str, content: str) -> None:
    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=os.path.dirname(file_path) or ".",
            prefix=f".{os.path.basename(file_path)}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            temp_path = file.name
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, file_path)
        _sync_parent_directory(file_path)
    except Exception:
        if temp_path is not None:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
        raise


def _sync_parent_directory(file_path: str) -> None:
    """Persist a replacement directory entry when the platform supports it."""
    directory_path = os.path.dirname(file_path) or "."
    directory_flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        directory_flags |= os.O_DIRECTORY

    directory_fd = os.open(directory_path, directory_flags)

    try:
        try:
            os.fsync(directory_fd)
        except OSError as exc:
            unsupported_errors = {
                errno.EINVAL,
                getattr(errno, "ENOSYS", errno.EINVAL),
                getattr(errno, "ENOTSUP", errno.EINVAL),
                getattr(errno, "EOPNOTSUPP", errno.EINVAL),
            }
            if exc.errno not in unsupported_errors:
                raise
    finally:
        os.close(directory_fd)


def _read_json_state_sync(
    session_save_path: str,
    *,
    allow_not_exist: bool,
    allow_empty: bool = False,
) -> tuple[bool, dict[str, Any]]:
    if not os.path.exists(session_save_path):
        if allow_not_exist:
            return False, {}
        raise ValueError(
            "Failed to load session state for file "
            f"{session_save_path} because it does not exist.",
        )

    with open(
        session_save_path,
        "r",
        encoding="utf-8",
        errors="surrogatepass",
    ) as file:
        content = file.read()

    if allow_empty and not content.strip():
        return True, {}

    states = json.loads(content)
    if not isinstance(states, dict):
        raise ValueError(
            f"Session file {session_save_path} does not contain "
            "a JSON object.",
        )
    return True, states


def _read_existing_state_for_save_sync(
    session_save_path: str,
) -> dict[str, Any]:
    """保存前读取已有状态，旧文件异常时沿用覆盖写入策略。"""
    if not os.path.exists(session_save_path):
        return {}

    with open(
        session_save_path,
        "r",
        encoding="utf-8",
        errors="surrogatepass",
    ) as file:
        content = file.read()

    if not content.strip():
        return {}

    try:
        loaded_state = json.loads(content)
    except json.JSONDecodeError:
        logger.warning(
            "Failed to parse existing session state at %s; "
            "overwriting with current state.",
            session_save_path,
        )
        return {}

    if isinstance(loaded_state, dict):
        return loaded_state
    return {}


def _write_json_state_sync(
    session_save_path: str,
    state: dict[str, Any],
) -> None:
    _write_json_text(
        session_save_path,
        json.dumps(state, ensure_ascii=False),
    )


class SessionExecution:
    """A session state snapshot protected by one file lock for its lifetime."""

    def __init__(
        self,
        session_save_path: str,
        *,
        timeout_seconds: float | None = None,
    ) -> None:
        self._session_save_path = session_save_path
        self._timeout_seconds = timeout_seconds
        self._scope = None
        self._state: dict[str, Any] = {}
        self._revision = 0
        self._schema_version = 1
        self._state_dirty = False
        self._entered = False
        self._active_executions_token: (
            Token[Mapping[str, "SessionExecution"]] | None
        ) = None

    @property
    def revision(self) -> int:
        """Return the revision of the latest state in this transaction."""
        return self._revision

    @property
    def schema_version(self) -> int:
        """Return the schema version of the loaded state."""
        return self._schema_version

    @property
    def state(self) -> dict[str, Any]:
        """Return the transaction-owned mutable state snapshot."""
        self._require_entered()
        return self._state

    async def __aenter__(self) -> "SessionExecution":
        if self._entered or self._scope is not None:
            raise RuntimeError("session execution is already active")
        self._scope = _session_write_scope(
            self._session_save_path,
            timeout_seconds=self._timeout_seconds,
        )
        try:
            await self._scope.__aenter__()
            _, self._state = await run_runtime_state_work(
                _read_json_state_sync,
                self._session_save_path,
                allow_not_exist=True,
                allow_empty=True,
            )
            self._schema_version = self._get_schema_version(self._state)
            self._revision = self._get_revision(self._state)
            active_executions = dict(_ACTIVE_SESSION_EXECUTIONS.get())
            active_executions[
                _get_normalized_session_path(self._session_save_path)
            ] = self
            self._active_executions_token = _ACTIVE_SESSION_EXECUTIONS.set(
                active_executions,
            )
            self._entered = True
            return self
        except BaseException:
            self._reset_active_executions()
            if self._scope is not None:
                await self._scope.__aexit__(None, None, None)
                self._scope = None
            raise

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        try:
            if self._scope is not None:
                await self._scope.__aexit__(exc_type, exc, traceback)
        finally:
            self._entered = False
            self._scope = None
            self._reset_active_executions()

    async def close(self) -> None:
        """Release this transaction before unrelated query cleanup begins."""
        if self._scope is not None:
            await self.__aexit__(None, None, None)

    @property
    def is_active(self) -> bool:
        """Return whether this transaction still owns its session lock."""
        return self._entered

    def _reset_active_executions(self) -> None:
        if self._active_executions_token is not None:
            _ACTIVE_SESSION_EXECUTIONS.reset(self._active_executions_token)
            self._active_executions_token = None

    async def read_state(self) -> dict[str, Any]:
        """Return the single state snapshot read while acquiring the lock."""
        return self.state

    @property
    def has_uncommitted_state(self) -> bool:
        """Return whether a transaction-side mutation still needs a commit."""
        return self._state_dirty

    def mark_state_dirty(self) -> None:
        """Mark a direct transaction-state mutation for final persistence."""
        self._require_entered()
        self._state_dirty = True

    async def commit_state(self, state: dict[str, Any]) -> dict[str, Any]:
        """Replace transaction state without reacquiring its held lock."""
        self._require_entered()
        if not isinstance(state, dict):
            raise ValueError("state must be a dict")

        next_revision = self._revision + 1
        committed_state = {
            **state,
            "schema_version": 2,
            "revision": next_revision,
        }
        write_task = asyncio.create_task(
            run_runtime_state_work(
                _write_json_state_sync,
                self._session_save_path,
                committed_state,
            ),
        )
        try:
            await asyncio.shield(write_task)
        except asyncio.CancelledError:
            while not write_task.done():
                try:
                    await asyncio.shield(write_task)
                except asyncio.CancelledError:
                    continue
            write_task.result()
            self._set_committed_state(committed_state, next_revision)
            raise
        self._set_committed_state(committed_state, next_revision)
        return self._state

    def _set_committed_state(
        self,
        committed_state: dict[str, Any],
        revision: int,
    ) -> None:
        self._state = committed_state
        self._schema_version = 2
        self._revision = revision
        self._state_dirty = False

    def _require_entered(self) -> None:
        if not self._entered:
            raise RuntimeError("session execution is not active")

    @staticmethod
    def _get_schema_version(state: dict[str, Any]) -> int:
        schema_version = state.get("schema_version", 1)
        return schema_version if isinstance(schema_version, int) else 1

    @staticmethod
    def _get_revision(state: dict[str, Any]) -> int:
        revision = state.get("revision", 0)
        return revision if isinstance(revision, int) and revision >= 0 else 0


class SafeJSONSession(SessionBase):
    """SessionBase subclass with filename sanitization and async file I/O.

    Uses :mod:`aiofiles` for reads and worker threads for writes so that
    disk I/O does not block the event loop.
    """

    def __init__(
        self,
        save_dir: str = "./",
    ) -> None:
        """Initialize the JSON session class.

        Args:
            save_dir (`str`, defaults to `"./"):
                The directory to save the session state.
        """
        self.save_dir = save_dir

    def _get_save_path(self, session_id: str, user_id: str) -> str:
        """Return a filesystem-safe save path.

        Overrides the parent implementation to ensure the generated
        filename is valid on Windows, macOS and Linux.
        """
        os.makedirs(self.save_dir, exist_ok=True)
        safe_sid = sanitize_filename(session_id)
        safe_uid = sanitize_filename(user_id) if user_id else ""
        if safe_uid:
            file_path = f"{safe_uid}_{safe_sid}.json"
        else:
            file_path = f"{safe_sid}.json"
        return os.path.join(self.save_dir, file_path)

    @asynccontextmanager
    async def session_write_lock(
        self,
        session_id: str,
        user_id: str = "",
        timeout_seconds: float | None = None,
    ) -> AsyncIterator[None]:
        """按会话文件串行化读改写，避免清理和运行结束互相覆盖。"""
        session_save_path = self._get_save_path(session_id, user_id=user_id)
        async with _session_write_scope(
            session_save_path,
            timeout_seconds=timeout_seconds,
        ):
            yield

    @asynccontextmanager
    async def execution(
        self,
        session_id: str,
        user_id: str = "",
        timeout_seconds: float | None = None,
    ) -> AsyncIterator[SessionExecution]:
        """Hold one session lock while reading and committing a snapshot."""
        session_save_path = self._get_save_path(session_id, user_id=user_id)
        transaction = SessionExecution(
            session_save_path,
            timeout_seconds=timeout_seconds,
        )
        async with transaction:
            yield transaction

    async def _read_session_state_file(
        self,
        session_save_path: str,
        *,
        allow_not_exist: bool,
    ) -> tuple[bool, dict[str, Any]]:
        _reject_short_lock_during_execution(session_save_path)
        async with _get_session_write_lock(session_save_path):
            return await run_runtime_state_work(
                _read_json_state_sync,
                session_save_path,
                allow_not_exist=allow_not_exist,
            )

    async def _read_existing_state_for_save(
        self,
        session_save_path: str,
    ) -> dict[str, Any]:
        """保存前读取已有状态，旧文件异常时沿用覆盖写入策略。"""
        return await run_runtime_state_work(
            _read_existing_state_for_save_sync,
            session_save_path,
        )

    async def save_session_state(
        self,
        session_id: str,
        user_id: str = "",
        **state_modules_mapping,
    ) -> None:
        """Save state modules to a JSON file using async I/O."""
        session_save_path = self._get_save_path(session_id, user_id=user_id)
        async with _session_write_scope(session_save_path):
            existing_state = await self._read_existing_state_for_save(
                session_save_path,
            )
            state_dicts = {
                name: state_module.state_dict()
                for name, state_module in state_modules_mapping.items()
            }
            state_dicts = {**existing_state, **state_dicts}
            await run_runtime_state_work(
                _write_json_state_sync,
                session_save_path,
                state_dicts,
            )

        logger.info(
            "Saved session state to %s successfully.",
            session_save_path,
        )

    async def load_session_state(
        self,
        session_id: str,
        user_id: str = "",
        allow_not_exist: bool = True,
        **state_modules_mapping,
    ) -> None:
        """Load state modules from a JSON file using async I/O."""
        session_save_path = self._get_save_path(session_id, user_id=user_id)
        exists, states = await self._read_session_state_file(
            session_save_path,
            allow_not_exist=allow_not_exist,
        )
        if exists:
            for name, state_module in state_modules_mapping.items():
                if name in states:
                    normalized_state = _normalize_state_for_load(
                        states[name],
                    )
                    state_module.load_state_dict(normalized_state)
            logger.info(
                "Load session state from %s successfully.",
                session_save_path,
            )
        else:
            logger.info(
                "Session file %s does not exist. Skip loading session state.",
                session_save_path,
            )

    async def update_session_state(
        self,
        session_id: str,
        key: Union[str, Sequence[str]],
        value,
        user_id: str = "",
        create_if_not_exist: bool = True,
    ) -> None:
        path = key.split(".") if isinstance(key, str) else list(key)
        if not path:
            raise ValueError("key path is empty")

        def _mutate(states: dict[str, Any]) -> dict[str, Any]:
            cur = states
            for k in path[:-1]:
                if k not in cur or not isinstance(cur[k], dict):
                    cur[k] = {}
                cur = cur[k]

            cur[path[-1]] = value
            return states

        await self.mutate_session_state(
            session_id=session_id,
            mutator=_mutate,
            user_id=user_id,
            create_if_not_exist=create_if_not_exist,
        )

        logger.info(
            "Updated session state key '%s' in %s successfully.",
            key,
            self._get_save_path(session_id, user_id=user_id),
        )

    async def get_session_state_dict(
        self,
        session_id: str,
        user_id: str = "",
        allow_not_exist: bool = True,
    ) -> dict:
        """Return the session state dict from the JSON file.

        Args:
            session_id (`str`):
                The session id.
            user_id (`str`, default to `""`):
                The user ID for the storage.
            allow_not_exist (`bool`, defaults to `True`):
                Whether to allow the session to not exist. If `False`, raises
                an error if the session does not exist.

        Returns:
            `dict`:
                The session state dict loaded from the JSON file. Returns an
                empty dict if the file does not exist and
                `allow_not_exist=True`.
        """
        session_save_path = self._get_save_path(session_id, user_id=user_id)
        exists, states = await self._read_session_state_file(
            session_save_path,
            allow_not_exist=allow_not_exist,
        )
        if exists:
            logger.info(
                "Get session state dict from %s successfully.",
                session_save_path,
            )
            return states
        logger.info(
            "Session file %s does not exist. Return empty state dict.",
            session_save_path,
        )
        return {}

    async def get_persisted_session_state_dict(
        self,
        session_id: str,
        user_id: str = "",
        allow_not_exist: bool = True,
    ) -> dict:
        """Read the latest atomically committed session snapshot without waiting.

        Session writers replace the JSON file atomically.  A history observer can
        therefore safely consume the last committed file while an execution owns
        the transaction lock, rather than waiting for model generation to end.
        """
        session_save_path = self._get_save_path(session_id, user_id=user_id)
        exists, states = await run_runtime_state_work(
            _read_json_state_sync,
            session_save_path,
            allow_not_exist=allow_not_exist,
        )
        return states if exists else {}

    async def get_session_skill_snapshot(
        self,
        session_id: str,
        user_id: str = "",
        allow_not_exist: bool = True,
    ) -> dict[str, dict]:
        """Return the persisted session skill snapshot."""
        state = await self.get_session_state_dict(
            session_id=session_id,
            user_id=user_id,
            allow_not_exist=allow_not_exist,
        )
        raw_snapshot = (
            state.get(SESSION_SKILL_SNAPSHOT_STATE_KEY)
            if isinstance(state, dict)
            else None
        )
        if not isinstance(raw_snapshot, dict):
            return {}

        snapshot: dict[str, dict] = {}
        for skill_name, entry in raw_snapshot.items():
            if isinstance(skill_name, str) and isinstance(entry, dict):
                snapshot[skill_name] = dict(entry)
        return snapshot

    async def save_session_skill_snapshot(
        self,
        session_id: str,
        snapshot: dict[str, dict],
        user_id: str = "",
    ) -> None:
        """Persist the top-level session skill snapshot."""
        await self.update_session_state(
            session_id=session_id,
            key=SESSION_SKILL_SNAPSHOT_STATE_KEY,
            value=snapshot,
            user_id=user_id,
        )

    async def save_merged_state(
        self,
        session_id: str,
        user_id: str = "",
        state: dict = None,
    ) -> None:
        """Save merged state dict to JSON file.

        Used by cron tasks to preserve existing session history while
        saving new state without overwriting.

        Args:
            session_id: The session id
            user_id: The user ID for the storage
            state: The merged state dict to save
        """
        if state is None:
            state = {}
        session_save_path = self._get_save_path(session_id, user_id=user_id)
        async with _session_write_scope(session_save_path):
            await run_runtime_state_work(
                _write_json_state_sync,
                session_save_path,
                state,
            )
        logger.info(
            "Saved merged session state to %s (keys=%d)",
            session_save_path,
            len(state),
        )

    async def mutate_session_state(
        self,
        session_id: str,
        mutator: Callable[[dict[str, Any]], dict[str, Any] | None],
        user_id: str = "",
        create_if_not_exist: bool = True,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        """Atomically read, merge and write session state under one lock."""
        session_save_path = self._get_save_path(session_id, user_id=user_id)
        async with _session_write_scope(
            session_save_path,
            timeout_seconds=timeout_seconds,
        ):
            exists, states = await run_runtime_state_work(
                _read_json_state_sync,
                session_save_path,
                allow_not_exist=True,
                allow_empty=True,
            )
            if not exists and not create_if_not_exist:
                raise ValueError(
                    f"Session file {session_save_path} does not exist.",
                )

            updated_state = mutator(states)
            if updated_state is None:
                updated_state = states
            if not isinstance(updated_state, dict):
                raise ValueError("mutator must return a dict or None")

            await run_runtime_state_work(
                _write_json_state_sync,
                session_save_path,
                updated_state,
            )

        logger.info(
            "Mutated session state in %s successfully.",
            session_save_path,
        )
        return updated_state
