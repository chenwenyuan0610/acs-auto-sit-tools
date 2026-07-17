from acs_auto_sit.ui_validation import stage_page, validate_stage_fields


def test_stage_validation_matches_runtime_placeholders_and_visible_attributes():
    page = {
        "visibleText": [
            "Verification code was resent via Email to user@example.test",
            "Submit",
            "Need help",
        ]
    }
    fields = {
        "challenge_message": "Verification code was resent via Email to {0}",
        "submit_button": "Submit",
        "help_label": "Need help",
    }

    results = validate_stage_fields("email", fields, page)

    assert [item["status"] for item in results] == ["matched", "matched", "matched"]
    assert {item["stage"] for item in results} == {"email"}
    assert results[0]["actual"] == "Verification code was resent via Email to user@example.test"
    assert results[1]["actual"] == "Submit"


def test_stage_validation_does_not_match_script_or_style_content():
    page = {"visibleText": ["Visible title"]}

    results = validate_stage_fields("sms", {"challenge_message": "hidden-script-copy"}, page)

    assert results[0]["status"] == "missing"
    assert results[0]["actual"] is None


def test_stage_page_extracts_nested_challenge_visible_text():
    action_results = {
        "smsSelection": {
            "challenge": {
                "visibleText": ["Email verification", "Enter Email OTP"],
            }
        }
    }

    page = stage_page(action_results, "smsSelection")

    assert page == {"stage": "smsSelection", "visibleText": ["Email verification", "Enter Email OTP"]}
