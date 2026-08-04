from veadk.utils.auth import (
    TIP_TOKEN_KEY_HEADER,
    extract_tip_token_key_from_payload,
    extract_tip_token_key_from_request_parts,
)


def test_extract_tip_token_key_prefers_header_over_body():
    token_key = extract_tip_token_key_from_request_parts(
        headers={TIP_TOKEN_KEY_HEADER: " header-key "},
        payload={"auth": {"tip_token_key": "body-key"}},
    )

    assert token_key == "header-key"


def test_extract_tip_token_key_reads_body_auth_field_when_header_missing():
    token_key = extract_tip_token_key_from_payload(
        {"auth": {"tip_token_key": " body-key "}}
    )

    assert token_key == "body-key"


def test_extract_tip_token_key_ignores_ve_tip_token_header():
    token_key = extract_tip_token_key_from_request_parts(
        headers={"X-Ve-TIP-Token": "raw-or-unknown"},
        payload={},
    )

    assert token_key is None


def test_extract_tip_token_key_returns_none_when_missing_or_empty():
    assert extract_tip_token_key_from_request_parts(headers={}, payload={}) is None
    assert (
        extract_tip_token_key_from_request_parts(
            headers={TIP_TOKEN_KEY_HEADER: " "},
            payload={"auth": {"tip_token_key": ""}},
        )
        is None
    )
