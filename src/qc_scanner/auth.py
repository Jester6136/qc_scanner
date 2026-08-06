"""Xác thực API key kiểu OpenAI: `Authorization: Bearer <key>`.

Nguyên tắc: **không có đường gọi ẩn danh**. Muốn chạy mở thì phải khai báo tường
minh `QC_SCANNER_AUTH=off` — quên đặt key là server không lên, chứ không phải
quên đặt key là hệ thống mở toang trong im lặng. Hai kiểu hỏng đó rất khác nhau:
một cái làm bạn khó chịu 30 giây, cái kia phơi giấy tờ tuỳ thân của khách ra cả
LAN mà không ai biết.

Cấu hình::

    QC_SCANNER_API_KEYS="app-web:qcs-a1b2...,batch:qcs-d4e5..."

Mỗi key gắn một **tên client**, để:

* thu hồi được từng client mà không đụng tới client khác;
* log biết ai đang gọi — lộ key thì còn truy được nguồn.

Xoay key không cần dừng service: thêm key mới vào danh sách, chuyển client sang,
rồi bỏ key cũ. Có hai key cùng sống là chuyện bình thường trong lúc chuyển.

⚠️ **Giới hạn thật, phải nói rõ**: key đi qua HTTP thuần là gửi mật khẩu dạng chữ
rõ. Nó chặn được người gọi nhầm và người dò cổng trong LAN, nhưng KHÔNG chặn được
người nghe lén trên chính đường truyền đó — bắt được gói tin là dùng lại key vô
thời hạn. Muốn kín thật thì đặt reverse proxy có TLS trước container.
"""

import hmac
import os
import secrets

#: Tiền tố key, học từ `sk-` của OpenAI. Không phải để bảo mật — để **nhận ra**:
#: một chuỗi `qcs-…` lọt vào commit hay log thì người đọc biết ngay đó là bí mật
#: của hệ thống nào mà đi thu hồi.
KEY_PREFIX = "qcs-"

ENV_KEYS = "QC_SCANNER_API_KEYS"
ENV_MODE = "QC_SCANNER_AUTH"

#: Tên client dùng khi key khai báo trống phần tên.
DEFAULT_CLIENT = "client"


class AuthConfigError(RuntimeError):
    """Cấu hình xác thực sai → **chết lúc khởi động**, không chạy tiếp.

    Không có mức "cảnh báo rồi chạy tạm": một service xác thực hỏng mà vẫn phục vụ
    là kiểu hỏng tệ nhất, vì nó trông y hệt service đang chạy đúng.
    """


def generate_key() -> str:
    """Sinh một key mới. 32 byte ngẫu nhiên — đủ để không ai dò nổi."""
    return KEY_PREFIX + secrets.token_hex(32)


def main(argv=None):
    """`qc-scanner-apikey` — sinh key và in ra dòng cấu hình dán được ngay."""
    import argparse

    ap = argparse.ArgumentParser(description=main.__doc__.splitlines()[0])
    ap.add_argument("name", nargs="?", default="app-web", help="Tên client.")
    args = ap.parse_args(argv)

    print(f'{ENV_KEYS}="{args.name}:{generate_key()}"')
    return 0


def parse_keys(raw: str) -> dict:
    """`"app-web:qcs-a1,batch:qcs-b2"` → `{"qcs-a1": "app-web", ...}`.

    Khoá theo **key**, không theo tên client: lúc kiểm ta có key trong tay và cần
    tra ngược ra tên. Tên trùng nhau thì không sao; key trùng nhau thì có, vì khi
    ấy log sẽ quy sai client — nên chặn luôn.
    """
    keys = {}
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        name, _, value = chunk.rpartition(":")
        name, value = name.strip() or DEFAULT_CLIENT, value.strip()
        if not value:
            raise AuthConfigError(f"{ENV_KEYS}: mục {chunk!r} không có key")
        if len(value) < 16:
            raise AuthConfigError(
                f"{ENV_KEYS}: key của {name!r} quá ngắn (<16 ký tự) — "
                f"sinh key bằng `qc-scanner-apikey`"
            )
        if value in keys:
            raise AuthConfigError(f"{ENV_KEYS}: key trùng nhau ở {keys[value]!r} và {name!r}")
        keys[value] = name
    return keys


def load(env=None) -> dict:
    """Đọc cấu hình xác thực từ môi trường. Ném `AuthConfigError` nếu không hợp lệ."""
    env = os.environ if env is None else env
    mode = (env.get(ENV_MODE) or "").strip().lower()
    raw = (env.get(ENV_KEYS) or "").strip()

    if mode == "off":
        # Có key mà lại tắt xác thực gần như luôn là nhầm lẫn, và nhầm theo hướng
        # nguy hiểm — người đặt key tưởng mình đã khoá cửa.
        if raw:
            raise AuthConfigError(
                f"{ENV_MODE}=off nhưng {ENV_KEYS} vẫn có key. "
                f"Bỏ một trong hai — đang bật hay tắt là chuyện phải rõ ràng."
            )
        return {"enabled": False, "keys": {}}

    if not raw:
        raise AuthConfigError(
            f"chưa đặt {ENV_KEYS} — server không khởi động.\n"
            f"  Sinh key:  qc-scanner-apikey\n"
            f'  Rồi đặt:   {ENV_KEYS}="app-web:<key>"\n'
            f"  Chạy mở (KHÔNG khuyến nghị, ai trong LAN cũng gọi được): {ENV_MODE}=off"
        )
    return {"enabled": True, "keys": parse_keys(raw)}


def client_for(header: str, keys: dict):
    """Tên client ứng với header `Authorization`, hoặc `None` nếu không hợp lệ.

    So sánh bằng `hmac.compare_digest` trên **mọi** key, không thoát sớm khi khớp:
    so sánh chuỗi thường thoát ở byte đầu khác nhau, nên thời gian phản hồi rò rỉ
    thông tin về việc đoán đúng được bao nhiêu ký tự đầu.
    """
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None

    token = token.strip()
    found = None
    for known, name in keys.items():
        if hmac.compare_digest(token, known):
            found = name
    return found
