from acs_auto_sit.three_ds import (
    build_first_creq,
    build_next_creq_draft,
    extract_acs_values,
    requires_challenge,
)


def test_non_challenge_ares_does_not_build_creq():
    areq = {"threeDSServerTransID": "server-trans-1", "messageVersion": "2.2.0"}
    ares = {"messageType": "ARes", "transStatus": "Y"}

    assert requires_challenge(ares) is False
    assert build_first_creq(ares, areq) is None


def test_challenge_ares_builds_first_creq_from_ares_and_areq():
    areq = {"threeDSServerTransID": "server-trans-1", "messageVersion": "2.2.0"}
    ares = {
        "messageType": "ARes",
        "messageVersion": "2.2.0",
        "transStatus": "C",
        "acsTransID": "acs-trans-1",
        "acsURL": "https://acs.example.test/challenge",
    }

    creq = build_first_creq(ares, areq, challenge_window_size="05")

    assert creq == {
        "messageType": "CReq",
        "messageVersion": "2.2.0",
        "threeDSServerTransID": "server-trans-1",
        "acsTransID": "acs-trans-1",
        "challengeWindowSize": "05",
    }


def test_challenge_cres_builds_editable_next_creq_draft():
    previous_creq = {
        "messageType": "CReq",
        "messageVersion": "2.2.0",
        "threeDSServerTransID": "server-trans-1",
        "acsTransID": "acs-trans-1",
        "challengeWindowSize": "05",
    }
    cres = {"messageType": "CRes", "transStatus": "C"}

    draft = build_next_creq_draft(cres, previous_creq)

    assert draft["messageType"] == "CReq"
    assert draft["threeDSServerTransID"] == "server-trans-1"
    assert draft["acsTransID"] == "acs-trans-1"
    assert draft["challengeDataEntry"] == ""


def test_extract_acs_values_reads_known_response_fields():
    ares = {
        "transStatus": "C",
        "acsURL": "https://acs.example.test/challenge",
        "acsTransID": "acs-trans-1",
        "threeDSServerTransID": "server-trans-1",
    }

    assert extract_acs_values(ares) == {
        "transStatus": "C",
        "acsURL": "https://acs.example.test/challenge",
        "acsTransID": "acs-trans-1",
        "threeDSServerTransID": "server-trans-1",
    }
