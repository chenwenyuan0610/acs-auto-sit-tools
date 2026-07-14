from acs_auto_sit.transaction_result_provider import simulated_transaction_result_for_acs_trans_id


def test_simulated_transaction_result_returns_successful_mastercard_fields():
    result = simulated_transaction_result_for_acs_trans_id("acs-trans-1")

    assert result["ok"] is True
    assert result["source"] == "simulated"
    assert result["acsTransID"] == "acs-trans-1"
    assert result["transaction"]["transStatus"] == "Y"
    assert result["transaction"]["eci"] == "02"
    assert result["transaction"]["cavv"]
    assert result["checks"]["cavv"]["status"] == "pass"
    assert result["checks"]["eci"]["status"] == "pass"


def test_simulated_transaction_result_is_stable_for_same_acs_trans_id():
    first = simulated_transaction_result_for_acs_trans_id("acs-trans-1")
    second = simulated_transaction_result_for_acs_trans_id("acs-trans-1")

    assert first["transaction"]["cavv"] == second["transaction"]["cavv"]
