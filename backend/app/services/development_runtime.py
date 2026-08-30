from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from uuid import uuid4

from app.core.config import Settings
from app.schemas.contracts import CodingBundle, GeneratedCodeFile

GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SAFE_EXACT_PATHS = {".gitignore", "README.md", "pyproject.toml", "product_factory.json"}
SAFE_DIRECTORY_SUFFIXES = {
    "app": {".py"},
    "tests": {".py"},
    "docs": {".md"},
    "web": {".html"},
}
SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"(?i)api[_-]?key\s*=\s*['\"][^'\"]{12,}['\"]"),
    re.compile(r"(?i)authorization\s*:\s*bearer\s+[A-Za-z0-9._-]{12,}"),
)


class ControlledCodingError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class MaterializedBundle:
    repository: Path
    commit_ref: str
    files: list[GeneratedCodeFile]
    total_bytes: int
    changed_files: list[str]


def safe_path(root: Path, *parts: str) -> Path:
    resolved_root = root.resolve()
    candidate = resolved_root.joinpath(*parts).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ControlledCodingError("WORKSPACE_PATH_DENIED", "文件路径超出项目工作区。") from exc
    return candidate


def project_repository(settings: Settings, project_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", project_id):
        raise ControlledCodingError("INVALID_PROJECT_ID", "项目标识不符合工作区规则。")
    return safe_path(settings.workspace_root, project_id, "repository")


def validate_relative_path(value: str) -> str:
    if "\\" in value or value.startswith("/") or "\x00" in value:
        raise ControlledCodingError("CODE_PATH_DENIED", "生成文件包含不允许的路径。")
    path = PurePosixPath(value)
    if not value or any(part in {"", ".", ".."} for part in path.parts):
        raise ControlledCodingError("CODE_PATH_DENIED", "生成文件包含不允许的路径。")
    if value in SAFE_EXACT_PATHS:
        return value
    if len(path.parts) != 2:
        raise ControlledCodingError("CODE_PATH_DENIED", "生成文件不在当前阶段白名单内。")
    allowed_suffixes = SAFE_DIRECTORY_SUFFIXES.get(path.parts[0])
    if not allowed_suffixes or path.suffix not in allowed_suffixes:
        raise ControlledCodingError("CODE_PATH_DENIED", "生成文件不在当前阶段白名单内。")
    if path.name.startswith("."):
        raise ControlledCodingError("CODE_PATH_DENIED", "隐藏文件不在当前阶段白名单内。")
    return value


def validate_bundle(bundle: CodingBundle, settings: Settings) -> list[GeneratedCodeFile]:
    if len(bundle.files) > settings.coding_max_files:
        raise ControlledCodingError("CODE_FILE_LIMIT", "生成文件数量超过当前阶段预算。")
    required = {"README.md", "pyproject.toml", "product_factory.json", "app/main.py"}
    if bundle.template == "controlled_html_webapp_v1":
        required.add("web/index.html")
    validated: list[GeneratedCodeFile] = []
    total_bytes = 0
    seen: set[str] = set()
    for item in bundle.files:
        path = validate_relative_path(item.path)
        if path in seen:
            raise ControlledCodingError("DUPLICATE_CODE_PATH", "生成文件路径重复。")
        seen.add(path)
        size = len(item.content.encode("utf-8"))
        if size > settings.coding_max_file_bytes:
            raise ControlledCodingError("CODE_FILE_TOO_LARGE", "单个生成文件超过当前阶段预算。")
        total_bytes += size
        if any(pattern.search(item.content) for pattern in SECRET_PATTERNS):
            raise ControlledCodingError("SECRET_IN_GENERATED_CODE", "生成代码疑似包含密钥，已停止写入。")
        try:
            if path.endswith(".py"):
                ast.parse(item.content, filename=path)
            elif path == "product_factory.json":
                json.loads(item.content)
        except (SyntaxError, ValueError) as exc:
            raise ControlledCodingError(
                "CODE_CONTRACT_INVALID", "生成文件没有通过语法或结构校验。"
            ) from exc
        validated.append(item)
    if not required.issubset(seen):
        raise ControlledCodingError("CODE_BUNDLE_INCOMPLETE", "生成代码包缺少必需文件。")
    if total_bytes > settings.coding_max_total_bytes:
        raise ControlledCodingError("CODE_BUNDLE_TOO_LARGE", "生成代码包超过当前阶段总预算。")
    return validated


def _git_environment() -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", ""),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_AUTHOR_NAME": "AI Product Factory",
        "GIT_AUTHOR_EMAIL": "product-factory@localhost",
        "GIT_COMMITTER_NAME": "AI Product Factory",
        "GIT_COMMITTER_EMAIL": "product-factory@localhost",
    }


def git_command(
    repository: Path,
    *args: str,
    check: bool = True,
    timeout: int = 10,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", *args],
            cwd=repository,
            env=_git_environment(),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise ControlledCodingError("GIT_UNAVAILABLE", "当前环境没有可用的 Git。") from exc
    except subprocess.TimeoutExpired as exc:
        raise ControlledCodingError("GIT_TIMEOUT", "Git 操作超时。") from exc
    if check and result.returncode != 0:
        raise ControlledCodingError("GIT_OPERATION_FAILED", "Git 版本操作失败。")
    return result


def _tracked_files(repository: Path) -> set[str]:
    result = git_command(repository, "ls-files", "-z", check=False)
    if result.returncode != 0:
        return set()
    return {item for item in result.stdout.split("\x00") if item}


def _atomic_write(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(target)


def materialize_bundle(
    *,
    settings: Settings,
    project_id: str,
    bundle: CodingBundle,
    commit_message: str,
) -> MaterializedBundle:
    files = validate_bundle(bundle, settings)
    repository = project_repository(settings, project_id)
    repository.mkdir(parents=True, exist_ok=True)
    if not (repository / ".git").is_dir():
        git_command(repository, "init", "--quiet")

    requested_paths = {item.path for item in files}
    tracked_before = _tracked_files(repository)
    for stale in sorted(tracked_before - requested_paths):
        try:
            validate_relative_path(stale)
        except ControlledCodingError:
            continue
        stale_path = safe_path(repository, *PurePosixPath(stale).parts)
        if stale_path.is_file() and not stale_path.is_symlink():
            stale_path.unlink()

    total_bytes = 0
    for item in files:
        target = safe_path(repository, *PurePosixPath(item.path).parts)
        if target.exists() and target.is_symlink():
            raise ControlledCodingError("WORKSPACE_SYMLINK_DENIED", "工作区内发现不允许的软链接。")
        _atomic_write(target, item.content)
        total_bytes += len(item.content.encode("utf-8"))

    git_command(repository, "add", "-A", "--", *sorted(requested_paths | tracked_before))
    head_before = git_command(repository, "rev-parse", "--verify", "HEAD", check=False)
    staged = git_command(repository, "diff", "--cached", "--quiet", check=False)
    if staged.returncode not in {0, 1}:
        raise ControlledCodingError("GIT_OPERATION_FAILED", "无法检查 Git 待提交内容。")
    if head_before.returncode != 0 or staged.returncode == 1:
        git_command(
            repository,
            "-c",
            "user.name=AI Product Factory",
            "-c",
            "user.email=product-factory@localhost",
            "commit",
            "--quiet",
            "--no-gpg-sign",
            "-m",
            commit_message[:120],
        )
    commit_ref = git_command(repository, "rev-parse", "HEAD").stdout.strip().lower()
    if not GIT_SHA_PATTERN.fullmatch(commit_ref):
        raise ControlledCodingError("GIT_INVALID_REVISION", "Git 没有返回有效版本号。")
    changed = git_command(
        repository,
        "show",
        "--format=",
        "--name-only",
        commit_ref,
    ).stdout.splitlines()
    return MaterializedBundle(
        repository=repository,
        commit_ref=commit_ref,
        files=files,
        total_bytes=total_bytes,
        changed_files=[item for item in changed if item],
    )


def file_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def read_file_at_commit(
    *, settings: Settings, project_id: str, commit_ref: str, path: str
) -> str:
    if not GIT_SHA_PATTERN.fullmatch(commit_ref):
        raise ControlledCodingError("GIT_INVALID_REVISION", "代码版本号无效。")
    safe_file = validate_relative_path(path)
    repository = project_repository(settings, project_id)
    if not (repository / ".git").is_dir():
        raise ControlledCodingError("WORKSPACE_NOT_READY", "项目代码工作区尚未准备好。")
    result = git_command(repository, "show", f"{commit_ref}:{safe_file}", check=False)
    if result.returncode != 0:
        raise ControlledCodingError("CODE_FILE_NOT_FOUND", "该版本中没有这个文件。")
    if len(result.stdout.encode("utf-8")) > settings.coding_max_file_bytes:
        raise ControlledCodingError("CODE_FILE_TOO_LARGE", "文件超过可查看大小。")
    return result.stdout


def restore_commit(*, settings: Settings, project_id: str, commit_ref: str) -> None:
    """Restore only the assigned generated repository to a previously tested commit."""

    if not GIT_SHA_PATTERN.fullmatch(commit_ref):
        raise ControlledCodingError("GIT_INVALID_REVISION", "回退版本号无效。")
    repository = project_repository(settings, project_id)
    if not (repository / ".git").is_dir():
        raise ControlledCodingError("WORKSPACE_NOT_READY", "项目代码工作区尚未准备好。")
    exists = git_command(repository, "cat-file", "-e", f"{commit_ref}^{{commit}}", check=False)
    if exists.returncode != 0:
        raise ControlledCodingError("GIT_VERSION_NOT_FOUND", "最后可用代码版本不存在。")
    git_command(repository, "reset", "--hard", commit_ref)
