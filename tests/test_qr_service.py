"""
tests/test_qr_service.py — Unit tests for QR payload builders and validators.
All functions are pure; no DB or network needed.
"""
import pytest

from app.services.qr_service import (
    UPIPayload,
    build_email_payload,
    build_geo_payload,
    build_sms_payload,
    build_upi_payload,
    build_vcard_payload,
    build_wifi_payload,
    validate_vpa,
)


# ── VPA validation ────────────────────────────────────────────────────────

class TestVPAValidation:
    def test_valid_vpas(self):
        valid = [
            "name@upi",
            "9876543210@paytm",
            "merchant@okaxis",
            "user.name@ybl",
            "abc@icici",
        ]
        for vpa in valid:
            assert validate_vpa(vpa), f"Should be valid: {vpa}"

    def test_invalid_vpas(self):
        invalid = [
            "",
            "noatsign",
            "@noprefix",
            "a@",
            "user@1",   # numeric provider < 2 alpha
            "x" * 300 + "@upi",  # too long
        ]
        for vpa in invalid:
            assert not validate_vpa(vpa), f"Should be invalid: {vpa}"


# ── UPI payload builder ───────────────────────────────────────────────────

class TestUPIPayload:
    def test_basic_payload(self):
        p = UPIPayload(vpa="test@upi", payee_name="Test User")
        result = build_upi_payload(p)
        assert result.startswith("upi://pay?")
        assert "pa=test%40upi" in result or "pa=test@upi" in result
        assert "cu=INR" in result

    def test_with_amount(self):
        p = UPIPayload(vpa="a@b", payee_name="Name", amount=100.50)
        result = build_upi_payload(p)
        assert "am=100.50" in result

    def test_without_amount(self):
        p = UPIPayload(vpa="a@b", payee_name="Name", amount=0)
        result = build_upi_payload(p)
        assert "am=" not in result

    def test_with_note(self):
        p = UPIPayload(vpa="a@b", payee_name="Name", note="Payment for dinner")
        result = build_upi_payload(p)
        assert "tn=" in result

    def test_payee_name_encoded(self):
        p = UPIPayload(vpa="a@b", payee_name="Café Owner")
        result = build_upi_payload(p)
        assert "pn=" in result
        assert "Café Owner" not in result  # must be URL-encoded


# ── Wi-Fi payload ─────────────────────────────────────────────────────────

class TestWifiPayload:
    def test_wpa_network(self):
        r = build_wifi_payload("MySSID", "MyPassword", "WPA")
        assert r.startswith("WIFI:")
        assert "S:MySSID" in r
        assert "P:MyPassword" in r
        assert "T:WPA" in r

    def test_open_network(self):
        r = build_wifi_payload("OpenNet", "", "nopass")
        assert "T:nopass" in r
        assert r.endswith(";;")

    def test_hidden_network(self):
        r = build_wifi_payload("HiddenSSID", "pass", hidden=True)
        assert "H:true" in r


# ── vCard payload ─────────────────────────────────────────────────────────

class TestVCardPayload:
    def test_full_vcard(self):
        r = build_vcard_payload("John Doe", "+911234567890", "john@example.com", "ACME")
        assert "BEGIN:VCARD" in r
        assert "END:VCARD" in r
        assert "FN:John Doe" in r
        assert "TEL:+911234567890" in r
        assert "EMAIL:john@example.com" in r
        assert "ORG:ACME" in r

    def test_minimal_vcard(self):
        r = build_vcard_payload("Jane", "")
        assert "BEGIN:VCARD" in r
        assert "FN:Jane" in r


# ── Email payload ─────────────────────────────────────────────────────────

class TestEmailPayload:
    def test_basic_email(self):
        r = build_email_payload("user@example.com")
        assert r == "mailto:user@example.com"

    def test_email_with_subject(self):
        r = build_email_payload("user@example.com", subject="Hello")
        assert "subject=Hello" in r

    def test_email_with_body(self):
        r = build_email_payload("user@example.com", body="Hi there")
        assert "body=" in r


# ── SMS payload ───────────────────────────────────────────────────────────

class TestSMSPayload:
    def test_basic_sms(self):
        r = build_sms_payload("+919876543210")
        assert r == "sms:+919876543210"

    def test_sms_with_message(self):
        r = build_sms_payload("+91123", "Hello World")
        assert "body=Hello%20World" in r


# ── Geo payload ───────────────────────────────────────────────────────────

class TestGeoPayload:
    def test_basic_geo(self):
        r = build_geo_payload(28.6139, 77.2090)
        assert r == "geo:28.6139,77.209"

    def test_geo_with_query(self):
        r = build_geo_payload(28.6, 77.2, "New Delhi")
        assert "q=New%20Delhi" in r
