"""密碼雜湊工具。SALT_ROUNDS 固定為 10，不因效能考量調低（見 CLAUDE.md 硬性規則）。"""

import bcrypt

SALT_ROUNDS = 10


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt(rounds=SALT_ROUNDS)).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
