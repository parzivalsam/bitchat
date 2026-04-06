import os
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from PyQt6.QtCore import QObject
import base64

class CryptoManager(QObject):
    def __init__(self):
        super().__init__()
        self.private_key = None
        self.public_key_bytes = None
        self._load_or_generate_keys()

    def _load_or_generate_keys(self):
        key_file = "private_key.pem"
        if os.path.exists(key_file):
            with open(key_file, "rb") as key_in:
                self.private_key = serialization.load_pem_private_key(
                    key_in.read(),
                    password=None,
                )
        else:
            self.private_key = ec.generate_private_key(ec.SECP256R1())
            with open(key_file, "wb") as key_out:
                key_out.write(self.private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption()
                ))

        pub_key = self.private_key.public_key()
        self.public_key_bytes = pub_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

    def get_public_key_b64(self):
        return base64.b64encode(self.public_key_bytes).decode('utf-8')

    def compute_shared_secret(self, peer_pub_key_b64):
        try:
            peer_pub_key_bytes = base64.b64decode(peer_pub_key_b64)
            peer_public_key = serialization.load_pem_public_key(peer_pub_key_bytes)
            shared_key = self.private_key.exchange(ec.ECDH(), peer_public_key)
            
            # Derive AES-GCM key from shared key
            derived_key = HKDF(
                algorithm=hashes.SHA256(),
                length=32,
                salt=None,
                info=b'ble_proximity_chat_handshake',
            ).derive(shared_key)
            
            return base64.b64encode(derived_key).decode('utf-8')
        except Exception as e:
            print(f"Error computing shared secret: {e}")
            return None

    def encrypt_message(self, plaintext, shared_secret_b64):
        if not shared_secret_b64 or not plaintext:
            return plaintext # fallback if no encryption setup
        try:
            aesgcm = AESGCM(base64.b64decode(shared_secret_b64))
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
            # Prepend nonce to ciphertext
            result = nonce + ciphertext
            return base64.b64encode(result).decode('utf-8')
        except Exception as e:
            print(f"Encryption error: {e}")
            return plaintext

    def decrypt_message(self, ciphertext_b64, shared_secret_b64):
        if not shared_secret_b64 or not ciphertext_b64:
            return ciphertext_b64
        try:
            data = base64.b64decode(ciphertext_b64)
            nonce = data[:12]
            ciphertext = data[12:]
            aesgcm = AESGCM(base64.b64decode(shared_secret_b64))
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            return plaintext.decode('utf-8')
        except Exception as e:
            print(f"Decryption error: {e}")
            return ciphertext_b64 # original if failed or not encrypted
