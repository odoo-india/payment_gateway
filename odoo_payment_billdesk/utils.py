# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
import base64
import os
import hmac
import hashlib
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend


def base64url_encode(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=')


def base64url_decode(data):
    padding = '=' * (-len(data) % 4)
    data += padding
    return base64.urlsafe_b64decode(data.encode())


def encrypt_request(json_payload, encryption_key, key_id, client_id):
    plaintext = json_payload.encode()
    iv = os.urandom(12)

    protected_header = {
        'alg': 'dir',
        'enc': 'A256GCM',
        'kid': key_id,
        'clientid': client_id,
    }

    protected_b64 = base64url_encode(
        json.dumps(protected_header, separators=(',', ':')).encode()
    )

    cipher = Cipher(
        algorithms.AES(encryption_key.encode()),
        modes.GCM(iv),
        backend=default_backend()
    )

    encryptor = cipher.encryptor()
    encryptor.authenticate_additional_data(protected_b64)

    ciphertext = encryptor.update(plaintext) + encryptor.finalize()

    return '.'.join([
        protected_b64.decode(),
        '',  # encrypted_key (empty for "dir")
        base64url_encode(iv).decode(),
        base64url_encode(ciphertext).decode(),
        base64url_encode(encryptor.tag).decode(),
    ])


def sign_request(encrypted_payload, signing_key, client_id):
    header = {
        'alg': 'HS256',
        'kid': 'HMAC',
        'clientid': client_id
    }

    header_b64 = base64url_encode(
        json.dumps(header, separators=(',', ':')).encode()
    )
    payload_64 = base64url_encode(encrypted_payload.encode())

    message = header_b64 + b"." + payload_64
    signature = hmac.new(signing_key.encode(), message, hashlib.sha256).digest()

    return '.'.join([
        header_b64.decode(),
        payload_64.decode(),
        base64url_encode(signature).decode()
    ])


def verify_response_signature(jws_response, signing_key):
    header_b64, payload, sig_b64 = jws_response.split('.')

    message = f'{header_b64}.{payload}'.encode()
    expected = hmac.new(signing_key.encode(), message, hashlib.sha256).digest()
    provided = base64url_decode(sig_b64)

    if not hmac.compare_digest(expected, provided):
        raise ValueError("Invalid Signature")

    return base64url_decode(payload).decode()


def decrypt_response(jwe_token, encryption_key):
    protected_b64, _, iv_b64, ciphertext_b64, tag_b64 = jwe_token.split(".")

    cipher = Cipher(
        algorithms.AES(encryption_key.encode()),
        modes.GCM(
            base64url_decode(iv_b64),
            base64url_decode(tag_b64)
        ),
        backend=default_backend()
    )

    decryptor = cipher.decryptor()
    decryptor.authenticate_additional_data(protected_b64.encode())

    plaintext = decryptor.update(
        base64url_decode(ciphertext_b64)
    ) + decryptor.finalize()

    return json.loads(plaintext.decode())


def billdesk_request(json_payload, key_id, encryption_key, signing_key, client_id):
    try:
        encrypted_payload = encrypt_request(json_payload, encryption_key, key_id, client_id)
        return sign_request(encrypted_payload, signing_key, client_id)
    except (ValueError, AttributeError, TypeError):
        return False


def billdesk_response(response, encryption_key, signing_key):
    try:
        verified_response = verify_response_signature(response, signing_key)
        return decrypt_response(verified_response, encryption_key)
    except (ValueError, AttributeError, TypeError):
        return False
