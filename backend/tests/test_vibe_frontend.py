from types import SimpleNamespace

from app.services.vibe_frontend import _is_timer_product, _timer_html


def test_learning_alarm_is_generated_as_an_interactive_timer() -> None:
    prd = SimpleNamespace(
        title="西瓜时间学习闹钟",
        summary="固定 25 分钟专注与 5 分钟短休息，每 4 轮进入长休息。",
        features=["开始、暂停、继续、结束本轮", "剩余时间和完成轮数"],
        acceptance_criteria=["用户可以操作完整专注循环"],
        scope={"included": ["专注与休息阶段切换"]},
        full_document=None,
    )

    assert _is_timer_product(prd) is True
    page = _timer_html(prd, "pop-typographic")
    assert 'id="toggleButton"' in page
    assert 'id="finishButton"' in page
    assert 'id="notificationButton"' in page
    assert "结束本轮" in page
    assert "finish.addEventListener('click', finishCurrentPhase)" in page
    assert "未完整完成，因此没有计入今日统计" in page
    assert "localStorage" in page
    assert 'data-ui-style="pop-typographic"' in page
