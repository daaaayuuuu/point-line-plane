from __future__ import annotations

import gzip
import io
import logging
import tarfile
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.support import ApiHarness, assert_error


def _pdf_with_text(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET\n".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream",
    ]
    payload = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, item in enumerate(objects, start=1):
        offsets.append(len(payload))
        payload.extend(f"{index} 0 obj\n".encode() + item + b"\nendobj\n")
    xref = len(payload)
    payload.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    payload.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        payload.extend(f"{offset:010d} 00000 n \n".encode())
    payload.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(payload)


def _zip_bytes(members: dict[str, str | bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _tar_bytes(name: str, content: bytes, *, gzip_enabled: bool) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz" if gzip_enabled else "w") as archive:
        member = tarfile.TarInfo(name)
        member.size = len(content)
        archive.addfile(member, io.BytesIO(content))
    return buffer.getvalue()


def test_text_code_pdf_and_zip_uploads_create_prd(
    api: ApiHarness,
    client: TestClient,
) -> None:
    token, _user = api.login("Upload User")
    markdown_project = api.create_project(token, name="Markdown Project")
    markdown = client.post(
        f"/api/v1/projects/{markdown_project['id']}/requirements/upload",
        files={"file": ("requirements.md", b"# Requirements\n\nReturn three insights.", "text/markdown")},
    )
    assert markdown.status_code == 200, markdown.text
    assert markdown.json()["status"] == "prd_ready"
    assert markdown.json()["artifact"]["type"] == "prd"

    text_project = api.create_project(token, name="Text Project")
    plain_text = client.post(
        f"/api/v1/projects/{text_project['id']}/requirements/upload",
        files={"file": ("需求说明.TXT", "输出摘要和建议".encode(), "text/plain")},
    )
    assert plain_text.status_code == 200, plain_text.text
    assert plain_text.json()["artifact"]["version"] == 1

    sql_project = api.create_project(token, name="SQL Project")
    sql = client.post(
        f"/api/v1/projects/{sql_project['id']}/requirements/upload",
        files={"file": ("schema.sql", b"CREATE TABLE tasks (id INTEGER);", "application/sql")},
    )
    assert sql.status_code == 200, sql.text

    pdf_project = api.create_project(token, name="PDF Project")
    pdf = client.post(
        f"/api/v1/projects/{pdf_project['id']}/requirements/upload",
        files={"file": ("requirements.pdf", _pdf_with_text("PDF requirement"), "application/pdf")},
    )
    assert pdf.status_code == 200, pdf.text

    archive_payload = _zip_bytes(
        {
            "docs/requirements.md": "# Archive requirement",
            "db/schema.sql": "CREATE TABLE projects (id INTEGER);",
            "assets/ignored.png": b"\x89PNG\r\n\x1a\n",
        }
    )
    archive_project = api.create_project(token, name="ZIP Project")
    zipped = client.post(
        f"/api/v1/projects/{archive_project['id']}/requirements/upload",
        files={"file": ("product-context.zip", archive_payload, "application/zip")},
    )
    assert zipped.status_code == 200, zipped.text


def test_office_and_compressed_text_uploads_create_prd(
    api: ApiHarness,
    client: TestClient,
) -> None:
    token, _user = api.login("Document Upload User")
    cases = [
        (
            "requirements.docx",
            _zip_bytes(
                {
                    "word/document.xml": (
                        '<w:document xmlns:w="urn:word"><w:body><w:p><w:r>'
                        "<w:t>DOCX requirement</w:t></w:r></w:p></w:body></w:document>"
                    )
                }
            ),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        (
            "requirements.pptx",
            _zip_bytes(
                {
                    "ppt/slides/slide1.xml": (
                        '<p:sld xmlns:p="urn:presentation" xmlns:a="urn:drawing">'
                        "<a:t>PPTX requirement</a:t></p:sld>"
                    )
                }
            ),
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ),
        (
            "requirements.xlsx",
            _zip_bytes(
                {
                    "xl/sharedStrings.xml": (
                        '<sst xmlns="urn:sheet"><si><t>XLSX requirement</t></si></sst>'
                    ),
                    "xl/worksheets/sheet1.xml": (
                        '<worksheet xmlns="urn:sheet"><sheetData><row><c t="s"><v>0</v>'
                        "</c></row></sheetData></worksheet>"
                    ),
                }
            ),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        (
            "schema.sql.gz",
            gzip.compress(b"CREATE TABLE compressed_sql (id INTEGER);"),
            "application/gzip",
        ),
        (
            "context.tar.gz",
            _tar_bytes("docs/context.md", b"# Compressed context", gzip_enabled=True),
            "application/gzip",
        ),
    ]
    for filename, payload, content_type in cases:
        project = api.create_project(token, name=f"Upload {filename}")
        response = client.post(
            f"/api/v1/projects/{project['id']}/requirements/upload",
            files={"file": (filename, payload, content_type)},
        )
        assert response.status_code == 200, f"{filename}: {response.text}"


@pytest.mark.parametrize(
    ("filename", "content", "content_type", "status_code", "error_code"),
    [
        ("../escape.md", b"unsafe path", "text/markdown", 400, "UNSAFE_FILENAME"),
        ("..\\escape.md", b"unsafe path", "text/markdown", 400, "UNSAFE_FILENAME"),
        ("requirements.exe", b"plain text", "application/octet-stream", 415, "UNSUPPORTED_FILE_TYPE"),
        ("requirements.pdf", b"plain text", "text/plain", 415, "UNSUPPORTED_CONTENT_TYPE"),
        ("requirements.md", b"plain text", "image/png", 415, "UNSUPPORTED_CONTENT_TYPE"),
        ("requirements.txt", b"x" * 1_025, "text/plain", 413, "FILE_TOO_LARGE"),
        ("requirements.txt", b"hello\x00world", "text/plain", 415, "INVALID_TEXT_FILE"),
        ("requirements.txt", b"\xff\xfe\xfa", "text/plain", 415, "INVALID_TEXT_FILE"),
        ("requirements.txt", b"  \n\t", "text/plain", 422, "EMPTY_FILE"),
    ],
)
def test_upload_rejects_unsafe_type_size_and_encoding(
    api: ApiHarness,
    client: TestClient,
    filename: str,
    content: bytes,
    content_type: str,
    status_code: int,
    error_code: str,
) -> None:
    token, _user = api.login(f"Upload Case {filename} {error_code}")
    project = api.create_project(token)
    response = client.post(
        f"/api/v1/projects/{project['id']}/requirements/upload",
        files={"file": (filename, content, content_type)},
    )
    assert_error(response, status_code=status_code, code=error_code)

    detail = client.get(f"/api/v1/projects/{project['id']}")
    assert detail.status_code == 200
    assert detail.json()["stage"] == "REQUIREMENTS"
    artifacts = client.get(f"/api/v1/projects/{project['id']}/artifacts")
    assert artifacts.status_code == 200
    assert artifacts.json()["items"] == []


def test_upload_rejects_binary_content_disguised_as_text(
    api: ApiHarness,
    client: TestClient,
) -> None:
    token, _user = api.login("Disguised Binary User")
    project = api.create_project(token)
    response = client.post(
        f"/api/v1/projects/{project['id']}/requirements/upload",
        files={"file": ("requirements.txt", b"%PDF-1.7\n1 0 obj\n", "text/plain")},
    )
    assert_error(
        response,
        status_code=415,
        code={"INVALID_TEXT_FILE", "UNSUPPORTED_CONTENT_TYPE"},
    )


def test_upload_rejects_unsafe_archive_paths(api: ApiHarness, client: TestClient) -> None:
    token, _user = api.login("Unsafe Archive User")
    project = api.create_project(token)
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        archive.writestr("../escape.sql", "SELECT 1;")
    response = client.post(
        f"/api/v1/projects/{project['id']}/requirements/upload",
        files={"file": ("unsafe.zip", archive_buffer.getvalue(), "application/zip")},
    )
    assert_error(response, status_code=415, code="UNSAFE_ARCHIVE")


def test_text_plain_with_utf8_charset_is_accepted(
    api: ApiHarness,
    client: TestClient,
) -> None:
    token, _user = api.login("Charset User")
    project = api.create_project(token)
    response = client.post(
        f"/api/v1/projects/{project['id']}/requirements/upload",
        files={"file": ("requirements.txt", "纯文本需求".encode(), "text/plain; charset=utf-8")},
    )
    assert response.status_code == 200, response.text


def test_validation_not_found_and_unknown_route_use_one_error_envelope(
    api: ApiHarness,
    client: TestClient,
) -> None:
    validation = client.post(
        "/api/v1/auth/invite-login",
        json={"invite_code": "test-invite", "display_name": ""},
        headers={"X-Request-ID": "validation-trace"},
    )
    validation_error = assert_error(validation, status_code=422, code="VALIDATION_ERROR")
    assert validation_error["trace_id"] == "validation-trace"
    assert "input" not in validation.text.lower()

    token, _user = api.login("Error User")
    api.use_token(token)
    missing = client.get("/api/v1/projects/not-a-real-project")
    assert_error(missing, status_code=404, code="NOT_FOUND")

    unknown = client.get("/api/v1/not-a-real-route")
    assert_error(unknown, status_code=404, code="HTTP_ERROR")


def test_unexpected_provider_failure_returns_generic_error_without_secret_or_stack(
    api: ApiHarness,
    client: TestClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    token, _user = api.login("No Leak User")
    _project, _task, preview_token = api.build_preview(token)
    secret_marker = "sk-test-super-secret-never-return"

    def explode_runtime(**_kwargs):
        raise RuntimeError(f"Traceback at generated runtime with {secret_marker}")

    monkeypatch.setattr(app.state.preview_manager, "request", explode_runtime)
    caplog.set_level(logging.ERROR)
    response = client.post(
        f"/api/v1/previews/{preview_token}/runs",
        json={"input": "trigger controlled test failure"},
        headers={"X-Request-ID": "unexpected-error-trace"},
    )
    error = assert_error(response, status_code=500, code="INTERNAL_ERROR")
    assert error["trace_id"] == "unexpected-error-trace"
    combined = response.text + "\n" + caplog.text
    assert secret_marker not in combined
    assert "traceback at generated runtime" not in combined.lower()
    assert "runtimeerror:" not in combined.lower()
