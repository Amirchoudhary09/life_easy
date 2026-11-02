from pydantic import ValidationError
from app.auth import RegisterBody,PhoneLoginSend
def test_signup_requires_valid_e164_phone():
    user=RegisterBody(display_name="Test User",email="test@example.com",password="a-very-long-test-password",phone_e164="+919876543210")
    assert user.phone_e164=="+919876543210"
def test_signup_rejects_non_e164_phone():
    try:
        RegisterBody(display_name="Test User",email="test@example.com",password="a-very-long-test-password",phone_e164="9876543210")
    except ValidationError:
        return
    raise AssertionError("Invalid phone number should be rejected")
def test_phone_login_accepts_e164():
    assert PhoneLoginSend(phone_e164="+919876543210").phone_e164=="+919876543210"
