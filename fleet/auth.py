import hashlib
import hmac
import secrets
import time

from fleet.db import connect, now


def hash_password(password):
    salt = secrets.token_hex(16)
    result = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1, dklen=64)
    return salt + ":" + result.hex()


def verify_password(password, encoded):
    salt, expected = encoded.split(":")
    result = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1, dklen=64)
    return hmac.compare_digest(result.hex(), expected)


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def configured():
    with connect() as con:
        return bool(con.execute("SELECT 1 FROM users").fetchone())


def authenticated(token):
    if not token:
        return False
    with connect() as con:
        return bool(con.execute("SELECT 1 FROM sessions WHERE token_hash=? AND expires_at>?", (token_hash(token), int(time.time()))).fetchone())


def create_user(password):
    if len(password) < 12 or len(password) > 256:
        raise ValueError("Zvolte heslo dlouhé alespoň 12 a nejvýše 256 znaků.")
    with connect() as con, con:
        con.execute("INSERT INTO users VALUES(1,?,?)", (hash_password(password), now()))


def login(password, client):
    timestamp = int(time.time())
    with connect() as con, con:
        attempts = con.execute("SELECT * FROM login_attempts WHERE client=?", (client,)).fetchone()
        if attempts and timestamp - attempts["window_start"] < 900 and attempts["attempts"] >= 5:
            return None, True
        user = con.execute("SELECT password_hash FROM users WHERE id=1").fetchone()
        if not user or not verify_password(password, user[0]):
            if not attempts or timestamp - attempts["window_start"] >= 900:
                con.execute("INSERT OR REPLACE INTO login_attempts VALUES(?,1,?)", (client, timestamp))
            else:
                con.execute("UPDATE login_attempts SET attempts=attempts+1 WHERE client=?", (client,))
            return None, False
        con.execute("DELETE FROM login_attempts WHERE client=?", (client,))
        token = secrets.token_urlsafe(32)
        con.execute("DELETE FROM sessions WHERE expires_at<=?", (timestamp,))
        con.execute("INSERT INTO sessions VALUES(?,?)", (token_hash(token), timestamp + 12 * 3600))
    return token, False
