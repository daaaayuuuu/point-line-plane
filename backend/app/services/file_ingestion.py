from __future__ import annotations

import gzip
import io
import stat
import tarfile
import zipfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

from fastapi import UploadFile
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.config import Settings
from app.core.errors import ApiError

TEXT_EXTENSIONS = {
    ".bash",
    ".c",
    ".cfg",
    ".conf",
    ".cpp",
    ".cs",
    ".css",
    ".csv",
    ".go",
    ".h",
    ".hpp",
    ".htm",
    ".html",
    ".ini",
    ".ipynb",
    ".java",
    ".js",
    ".json",
    ".jsonl",
    ".jsx",
    ".less",
    ".log",
    ".markdown",
    ".md",
    ".mjs",
    ".php",
    ".properties",
    ".py",
    ".rb",
    ".rs",
    ".rtf",
    ".scss",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsv",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
    ".zsh",
}
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx"}
ARCHIVE_EXTENSIONS = {".zip", ".tar", ".tar.gz", ".tgz", ".gz"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | DOCUMENT_EXTENSIONS | ARCHIVE_EXTENSIONS

TEXT_MEDIA_TYPES = {
    "application/javascript",
    "application/json",
    "application/sql",
    "application/toml",
    "application/x-httpd-php",
    "application/x-javascript",
    "application/x-sh",
    "application/xml",
    "application/yaml",
    "application/octet-stream",
}
OFFICE_MEDIA_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/octet-stream",
    "application/zip",
}
ARCHIVE_MEDIA_TYPES = {
    "application/gzip",
    "application/octet-stream",
    "application/x-gzip",
    "application/x-tar",
    "application/x-gtar",
    "application/zip",
}
MAX_ARCHIVE_FILES = 200


def extract_upload_text(file: UploadFile, content: bytes, settings: Settings) -> str:
    filename = _safe_filename(file.filename or "")
    if len(content) > settings.max_upload_bytes:
        raise ApiError("FILE_TOO_LARGE", "文件超过上传大小限制。", 413)

    extension = _extension(filename)
    if extension not in SUPPORTED_EXTENSIONS:
        raise ApiError(
            "UNSUPPORTED_FILE_TYPE",
            "暂不支持这种文件。请上传文本、代码、PDF、Office 文档或常见压缩包。",
            415,
        )
    _validate_media_type(extension, file.content_type or "")

    if extension in TEXT_EXTENSIONS:
        text = _decode_text(content)
    elif extension == ".pdf":
        text = _extract_pdf(content)
    elif extension in {".docx", ".pptx", ".xlsx"}:
        text = _extract_office(extension, content, settings.max_upload_bytes)
    else:
        text = _extract_archive(filename, extension, content, settings.max_upload_bytes)
    return _finalize_text(text)


def _safe_filename(filename: str) -> str:
    if (
        not filename
        or filename != Path(filename).name
        or "/" in filename
        or "\\" in filename
        or "\x00" in filename
    ):
        raise ApiError("UNSAFE_FILENAME", "文件名不安全，请重命名后上传。", 400)
    return filename


def _extension(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".tar.gz"):
        return ".tar.gz"
    return Path(lower).suffix


def _validate_media_type(extension: str, raw_media_type: str) -> None:
    media_type = raw_media_type.split(";", 1)[0].strip().lower()
    if not media_type:
        return
    if extension in TEXT_EXTENSIONS:
        accepted = media_type.startswith("text/") or media_type in TEXT_MEDIA_TYPES
    elif extension == ".pdf":
        accepted = media_type in {"application/pdf", "application/octet-stream"}
    elif extension in {".docx", ".pptx", ".xlsx"}:
        accepted = media_type in OFFICE_MEDIA_TYPES
    else:
        accepted = media_type in ARCHIVE_MEDIA_TYPES
    if not accepted:
        raise ApiError("UNSUPPORTED_CONTENT_TYPE", "文件类型与文件内容不匹配。", 415)


def _decode_text(content: bytes) -> str:
    binary_signatures = (
        b"%PDF-",
        b"PK\x03\x04",
        b"PK\x05\x06",
        b"\x89PNG\r\n\x1a\n",
        b"\xff\xd8\xff",
        b"GIF87a",
        b"GIF89a",
        b"\x7fELF",
    )
    if b"\x00" in content or any(content.startswith(signature) for signature in binary_signatures):
        raise ApiError("INVALID_TEXT_FILE", "文件不是有效的文本内容。", 415)
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ApiError("INVALID_TEXT_FILE", "文本和代码文件必须使用 UTF-8 编码。", 415) from exc


def _extract_pdf(content: bytes) -> str:
    if not content.startswith(b"%PDF-"):
        raise ApiError("INVALID_DOCUMENT", "PDF 文件内容无效。", 415)
    try:
        reader = PdfReader(io.BytesIO(content), strict=False)
        return "\n\n".join((page.extract_text() or "").strip() for page in reader.pages)
    except (PdfReadError, ValueError, TypeError) as exc:
        raise ApiError("INVALID_DOCUMENT", "PDF 文件损坏或无法读取。", 415) from exc


def _extract_office(extension: str, content: bytes, max_bytes: int) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            _validate_zip_members(archive.infolist(), max_bytes)
            if extension == ".docx":
                return _xml_member_text(archive, ["word/document.xml"])
            if extension == ".pptx":
                names = sorted(
                    name
                    for name in archive.namelist()
                    if name.startswith("ppt/slides/slide") and name.endswith(".xml")
                )
                return _xml_member_text(archive, names)
            return _extract_xlsx(archive)
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise ApiError("INVALID_DOCUMENT", "Office 文档损坏或无法读取。", 415) from exc


def _xml_member_text(archive: zipfile.ZipFile, names: list[str]) -> str:
    sections: list[str] = []
    for name in names:
        root = ElementTree.fromstring(archive.read(name))
        values = [node.text.strip() for node in root.iter() if node.text and _local_tag(node.tag) == "t"]
        if values:
            sections.append("\n".join(values))
    return "\n\n".join(sections)


def _extract_xlsx(archive: zipfile.ZipFile) -> str:
    shared: list[str] = []
    if "xl/sharedStrings.xml" in archive.namelist():
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
        for item in root.iter():
            if _local_tag(item.tag) == "si":
                shared.append("".join(node.text or "" for node in item.iter() if _local_tag(node.tag) == "t"))

    sheets: list[str] = []
    for name in sorted(
        item
        for item in archive.namelist()
        if item.startswith("xl/worksheets/sheet") and item.endswith(".xml")
    ):
        root = ElementTree.fromstring(archive.read(name))
        rows: list[str] = []
        for row in (node for node in root.iter() if _local_tag(node.tag) == "row"):
            values: list[str] = []
            for cell in (node for node in row if _local_tag(node.tag) == "c"):
                raw = next((node.text or "" for node in cell.iter() if _local_tag(node.tag) == "v"), "")
                if cell.attrib.get("t") == "s" and raw.isdigit() and int(raw) < len(shared):
                    raw = shared[int(raw)]
                if cell.attrib.get("t") == "inlineStr":
                    raw = "".join(
                        node.text or "" for node in cell.iter() if _local_tag(node.tag) == "t"
                    )
                values.append(raw)
            if any(value for value in values):
                rows.append("\t".join(values))
        if rows:
            sheets.append(f"[{name}]\n" + "\n".join(rows))
    return "\n\n".join(sheets)


def _extract_archive(filename: str, extension: str, content: bytes, max_bytes: int) -> str:
    if extension == ".zip":
        return _extract_zip_archive(content, max_bytes)
    if extension in {".tar", ".tar.gz", ".tgz"}:
        return _extract_tar_archive(content, max_bytes)
    return _extract_gzip_file(filename, content, max_bytes)


def _extract_zip_archive(content: bytes, max_bytes: int) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist()
            _validate_zip_members(infos, max_bytes)
            sections: list[str] = []
            extracted_bytes = 0
            for info in infos:
                if info.is_dir() or _extension(info.filename) not in TEXT_EXTENSIONS | DOCUMENT_EXTENSIONS:
                    continue
                extracted_bytes += info.file_size
                if extracted_bytes > max_bytes:
                    raise ApiError("ARCHIVE_TOO_LARGE", "压缩包解压后的可读文件超过大小限制。", 413)
                data = archive.read(info)
                text = _extract_member(info.filename, data, max_bytes)
                if text.strip():
                    sections.append(f"--- {info.filename} ---\n{text}")
            return "\n\n".join(sections)
    except zipfile.BadZipFile as exc:
        raise ApiError("INVALID_ARCHIVE", "ZIP 压缩包损坏或无法读取。", 415) from exc


def _validate_zip_members(infos: list[zipfile.ZipInfo], max_bytes: int) -> None:
    if len(infos) > MAX_ARCHIVE_FILES:
        raise ApiError("ARCHIVE_TOO_MANY_FILES", "压缩包文件数量超过限制。", 413)
    for info in infos:
        _safe_archive_path(info.filename)
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise ApiError("UNSAFE_ARCHIVE", "压缩包不能包含符号链接。", 415)
        if info.file_size > max_bytes:
            raise ApiError("ARCHIVE_TOO_LARGE", "压缩包内单个文件超过大小限制。", 413)


def _extract_tar_archive(content: bytes, max_bytes: int) -> str:
    try:
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:*") as archive:
            members = archive.getmembers()
            if len(members) > MAX_ARCHIVE_FILES:
                raise ApiError("ARCHIVE_TOO_MANY_FILES", "压缩包文件数量超过限制。", 413)
            sections: list[str] = []
            extracted_bytes = 0
            for member in members:
                _safe_archive_path(member.name)
                if member.issym() or member.islnk():
                    raise ApiError("UNSAFE_ARCHIVE", "压缩包不能包含链接文件。", 415)
                if not member.isfile() or _extension(member.name) not in TEXT_EXTENSIONS | DOCUMENT_EXTENSIONS:
                    continue
                extracted_bytes += member.size
                if extracted_bytes > max_bytes:
                    raise ApiError("ARCHIVE_TOO_LARGE", "压缩包解压后的可读文件超过大小限制。", 413)
                stream = archive.extractfile(member)
                if stream is None:
                    continue
                text = _extract_member(member.name, stream.read(max_bytes + 1), max_bytes)
                if text.strip():
                    sections.append(f"--- {member.name} ---\n{text}")
            return "\n\n".join(sections)
    except (tarfile.TarError, EOFError) as exc:
        raise ApiError("INVALID_ARCHIVE", "TAR 压缩包损坏或无法读取。", 415) from exc


def _extract_gzip_file(filename: str, content: bytes, max_bytes: int) -> str:
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(content)) as archive:
            data = archive.read(max_bytes + 1)
    except (gzip.BadGzipFile, EOFError, OSError) as exc:
        raise ApiError("INVALID_ARCHIVE", "GZ 压缩包损坏或无法读取。", 415) from exc
    if len(data) > max_bytes:
        raise ApiError("ARCHIVE_TOO_LARGE", "压缩包解压后的文件超过大小限制。", 413)
    inner_name = filename[:-3]
    if _extension(inner_name) not in TEXT_EXTENSIONS | DOCUMENT_EXTENSIONS:
        inner_name += ".txt"
    return f"--- {inner_name} ---\n{_extract_member(inner_name, data, max_bytes)}"


def _extract_member(filename: str, content: bytes, max_bytes: int) -> str:
    if len(content) > max_bytes:
        raise ApiError("ARCHIVE_TOO_LARGE", "压缩包内单个文件超过大小限制。", 413)
    extension = _extension(filename)
    if extension in TEXT_EXTENSIONS:
        return _decode_text(content)
    if extension == ".pdf":
        return _extract_pdf(content)
    if extension in {".docx", ".pptx", ".xlsx"}:
        return _extract_office(extension, content, max_bytes)
    return ""


def _safe_archive_path(value: str) -> None:
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or "\x00" in value:
        raise ApiError("UNSAFE_ARCHIVE", "压缩包包含不安全的文件路径。", 415)


def _local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _finalize_text(text: str) -> str:
    text = text.replace("\x0c", "\n").strip()
    if not text:
        raise ApiError("EMPTY_FILE", "文件中没有可读取的文字内容。", 422)
    forbidden_controls = [char for char in text if ord(char) < 32 and char not in "\n\r\t"]
    if forbidden_controls:
        raise ApiError("INVALID_TEXT_FILE", "文件包含不支持的控制字符。", 415)
    return text
