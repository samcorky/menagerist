from app.modules.identity.adapters.api.device_header_fields import device_header_fields


def test_device_header_fields_has_only_allowlisted_keys() -> None:
    """Absent request headers remain visible as `None` without extra fields."""
    fields = device_header_fields({}, None)

    assert fields == {
        "user_agent": None,
        "sec_ch_ua": None,
        "sec_ch_ua_mobile": None,
        "sec_ch_ua_platform": None,
        "x_forwarded_for": None,
        "x_forwarded_proto": None,
        "forwarded": None,
        "client_ip": None,
    }


def test_device_header_fields_escapes_controls_and_caps_values() -> None:
    """Untrusted headers cannot inject controls or unbounded log values."""
    fields = device_header_fields(
        {"User-Agent": "browser\n\x1b[31m" + "x" * 300}, "192.0.2.1\r\n"
    )

    assert fields["user_agent"] == "browser\\x0a\\x1b[31m" + "x" * 234 + "..."
    assert len(fields["user_agent"] or "") == 256
    assert fields["client_ip"] == "192.0.2.1\\x0d\\x0a"
    assert all(value is None or len(value) <= 256 for value in fields.values())
