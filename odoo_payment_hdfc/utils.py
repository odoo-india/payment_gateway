# Part of Odoo. See LICENSE file for full copyright and licensing details.

import binascii
import re

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def generate_hdfc_refund_string(payload, hash_sequence):
    """
    Generate SHA512 hash for PayU transaction request.

    hashSequence = "merchant_id|new_order_no|original_order_no|original_txn_ref_no|original_cust_ref_no|remarks|refund_amount|currency|payment_type|txn_type|additional_1..10",
    """
    hash_keys = hash_sequence.split("|")
    hash_string = '|'.join(str(payload.get(key, '')) for key in hash_keys)
    return encrypt_request(hash_string, payload.get('merchant_key'))


def encrypt_request(plain_text, merchant_key_hex):
    """
    Encrypts refund request payload exactly as per HDFC spec:
    - AES-128
    - ECB mode
    - PKCS7 padding
    - HEX output (uppercase)
    """
    key_bytes = bytes.fromhex(merchant_key_hex)
    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(plain_text.encode("utf-8")) + padder.finalize()
    cipher = Cipher(algorithms.AES(key_bytes), modes.ECB())
    encryptor = cipher.encryptor()
    encrypted_bytes = encryptor.update(padded_data) + encryptor.finalize()
    encrypted_hex = binascii.hexlify(encrypted_bytes).decode("utf-8").upper()
    return encrypted_hex


def decrypt_response(merchant_response, merchant_key):
    """ Decrypts the response using AES and PKCS7 unpadding. """
    meRes_hex = re.sub(r'[^0-9A-Fa-f]', '', merchant_response)

    if len(meRes_hex) % 2 != 0:
        raise ValueError('Invalid hex length')

    encrypted_bytes = bytes.fromhex(meRes_hex)
    key_bytes = bytes.fromhex(merchant_key)
    cipher = Cipher(algorithms.AES(key_bytes), modes.ECB())
    decryptor = cipher.decryptor()
    decrypted = decryptor.update(encrypted_bytes) + decryptor.finalize()
    try:
        decrypted = pkcs7_unpad(decrypted)
    except ValueError:
        raise ValueError("PKCS7 unpadding failed (invalid key or corrupted payload)")

    decrypted_text = decrypted.decode('utf-8')

    if not decrypted_text.strip():
        raise ValueError("Empty decrypted response")

    return decrypted_text


def pkcs7_unpad(data: bytes):
    """ Unpads the input data using PKCS7 padding scheme. """
    padder = padding.PKCS7(128).unpadder()
    unpadded_data = padder.update(data) + padder.finalize()
    return unpadded_data
