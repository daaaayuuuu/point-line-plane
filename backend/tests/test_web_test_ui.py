from __future__ import annotations


def test_web_test_ui_is_served_without_exposing_demo_credentials(client) -> None:
    page = client.get("/test-ui/")
    assert page.status_code == 200, page.text
    assert "AI 产品工厂｜第三阶段体验台" in page.text
    assert "产品地图" in page.text
    assert "虚拟用户走查" in page.text
    assert "受控自动开发" in page.text
    assert "逐个查看文件用途和精确代码" in page.text
    assert "phase2-demo-invite" not in page.text

    styles = client.get("/test-ui/styles.css")
    script = client.get("/test-ui/app.js")
    assert styles.status_code == 200
    assert script.status_code == 200
    assert "product-dashboard" in script.text
    assert "technical_contract" in script.text
    assert "development-runs" in script.text
    assert "code-versions" in script.text
