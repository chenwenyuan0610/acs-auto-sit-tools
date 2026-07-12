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
