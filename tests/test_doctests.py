import doctest
import app.core.security


def test_security_doctests():
    """
    Executes all docstring tests in app.core.security.
    Covers:
      - base64url_encode
      - base64url_decode
      - generate_qr_token
      - verify_qr_token
    """
    results = doctest.testmod(app.core.security)
    assert results.failed == 0, f"Doctests failed in app.core.security: {results}"
    assert results.attempted > 0, "No doctests were discovered in app.core.security"
