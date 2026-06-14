import os
import base64
import hashlib
import hmac
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP, AES
from Crypto.Random import get_random_bytes


def generate_rsa_keypair():
    key = RSA.generate(2048)
    private_key = key.export_key().decode('utf-8')
    public_key = key.publickey().export_key().decode('utf-8')
    return public_key, private_key


def encrypt_file_hybrid(file_data, public_key_pem):
    aes_key = get_random_bytes(32)
    nonce = get_random_bytes(12)
    
    cipher_aes = AES.new(aes_key, AES.MODE_GCM, nonce=nonce)
    encrypted_data, tag = cipher_aes.encrypt_and_digest(file_data)
    
    public_key = RSA.import_key(public_key_pem)
    cipher_rsa = PKCS1_OAEP.new(public_key)
    encrypted_aes_key = cipher_rsa.encrypt(aes_key)
    
    result = base64.b64encode(encrypted_aes_key).decode('utf-8') + '|||' + \
             base64.b64encode(nonce).decode('utf-8') + '|||' + \
             base64.b64encode(tag).decode('utf-8') + '|||' + \
             base64.b64encode(encrypted_data).decode('utf-8')
    
    return result.encode('utf-8')


def decrypt_file_hybrid(encrypted_content, private_key_pem):
    content = encrypted_content.decode('utf-8')
    parts = content.split('|||')
    
    if len(parts) == 3:
        encrypted_aes_key = base64.b64decode(parts[0])
        iv = base64.b64decode(parts[1])
        encrypted_data = base64.b64decode(parts[2])
        
        private_key = RSA.import_key(private_key_pem)
        cipher_rsa = PKCS1_OAEP.new(private_key)
        aes_key = cipher_rsa.decrypt(encrypted_aes_key)
        
        cipher_aes = AES.new(aes_key, AES.MODE_CBC, iv)
        decrypted_padded = cipher_aes.decrypt(encrypted_data)
        
        padding_length = decrypted_padded[-1]
        decrypted_data = decrypted_padded[:-padding_length]
        
        return decrypted_data
    
    if len(parts) != 4:
        raise ValueError("Invalid encrypted file format")
    
    encrypted_aes_key = base64.b64decode(parts[0])
    nonce = base64.b64decode(parts[1])
    tag = base64.b64decode(parts[2])
    encrypted_data = base64.b64decode(parts[3])
    
    private_key = RSA.import_key(private_key_pem)
    cipher_rsa = PKCS1_OAEP.new(private_key)
    aes_key = cipher_rsa.decrypt(encrypted_aes_key)
    
    cipher_aes = AES.new(aes_key, AES.MODE_GCM, nonce=nonce)
    decrypted_data = cipher_aes.decrypt_and_verify(encrypted_data, tag)
    
    return decrypted_data


def encrypt_message(message, public_key_pem):
    public_key = RSA.import_key(public_key_pem)
    cipher = PKCS1_OAEP.new(public_key)
    
    message_bytes = message.encode('utf-8')
    max_chunk_size = 190
    
    encrypted_chunks = []
    for i in range(0, len(message_bytes), max_chunk_size):
        chunk = message_bytes[i:i+max_chunk_size]
        encrypted_chunk = cipher.encrypt(chunk)
        encrypted_chunks.append(base64.b64encode(encrypted_chunk).decode('utf-8'))
    
    return '|||'.join(encrypted_chunks)


def decrypt_message(encrypted_message, private_key_pem):
    private_key = RSA.import_key(private_key_pem)
    cipher = PKCS1_OAEP.new(private_key)
    
    chunks = encrypted_message.split('|||')
    decrypted_chunks = []
    
    for chunk in chunks:
        encrypted_chunk = base64.b64decode(chunk)
        decrypted_chunk = cipher.decrypt(encrypted_chunk)
        decrypted_chunks.append(decrypted_chunk.decode('utf-8'))
    
    return ''.join(decrypted_chunks)
