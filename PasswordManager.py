import zlib

class PasswordManager:
    def encrypt_password(self, password):
        """Encriptar una contraseña usando CRC32"""
        encrypted = zlib.crc32(password.encode("utf-8"))
        return str(encrypted)