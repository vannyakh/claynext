"""Round-trip for Settings → API Keys export and import."""
from claynext.models.llm_keys import export_api_keys_payload, parse_api_keys_payload


def test_export_and_import_round_trip():
    payload = export_api_keys_payload([
        {"provider": "gemini", "label": "K1", "secret": "test-secret-one", "enabled": 1},
        {"provider": "elevenlabs", "label": "", "secret": "test-secret-two", "enabled": 0},
        {"provider": "gemini", "label": "blank", "secret": "  ", "enabled": 1},
    ])
    assert payload["format"] == "claynext-api-keys"
    assert [row["label"] for row in payload["keys"]] == ["K1", ""]
    parsed = parse_api_keys_payload(payload)
    assert parsed[0]["provider"] == "gemini"
    assert parsed[0]["enabled"] is True
    assert parsed[1]["provider"] == "elevenlabs"
    assert parsed[1]["enabled"] is False


def test_import_accepts_a_provider_label_and_a_bare_list():
    rows = parse_api_keys_payload([
        {"provider": "Google Gemini", "key": "test-secret-three", "label": "Desk"},
    ])
    assert rows == [{
        "provider": "gemini",
        "label": "Desk",
        "secret": "test-secret-three",
        "enabled": True,
    }]


def test_import_rejects_a_file_with_no_keys():
    try:
        parse_api_keys_payload({"format": "claynext-api-keys", "keys": []})
    except ValueError as exc:
        assert "no keys" in str(exc).lower()
    else:
        raise AssertionError("empty file should fail")
