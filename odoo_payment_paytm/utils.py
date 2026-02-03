# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import hashlib
import random
import string

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding as crypto_padding
from cryptography.hazmat.primitives.ciphers import algorithms, Cipher, modes


IV = b'@@@@&&&&####$$$$'
BLOCK_SIZE = 16


def pad(data):
    """Pad data to BLOCK_SIZE using PKCS7 padding."""
    if isinstance(data, str):
        data = data.encode('utf-8')
    padder = crypto_padding.PKCS7(BLOCK_SIZE * 8).padder()
    return padder.update(data) + padder.finalize()


def unpad(data):
    """Remove PKCS7 padding from data."""
    unpadder = crypto_padding.PKCS7(BLOCK_SIZE * 8).unpadder()
    unpadded_data = unpadder.update(data) + unpadder.finalize()
    return unpadded_data.decode('utf-8')


def encrypt(input_data, key):
    """Encrypt data using AES-CBC."""
    padded_data = pad(input_data)
    key_bytes = key.encode('utf-8')
    cipher = Cipher(algorithms.AES(key_bytes), modes.CBC(IV), backend=default_backend())
    encryptor = cipher.encryptor()
    encrypted_data = encryptor.update(padded_data) + encryptor.finalize()
    return base64.b64encode(encrypted_data).decode('utf-8')


def decrypt(encrypted_data, key):
    """Decrypt data using AES-CBC."""
    encrypted_bytes = base64.b64decode(encrypted_data)
    key_bytes = key.encode('utf-8')
    cipher = Cipher(algorithms.AES(key_bytes), modes.CBC(IV), backend=default_backend())
    decryptor = cipher.decryptor()
    decrypted_data = decryptor.update(encrypted_bytes) + decryptor.finalize()
    return unpad(decrypted_data)


def generateSignature(params, key):
    if type(params) is not dict and type(params) is not str:
        raise Exception('string or dict expected, ' + str(type(params)) + ' given')
    if type(params) is dict:
        params = getStringByParams(params)
    return generateSignatureByString(params, key)


def verifySignature(params, key, checksum):
    try:
        if type(params) is not dict and type(params) is not str:
            raise Exception('string or dict expected, ' + str(type(params)) + ' given')
        if 'CHECKSUMHASH' in params:
            del params['CHECKSUMHASH']

        if type(params) is dict:
            params = getStringByParams(params)
        return verifySignatureByString(params, key, checksum)
    except (ValueError, AttributeError, TypeError):
        return False


def generateSignatureByString(params, key):
    salt = generateRandomString(4)
    return calculateChecksum(params, key, salt)


def verifySignatureByString(params, key, checksum):
    paytm_hash = decrypt(checksum, key)
    salt = paytm_hash[-4:]
    return paytm_hash == calculateHash(params, salt)


def generateRandomString(length):
    chars = string.ascii_uppercase + string.digits + string.ascii_lowercase
    return ''.join(random.choice(chars) for _ in range(length))


def getStringByParams(params):
    params_string = []
    for key in sorted(params.keys()):
        value = (
            params[key]
            if params[key] is not None and params[key].lower() != 'null'
            else ''
        )
        params_string.append(str(value))
    return '|'.join(params_string)


def calculateHash(params, salt):
    finalString = '%s|%s' % (params, salt)
    hasher = hashlib.sha256(finalString.encode())
    hashString = hasher.hexdigest() + salt
    return hashString


def calculateChecksum(params, key, salt):
    hashString = calculateHash(params, salt)
    return encrypt(hashString, key)
