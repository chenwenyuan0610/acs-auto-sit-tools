from acs_auto_sit.challenge import parse_challenge_page


def test_challenge_parser_detects_oob_continue_page():
    page = parse_challenge_page(
        """
        <html><body>
          <form action="/oob" method="POST">
            <input type="hidden" name="acsTransID" value="acs-trans-1">
            <input type="hidden" name="oobContinue" value="">
            <button type="submit">Continue</button>
          </form>
        </body></html>
        """,
        "https://acs.example.test/challenge",
    )

    assert page["type"] == "oob"
    assert page["fields"]["oobContinue"] == ""


def test_challenge_parser_detects_oob_page_that_can_switch_to_otp():
    page = parse_challenge_page(
        """
        <html><body>
          <form action="/oob" method="POST">
            <input type="hidden" name="acsTransID" value="acs-trans-1">
            <input type="hidden" name="oobContinue" value="">
            <input type="hidden" name="switchauthm" value="N">
            <button type="submit">Continue</button>
          </form>
        </body></html>
        """,
        "https://acs.example.test/challenge",
    )

    assert page["type"] == "oob"
    assert page["availableActions"]["oobContinue"] is True
    assert page["availableActions"]["switchToOtp"] is True


def test_challenge_parser_detects_resend_code_button():
    page = parse_challenge_page(
        """
        <html><body>
          <form action="/otp" method="POST">
            <input type="hidden" name="acsTransID" value="acs-trans-1">
            <input type="text" name="challengeValue" value="">
            <button type="submit" name="resendCode" value="Y">RESEND CODE</button>
          </form>
        </body></html>
        """,
        "https://acs.example.test/challenge",
    )

    assert page["type"] == "otp"
    assert page["availableActions"]["resendOtp"] is True


def test_challenge_parser_retains_raw_html_for_technical_details():
    raw_html = "<html><body><strong>Important wording</strong></body></html>"

    page = parse_challenge_page(raw_html, "https://acs.example.test/challenge")

    assert page["rawHtml"] == raw_html


def test_challenge_parser_collects_visible_wording_from_common_attributes():
    page = parse_challenge_page(
        """
        <html><body>
          <form action="/select" method="POST">
            <h1>Challenge Methods Selection</h1>
            <p>Please select Challenge Methods</p>
            <input type="radio" id="sms" name="challengeValue" value="1">
            <label for="sms">SMS OTP</label>
            <input type="submit" name="nextStep" value="Next">
            <button type="button" aria-label="Want Help ?"></button>
            <div title="For further questions, please call the phone number on the back of your credit card."></div>
          </form>
        </body></html>
        """,
        "https://acs.example.test/challenge",
    )

    assert page["visibleText"] == [
        "Challenge Methods Selection",
        "Please select Challenge Methods",
        "SMS OTP",
        "Next",
        "Want Help ?",
        "For further questions, please call the phone number on the back of your credit card.",
    ]


def test_challenge_parser_ignores_script_style_template_and_noscript_text():
    page = parse_challenge_page(
        """
        <html><body>
          <style>hidden-style-copy</style>
          <script>hidden-script-copy</script>
          <template>hidden-template-copy</template>
          <noscript>hidden-noscript-copy</noscript>
          <form action="/select" method="POST">
            <div aria-label="Visible aria label"></div>
            <input type="text" placeholder="Visible placeholder">
          </form>
        </body></html>
        """,
        "https://acs.example.test/challenge",
    )

    assert "hidden-style-copy" not in page["visibleText"]
    assert "hidden-script-copy" not in page["visibleText"]
    assert "hidden-template-copy" not in page["visibleText"]
    assert "hidden-noscript-copy" not in page["visibleText"]
    assert "Visible aria label" in page["visibleText"]
    assert "Visible placeholder" in page["visibleText"]


def test_challenge_parser_excludes_non_visible_container_text():
    page = parse_challenge_page(
        "<html><style>hidden-style-copy</style><script>hidden-script-copy</script>"
        "<template>hidden-template-copy</template><noscript>hidden-noscript-copy</noscript>"
        "<body><p>Visible title</p></body></html>",
        "https://acs.example.test/challenge",
    )

    assert page["visibleText"] == ["Visible title"]
