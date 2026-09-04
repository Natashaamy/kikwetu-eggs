"""Small Safaricom Daraja sandbox client for M-Pesa STK Push."""

import base64
import json
import os
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SANDBOX_BASE_URL = "https://sandbox.safaricom.co.ke"


class MpesaError(Exception):
    """A safe, user-facing M-Pesa integration error."""


class MpesaConfigurationError(MpesaError):
    """Raised when required sandbox configuration is missing or unsafe."""


def normalize_kenyan_phone(phone_number):
    """Return a Kenyan mobile number in 2547XXXXXXXX/2541XXXXXXXX format."""
    if not isinstance(phone_number, str):
        raise MpesaError("A valid Kenyan phone number is required")

    compact = "".join(character for character in phone_number.strip() if character not in " +()-")
    if compact.startswith("0") and len(compact) == 10:
        compact = "254" + compact[1:]
    elif len(compact) == 9 and compact[0] in {"7", "1"}:
        compact = "254" + compact

    if not compact.isdigit() or len(compact) != 12 or not compact.startswith(("2547", "2541")):
        raise MpesaError("A valid Kenyan phone number is required")
    return compact


def _settings():
    if os.environ.get("MPESA_ENV", "sandbox").strip().lower() != "sandbox":
        raise MpesaConfigurationError("Only M-Pesa sandbox mode is enabled")

    names = (
        "MPESA_CONSUMER_KEY",
        "MPESA_CONSUMER_SECRET",
        "MPESA_SHORTCODE",
        "MPESA_PASSKEY",
        "MPESA_CALLBACK_URL",
    )
    values = {name: os.environ.get(name, "").strip() for name in names}
    if any(not value for value in values.values()):
        raise MpesaConfigurationError("M-Pesa sandbox is not configured")
    if not values["MPESA_CALLBACK_URL"].lower().startswith("https://"):
        raise MpesaConfigurationError("M-Pesa callback URL must use HTTPS")
    return values


def _json_request(url, *, headers=None, payload=None, timeout=20):
    request_headers = {"Accept": "application/json", **(headers or {})}
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"

    try:
        with urlopen(Request(url, data=body, headers=request_headers), timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        # Read and discard the response so connection resources are released. Never
        # include Daraja response details because they may contain sensitive context.
        error.read()
        raise MpesaError("M-Pesa is currently unable to process the request") from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise MpesaError("M-Pesa is currently unavailable. Please try again") from error


def get_access_token(settings=None):
    """Request a short-lived OAuth token without logging or returning credentials."""
    settings = settings or _settings()
    credentials = base64.b64encode(
        f'{settings["MPESA_CONSUMER_KEY"]}:{settings["MPESA_CONSUMER_SECRET"]}'.encode("utf-8")
    ).decode("ascii")
    response = _json_request(
        f"{SANDBOX_BASE_URL}/oauth/v1/generate?grant_type=client_credentials",
        headers={"Authorization": f"Basic {credentials}"},
    )
    token = response.get("access_token")
    if not token:
        raise MpesaError("M-Pesa authentication failed")
    return token


def initiate_stk_push(*, phone_number, amount, order_number):
    """Send an STK Push using server-owned price and sandbox credentials."""
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
        raise MpesaError("This order does not have a payable amount")

    settings = _settings()
    normalized_phone = normalize_kenyan_phone(phone_number)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    password = base64.b64encode(
        f'{settings["MPESA_SHORTCODE"]}{settings["MPESA_PASSKEY"]}{timestamp}'.encode("utf-8")
    ).decode("ascii")
    payload = {
        "BusinessShortCode": settings["MPESA_SHORTCODE"],
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": amount,
        "PartyA": normalized_phone,
        "PartyB": settings["MPESA_SHORTCODE"],
        "PhoneNumber": normalized_phone,
        "CallBackURL": settings["MPESA_CALLBACK_URL"],
        "AccountReference": order_number[:12],
        "TransactionDesc": f"Payment for {order_number}"[:20],
    }
    response = _json_request(
        f"{SANDBOX_BASE_URL}/mpesa/stkpush/v1/processrequest",
        headers={"Authorization": f"Bearer {get_access_token(settings)}"},
        payload=payload,
    )

    merchant_request_id = response.get("MerchantRequestID")
    checkout_request_id = response.get("CheckoutRequestID")
    if str(response.get("ResponseCode")) != "0" or not merchant_request_id or not checkout_request_id:
        raise MpesaError("M-Pesa payment prompt could not be sent")
    return {
        "merchant_request_id": merchant_request_id,
        "checkout_request_id": checkout_request_id,
        "phone_number": normalized_phone,
    }
