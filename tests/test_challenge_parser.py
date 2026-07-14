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
