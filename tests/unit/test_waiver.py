"""Tests for functions/kiosk/waiver/handler.py

POST /v1/kiosk/waiver — stores a signed waiver PDF in S3 and records it in Aurora.
"""
import base64
import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import FakeContext, device_event, load_kiosk_handler
from tests.helpers import make_rds

FAKE_PDF = base64.b64encode(b"%PDF-1.4 fake pdf content").decode()
FAKE_MEMBER_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
FAKE_GUEST_ID = "11111111-2222-3333-4444-555555555555"


@pytest.fixture()
def mod():
    m = load_kiosk_handler("waiver")
    yield m
    for key in list(sys.modules.keys()):
        if key in ("_auth", "kiosk_waiver_handler"):
            del sys.modules[key]


def _make_s3():
    """Return an S3 mock that accepts put_object."""
    s3 = MagicMock()
    s3.put_object.return_value = {}
    return s3


def _rds_member():
    return make_rds({
        "set_config": {"records": []},
        "FROM members WHERE id": {"records": [[{"stringValue": FAKE_MEMBER_ID}]]},
        "UPDATE members": {"numberOfRecordsUpdated": 1},
        "INSERT INTO activity_logs": {"numberOfRecordsUpdated": 1},
    })


def _rds_guest():
    return make_rds({
        "set_config": {"records": []},
        "FROM guests WHERE id": {"records": [[{"stringValue": FAKE_GUEST_ID}]]},
        "UPDATE guests": {"numberOfRecordsUpdated": 1},
        "INSERT INTO activity_logs": {"numberOfRecordsUpdated": 1},
    })


def _client_factory(s3_mock, rds_mock):
    def _factory(svc, **_):
        if svc == "s3":
            return s3_mock
        return rds_mock
    return _factory


class TestWaiver:
    def test_happy_path_member_waiver(self, mod):
        s3, rds = _make_s3(), _rds_member()
        with patch("boto3.client", side_effect=_client_factory(s3, rds)):
            resp = mod.handler(
                device_event({"member_id": FAKE_MEMBER_ID, "pdf_bytes": FAKE_PDF}),
                FakeContext(),
            )
        assert resp["statusCode"] == 200
        s3.put_object.assert_called_once()

    def test_happy_path_guest_waiver(self, mod):
        s3, rds = _make_s3(), _rds_guest()
        with patch("boto3.client", side_effect=_client_factory(s3, rds)):
            resp = mod.handler(
                device_event({
                    "member_id": FAKE_MEMBER_ID,
                    "pdf_bytes": FAKE_PDF,
                    "guest_id": FAKE_GUEST_ID,
                }),
                FakeContext(),
            )
        assert resp["statusCode"] == 200
        s3.put_object.assert_called_once()

    def test_missing_device_token_returns_403(self, mod):
        event = {
            "httpMethod": "POST",
            "headers": {},
            "body": json.dumps({"member_id": FAKE_MEMBER_ID, "pdf_bytes": FAKE_PDF}),
            "pathParameters": {},
        }
        rds = MagicMock()
        rds.execute_statement.return_value = {"records": []}
        with patch("boto3.client", return_value=rds):
            resp = mod.handler(event, FakeContext())
        assert resp["statusCode"] == 403

    def test_missing_member_id_returns_400(self, mod):
        rds = _rds_member()
        with patch("boto3.client", side_effect=_client_factory(_make_s3(), rds)):
            resp = mod.handler(device_event({"pdf_bytes": FAKE_PDF}), FakeContext())
        assert resp["statusCode"] == 400

    def test_missing_pdf_bytes_returns_400(self, mod):
        rds = _rds_member()
        with patch("boto3.client", side_effect=_client_factory(_make_s3(), rds)):
            resp = mod.handler(device_event({"member_id": FAKE_MEMBER_ID}), FakeContext())
        assert resp["statusCode"] == 400

    def test_invalid_member_id_uuid_returns_400(self, mod):
        rds = _rds_member()
        with patch("boto3.client", side_effect=_client_factory(_make_s3(), rds)):
            resp = mod.handler(
                device_event({"member_id": "not-a-uuid", "pdf_bytes": FAKE_PDF}),
                FakeContext(),
            )
        assert resp["statusCode"] == 400

    def test_invalid_base64_pdf_returns_400(self, mod):
        rds = _rds_member()
        with patch("boto3.client", side_effect=_client_factory(_make_s3(), rds)):
            resp = mod.handler(
                device_event({"member_id": FAKE_MEMBER_ID, "pdf_bytes": "!!!notbase64!!!"}),
                FakeContext(),
            )
        assert resp["statusCode"] == 400

    def test_s3_failure_returns_500(self, mod):
        s3 = MagicMock()
        s3.put_object.side_effect = Exception("S3 unavailable")
        rds = _rds_member()
        with patch("boto3.client", side_effect=_client_factory(s3, rds)):
            resp = mod.handler(
                device_event({"member_id": FAKE_MEMBER_ID, "pdf_bytes": FAKE_PDF}),
                FakeContext(),
            )
        assert resp["statusCode"] == 500

    def test_cors_headers_present(self, mod):
        rds = MagicMock()
        rds.execute_statement.return_value = {"records": []}
        with patch("boto3.client", return_value=rds):
            resp = mod.handler(
                device_event({"member_id": FAKE_MEMBER_ID, "pdf_bytes": FAKE_PDF}),
                FakeContext(),
            )
        assert "Access-Control-Allow-Origin" in resp["headers"]
