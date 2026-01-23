# Part of Odoo. See LICENSE file for full copyright and licensing details.

import binascii
import hashlib

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding as crypto_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def encrypt_ccavenue_data(plain_text, working_key):
    """Encrypt data for CCAvenue using their specific method."""
    try:
        md5_key = hashlib.md5(working_key.encode('utf-8')).digest()
        iv = binascii.unhexlify('000102030405060708090a0b0c0d0e0f')

        padder = crypto_padding.PKCS7(128).padder()
        padded_data = padder.update(plain_text.encode('utf-8')) + padder.finalize()
        # Encrypt
        cipher = Cipher(
            algorithms.AES(md5_key), modes.CBC(iv), backend=default_backend()
        )
        encryptor = cipher.encryptor()
        encrypted = encryptor.update(padded_data) + encryptor.finalize()
        return encrypted.hex()
    except AttributeError:
        raise ValueError('CCAvenue encryption failed')


def decrypt_ccavenue_data(encrypted_hex, working_key):
    """Decrypt data from CCAvenue using their specific method."""
    try:
        md5_key = hashlib.md5(working_key.encode('utf-8')).digest()
        iv = binascii.unhexlify('000102030405060708090a0b0c0d0e0f')
        encrypted_data = binascii.unhexlify(encrypted_hex)
        cipher = Cipher(
            algorithms.AES(md5_key), modes.CBC(iv), backend=default_backend()
        )
        decryptor = cipher.decryptor()
        decrypted_padded = decryptor.update(encrypted_data) + decryptor.finalize()

        unpadder = crypto_padding.PKCS7(128).unpadder()
        decrypted = unpadder.update(decrypted_padded) + unpadder.finalize()
        return decrypted.decode('utf-8')
    except (binascii.Error, ValueError):
        raise ValueError('CCAvenue decryption failed')


def prepare_ccavenue_query_string(form_data):
    """Convert form data to CCAvenue query string format."""
    query_parts = []
    for key, value in form_data.items():
        if value:  # Only include non-empty values
            query_parts.append(f'{key}={value}')

    # Join with & but don't add trailing &
    return '&'.join(query_parts)


def parse_ccavenue_response(response_string):
    """Parse CCAvenue response string into dictionary."""
    response_dict = {}
    if response_string:
        pairs = response_string.strip().split('&')
        for pair in pairs:
            if '=' in pair:
                key, value = pair.split('=', 1)
                response_dict[key] = value
    return response_dict
