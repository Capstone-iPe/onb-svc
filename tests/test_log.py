import logging

from onb.log import log_result


def test_log_names_the_tool_and_not_the_answer(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="onb"):
        log_result(
            "save_answer",
            {
                "application_id": "app_1",
                "field": "shop_name",
                "value": "Lotus Tea House",
                "snapshot": {"answers": {"shop_name": "Lotus Tea House"}},
            },
        )

    assert len(caplog.records) == 1
    message = caplog.records[0].message
    assert "tool=save_answer" in message
    assert "application_id=app_1" in message
    assert "field=shop_name" in message
    assert "Lotus Tea House" not in message


def test_an_error_is_a_warning(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="onb"):
        log_result("save_file", {"error": "file_missing", "slot": "bank_proof"})

    assert caplog.records[0].levelname == "WARNING"
    assert "error=file_missing" in caplog.records[0].message
    assert "slot=bank_proof" in caplog.records[0].message
