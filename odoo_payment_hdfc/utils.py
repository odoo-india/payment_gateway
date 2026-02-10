# Part of Odoo. See LICENSE file for full copyright and licensing details.

import binascii
import re

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def generate_hdfc_refund_string(payload, hash_sequence):
    """
    Generate and encrypt the refund hash string for an HDFC refund request.

    :param dict payload: Refund request data used to build the hash string.
    :param str hash_sequence: Pipe-separated sequence of keys defining the hash order.
    :return: Encrypted hash string to be sent in the refund request.
    :rtype: str

    Sample hash_sequence = "merchant_id|new_order_no|original_order_no|original_txn_ref_no|original_cust_ref_no|remarks|refund_amount|currency|payment_type|txn_type|additional_1..10",
    """
    hash_keys = hash_sequence.split('|')
    hash_string = '|'.join(str(payload.get(key, '')) for key in hash_keys)
    return encrypt_request(hash_string, payload.get('merchant_key'))


def encrypt_request(plain_text, merchant_key_hex):
    """
    Encrypt the refund request payload as per HDFC specification.

    :param str plain_text: The plain text payload to encrypt.
    :param str merchant_key_hex: The HDFC merchant key in HEX format.
    :return: The encrypted payload as an uppercase HEX string.
    :rtype: str
    """
    key_bytes = bytes.fromhex(merchant_key_hex)
    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(plain_text.encode('utf-8')) + padder.finalize()
    cipher = Cipher(algorithms.AES(key_bytes), modes.ECB())
    encryptor = cipher.encryptor()
    encrypted_bytes = encryptor.update(padded_data) + encryptor.finalize()
    encrypted_hex = binascii.hexlify(encrypted_bytes).decode('utf-8').upper()
    return encrypted_hex


def decrypt_response(merchant_response, merchant_key):
    """
    Decrypt the HDFC encrypted response payload.

    :param str merchant_response: Encrypted response string in HEX format.
    :param str merchant_key: The HDFC merchant key in HEX format.
    :return: Decrypted response as a UTF-8 string.
    :rtype: str
    :raises ValueError: If the payload is invalid, decryption fails, or the result is empty.
    """
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
        raise ValueError('PKCS7 unpadding failed (invalid key or corrupted payload)')

    decrypted_text = decrypted.decode('utf-8')

    if not decrypted_text.strip():
        raise ValueError('Empty decrypted response')

    return decrypted_text


def pkcs7_unpad(data):
    """
    Remove PKCS7 padding from decrypted data.

    :param bytes data: Decrypted data with PKCS7 padding.
    :return: Unpadded raw bytes.
    :rtype: bytes
    :raises ValueError: If the padding is invalid.
    """
    padder = padding.PKCS7(128).unpadder()
    unpadded_data = padder.update(data) + padder.finalize()
    return unpadded_data


def generate_qr_code(hdfc_provider, txn_ref, txn_note, amount):
    """
    Build the UPI QR payload string for HDFC payments.

    :param recordset hdfc_provider: HDFC payment provider configuration record.
    :param str txn_ref: Unique transaction reference.
    :param str txn_note: Optional transaction note/description.
    :param float amount: Amount to be paid.
    :return: UPI QR payload string.
    :rtype: str
    """
    version = '01'
    mode = '03' if hdfc_provider.state == 'test' else '15'
    payee_name = hdfc_provider.hdfc_merchant_name
    payee_vpa = hdfc_provider.hdfc_merchant_vpa
    merchant_category = '6012'
    currency = 'INR'
    amount = str(amount)

    hdfc_qr_string = (
        'upi://pay?'
        f'ver={version}&'
        f'mode={mode}&'
        f'tr={txn_ref}&'
        f'tn={txn_note}&'
        f'pn={payee_name}&'
        f'pa={payee_vpa}&'
        f'mc={merchant_category}&'
        f'am={amount}&'
        f'cu={currency}&'
        'qrMedium=06'
    )

    return hdfc_qr_string
