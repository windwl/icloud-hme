#!/usr/bin/env python3
"""回归测试 — 覆盖核心流程，发现重构中的破坏性变更。"""

import sys
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))


def test_parse_cookie_header_string():
    """Cookie Header String 格式解析"""
    from account_manager import AccountManager
    mgr = AccountManager()
    
    raw = "X_APPLE_WEB_KB=abc123; SESSION_TOKEN=xyz789"
    cookies = mgr.parse_cookie_input(raw)
    assert len(cookies) == 2
    assert cookies["X_APPLE_WEB_KB"] == "abc123"
    assert cookies["SESSION_TOKEN"] == "xyz789"
    print("  PASS test_parse_cookie_header_string")


def test_parse_cookie_json():
    """JSON 格式 Cookie 解析"""
    from account_manager import AccountManager
    mgr = AccountManager()
    
    raw = '{"X_APPLE_WEB_KB":"abc123","SESSION_TOKEN":"xyz789"}'
    cookies = mgr.parse_cookie_input(raw)
    assert len(cookies) == 2
    assert cookies["X_APPLE_WEB_KB"] == "abc123"
    print("  PASS test_parse_cookie_json")


def test_parse_cookie_editor_export():
    """支持 Cookie Editor 账号导出格式"""
    from account_manager import AccountManager

    raw = json.dumps({"accounts": [{"cookies": [
        {"domain": ".icloud.com.cn", "name": "TOKEN", "value": "abc"},
        {"domain": ".icloud.com.cn", "name": "SESSION", "value": "xyz"},
    ]}]})
    cookies = AccountManager.parse_cookie_input(raw)
    assert cookies == {"TOKEN": "abc", "SESSION": "xyz"}
    print("  PASS test_parse_cookie_editor_export")


def test_parse_empty_input():
    """空输入应抛出 ValueError"""
    from account_manager import AccountManager
    mgr = AccountManager()
    
    try:
        mgr.parse_cookie_input("")
        assert False, "应该抛出 ValueError"
    except ValueError:
        pass
    print("  PASS test_parse_empty_input")


def test_derive_icloud_email_primary():
    """dsInfo 有 primaryEmail 时直接使用"""
    from account_manager import AccountManager
    info = {"appleId": "user@qq.com", "primaryEmail": "user@icloud.com"}
    result = AccountManager._derive_icloud_email(info)
    assert result == "user@icloud.com"
    print("  PASS test_derive_icloud_email_primary")


def test_derive_icloud_email_appleid_is_icloud():
    """appleId 本身是 @icloud.com"""
    from account_manager import AccountManager
    info = {"appleId": "user@icloud.com", "primaryEmail": ""}
    result = AccountManager._derive_icloud_email(info)
    assert result == "user@icloud.com"
    print("  PASS test_derive_icloud_email_appleid_is_icloud")


def test_derive_icloud_email_third_party():
    """第三方 Apple ID 需要显式设置 iCloud Mail 地址"""
    from account_manager import AccountManager
    info = {"appleId": "test@gmail.com", "primaryEmail": ""}
    result = AccountManager._derive_icloud_email(info)
    assert result == ""
    print("  PASS test_derive_icloud_email_third_party")


def test_mail_cache_basic():
    """邮件缓存基本读写"""
    from mail_cache import MailCache
    cache = MailCache()
    cache.clear_account("test_acc")

    emails = [
        {"id": "1", "from": "a@b.com", "to": "x@icloud.com", "subject": "Hello", "date": "2025-01-01T00:00:00"},
        {"id": "2", "from": "c@d.com", "to": "y@icloud.com", "subject": "World", "date": "2025-01-02T00:00:00"},
        {"id": "1", "from": "a@b.com", "to": "x@icloud.com", "subject": "Hello Duplicate", "date": "2025-01-03T00:00:00"},
        {"id": "1", "mailbox": "Junk", "from": "spam@b.com", "to": "x@icloud.com", "subject": "Junk", "date": "2025-01-04T00:00:00"},
    ]

    cache.set_inbox("test_acc", emails)
    cached = cache.get_inbox("test_acc")

    # 同一目录的重复 UID 去重，不同目录的相同 UID 分别保留。
    assert len(cached) == 3, f"期望 3 封，实际 {len(cached)}"
    
    # 清理
    cache.clear_account("test_acc")
    assert len(cache.get_inbox("test_acc")) == 0
    print("  PASS test_mail_cache_basic")


def test_mail_reads_inbox_and_junk():
    """默认合并收件箱与垃圾邮件，并保留邮件目录。"""
    from icloud_mail import ICloudMail

    class Connection:
        state = "AUTH"

        def __init__(self):
            self.selected = []

        def select(self, mailbox, readonly=True):
            self.selected.append(mailbox)
            self.state = "SELECTED"
            return "OK", [b"1"]

    mail = ICloudMail("user@icloud.com", "password")
    mail._conn = Connection()

    def search(criteria, limit, days, mailbox):
        date = "2026-07-29T12:00:00" if mailbox == "INBOX" else "2026-07-29T13:00:00"
        return [{"id": "1", "mailbox": mailbox, "date": date}]

    mail._search_and_fetch = search
    messages = mail.check_inbox(limit=10, days=7)

    assert mail._conn.selected == ["INBOX", "Junk"]
    assert [message["mailbox"] for message in messages] == ["Junk", "INBOX"]

    mail._fetch_full_message = lambda msg_id: {"body": "code"}
    mail._fetch_headers_uid = lambda msg_id, mailbox="INBOX": {
        "id": msg_id.decode(), "mailbox": mailbox
    }
    full = mail.fetch_full(b"1", mailbox="Junk")
    assert full["body"] == "code"
    assert full["mailbox"] == "Junk"
    print("  PASS test_mail_reads_inbox_and_junk")


def test_strip_html():
    """HTML 标签剥离"""
    from icloud_mail import _strip_html
    
    html = "<html><body><p>Hello</p><br><div>World</div></body></html>"
    text = _strip_html(html)
    assert "Hello" in text
    assert "World" in text
    assert "<p>" not in text
    assert "<html>" not in text
    print("  PASS test_strip_html")


def test_strip_html_with_link():
    """HTML 链接保留文字"""
    from icloud_mail import _strip_html
    
    html = '<a href="https://example.com">Click here</a>'
    text = _strip_html(html)
    assert "Click here" in text
    assert "example.com" in text
    print("  PASS test_strip_html_with_link")


def test_chrome_cookie_path_scans_profiles():
    """Chrome 使用 Profile 1 时也能定位 Cookie 数据库"""
    import sqlite3
    import tempfile
    import icloud_hme

    old_local_appdata = os.environ.get("LOCALAPPDATA")
    original_key = icloud_hme._get_chrome_key
    original_decrypt = icloud_hme._decrypt_chrome_value
    original_copy = icloud_hme.shutil.copy2
    try:
        with tempfile.TemporaryDirectory() as tmp:
            cookie = Path(tmp) / "Google" / "Chrome" / "User Data" / "Profile 1" / "Network" / "Cookies"
            cookie.parent.mkdir(parents=True)
            conn = sqlite3.connect(cookie)
            conn.execute("CREATE TABLE cookies (host_key TEXT, name TEXT, encrypted_value BLOB)")
            conn.execute(
                "INSERT INTO cookies VALUES (?, ?, ?)",
                (".icloud.com", "TOKEN", b"encrypted"),
            )
            conn.commit()
            conn.close()
            os.environ["LOCALAPPDATA"] = tmp
            assert Path(icloud_hme._get_chrome_cookie_path()) == cookie
            icloud_hme._get_chrome_key = lambda: b"key"
            icloud_hme._decrypt_chrome_value = lambda value, key: "decrypted"
            icloud_hme.shutil.copy2 = lambda *args, **kwargs: (_ for _ in ()).throw(
                PermissionError("Chrome database is locked")
            )
            assert icloud_hme.extract_chrome_cookies() == {"TOKEN": "decrypted"}
    finally:
        icloud_hme._get_chrome_key = original_key
        icloud_hme._decrypt_chrome_value = original_decrypt
        icloud_hme.shutil.copy2 = original_copy
        if old_local_appdata is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = old_local_appdata
    print("  PASS test_chrome_cookie_path_scans_profiles")


def test_icloud_hme_421_message():
    """421 不回显响应中的会话令牌"""
    from icloud_hme import ICloudHME

    class Response:
        ok = False
        status_code = 421
        text = '{"trustTokens":["SECRET"]}'

    class Session:
        def request(self, *args, **kwargs):
            return Response()

    client = ICloudHME({}, verbose=False)
    client.session = Session()
    try:
        client._request("POST", "https://setup.icloud.com/setup/ws/1/validate", max_attempts=1)
        assert False, "应该抛出 RuntimeError"
    except RuntimeError as exc:
        assert "会话已失效" in str(exc)
        assert "SECRET" not in str(exc)
    print("  PASS test_icloud_hme_421_message")


def test_icloud_hme_account_info():
    """ICloudHME 客户端有 get_account_info 方法"""
    from icloud_hme import ICloudHME
    client = ICloudHME({}, verbose=False)
    assert hasattr(client, "get_account_info")
    # 未校验前应返回 None
    assert client.get_account_info() is None
    print("  PASS test_icloud_hme_account_info")


def test_update_cookies_preserves_account():
    """新 Cookie 校验成功后覆盖旧值并保留账号配置"""
    import tempfile
    import account_manager as module
    import icloud_hme

    original_path = module.ACCOUNTS_FILE
    original_client = icloud_hme.ICloudHME

    class Cookies:
        def __init__(self, values):
            self.values = values

        def get_dict(self):
            return dict(self.values)

    class Client:
        def __init__(self, cookies, host="icloud.com", verbose=False):
            self.input_cookies = cookies
            self.host = host
            self.session = type("Session", (), {
                "cookies": Cookies({**cookies, "REFRESHED": "yes"})
            })()

        def validate_session(self):
            if self.input_cookies.get("TOKEN") == "bad":
                raise RuntimeError("HTTP 421")
            return {}

        def get_account_info(self):
            return {"appleId": "owner@example.com", "primaryEmail": ""}

        def list_aliases(self):
            return [{"active": True}, {"active": False}]

    try:
        with tempfile.TemporaryDirectory() as tmp:
            module.ACCOUNTS_FILE = Path(tmp) / "accounts.json"
            icloud_hme.ICloudHME = Client
            manager = module.AccountManager()
            manager.accounts = {"acc_1": {
                "id": "acc_1",
                "name": "main",
                "real_email": "owner@example.com",
                "icloud_email": "mailbox@icloud.com",
                "app_password": "keep-me",
                "cookies": {"TOKEN": "old"},
                "host": "icloud.com",
                "status": "error",
            }}

            try:
                manager.update_cookies("acc_1", "TOKEN=bad")
                assert False, "过期 Cookie 应校验失败"
            except RuntimeError:
                pass
            assert manager.accounts["acc_1"]["cookies"] == {"TOKEN": "old"}

            updated = manager.update_cookies("acc_1", "TOKEN=new")
            assert updated["id"] == "acc_1"
            assert updated["cookies"] == {"TOKEN": "new", "REFRESHED": "yes"}
            assert updated["app_password"] == "keep-me"
            assert updated["icloud_email"] == "mailbox@icloud.com"
            assert updated["alias_total"] == 2
            assert updated["status"] == "active"
    finally:
        module.ACCOUNTS_FILE = original_path
        icloud_hme.ICloudHME = original_client
    print("  PASS test_update_cookies_preserves_account")


def test_alias_deactivate_and_delete():
    """停用与删除校验账号归属并更新统计"""
    import tempfile
    import account_manager as module
    from icloud_hme import ICloudHME

    api = ICloudHME({}, verbose=False)
    api._service_url = "https://example.invalid"
    api._resolve_service = lambda: None
    requests = []
    api._request = lambda method, url, json_data=None, **kwargs: (
        requests.append((method, url, json_data)) or {"success": True}
    )
    assert api.deactivate("alias_1") is True
    assert requests[-1][1].endswith("/v1/hme/deactivate")
    assert requests[-1][2] == {"anonymousId": "alias_1"}

    class Client:
        def __init__(self):
            self.deactivated = []
            self.deleted = []

        def list_aliases(self):
            return [
                {"anonymousId": "alias_1", "active": True},
                {"anonymousId": "alias_2", "active": False},
            ]

        def deactivate(self, anonymous_id):
            self.deactivated.append(anonymous_id)

        def delete(self, anonymous_id):
            self.deleted.append(anonymous_id)

    original_path = module.ACCOUNTS_FILE
    try:
        with tempfile.TemporaryDirectory() as tmp:
            module.ACCOUNTS_FILE = Path(tmp) / "accounts.json"
            manager = module.AccountManager()
            manager.accounts = {"acc_1": {
                "id": "acc_1", "cookies": {},
                "alias_total": 2, "alias_active": 1,
            }}
            client = Client()
            manager.get_client = lambda *args, **kwargs: client

            deactivated = manager.deactivate_alias("acc_1", "alias_1")
            assert client.deactivated == ["alias_1"]
            assert deactivated["alias_total"] == 2
            assert deactivated["alias_active"] == 0

            deleted = manager.delete_alias("acc_1", "alias_1")
            assert client.deleted == ["alias_1"]
            assert deleted["alias_total"] == 1
            assert deleted["alias_active"] == 0
    finally:
        module.ACCOUNTS_FILE = original_path
    print("  PASS test_alias_deactivate_and_delete")


def test_scheduler_beijing_window_and_shared_web_core():
    """调度窗口使用北京时间，Web 复用统一核心"""
    from datetime import datetime, timezone
    import inspect
    import scheduler
    import web_ui

    utc_2300 = datetime(2026, 1, 1, 23, 0, tzinfo=timezone.utc)
    utc_1200 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert scheduler.beijing_now(utc_2300).hour == 7
    assert scheduler.is_active_window(utc_2300) is True
    assert scheduler.beijing_now(utc_1200).hour == 20
    assert scheduler.is_active_window(utc_1200) is False
    assert "run_scheduler" in inspect.getsource(web_ui._scheduler_loop)
    assert web_ui._scheduler_stop_event is not web_ui._shutdown_event
    print("  PASS test_scheduler_beijing_window_and_shared_web_core")


def test_account_update_lock():
    """账号更新可在持久化时重入锁"""
    import tempfile
    import threading
    from pathlib import Path
    import account_manager as module

    original_path = module.ACCOUNTS_FILE
    try:
        with tempfile.TemporaryDirectory() as tmp:
            module.ACCOUNTS_FILE = Path(tmp) / "accounts.json"
            manager = module.AccountManager()
            manager.accounts = {"acc": {"id": "acc"}}
            thread = threading.Thread(
                target=lambda: manager.update_account("acc", status="active"),
                daemon=True,
            )
            thread.start()
            thread.join(1)
            assert not thread.is_alive(), "账号更新发生锁等待"
    finally:
        module.ACCOUNTS_FILE = original_path
    print("  PASS test_account_update_lock")


def test_log_polling_does_not_hold_server_threads():
    """日志接口返回有限快照，前端刷新失败时保留现有账号"""
    import web_ui

    web_ui._logs.clear()
    web_ui._emit_log("info", "snapshot")
    response = web_ui.app.test_client().get("/api/logs")
    assert response.status_code == 200
    assert response.get_json()["logs"][-1]["msg"] == "snapshot"
    assert "text/event-stream" not in response.content_type
    assert "if(Array.isArray(a.accounts))accounts=a.accounts" in web_ui.UI_HTML
    assert ".acc-card .acc-error{" in web_ui.UI_HTML
    assert "stText.substring" not in web_ui.UI_HTML
    assert "loading-spinner" in web_ui.UI_HTML
    assert "apiLong" in web_ui.UI_HTML
    assert "重复启动返回 HTTP 409" in web_ui.UI_HTML
    assert "/api/code?token=TOKEN" in web_ui.UI_HTML
    assert "Token 使用流程" in web_ui.UI_HTML
    assert '"code":"123456","token":"TOKEN"' in web_ui.UI_HTML
    assert "<th>Token</th>" in web_ui.UI_HTML
    assert ".email-table th{text-align:center;" in web_ui.UI_HTML
    assert '<th style="text-align:right">操作</th>' not in web_ui.UI_HTML
    assert "复制 Token" in web_ui.UI_HTML
    assert "/api/code?email=alias@icloud.com" in web_ui.UI_HTML
    web_ui._logs.clear()
    print("  PASS test_log_polling_does_not_hold_server_threads")


def test_chrome_extension_manifest():
    """Chrome 扩展仅申请 iCloud Cookie 与本机服务权限"""
    manifest = json.loads(
        (HERE / "icloud-cookie-extensions" / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["manifest_version"] == 3
    assert manifest["permissions"] == ["cookies"]
    assert "https://*.icloud.com/*" in manifest["host_permissions"]
    assert "http://127.0.0.1/*" in manifest["host_permissions"]
    assert (HERE / "icloud-cookie-extensions" / "background.js").exists()
    assert (HERE / "icloud-cookie-extensions" / "bridge.js").exists()
    print("  PASS test_chrome_extension_manifest")


def test_compat_api_contract():
    """主项目需要的 accounts/create/inbox API 契约"""
    import web_ui

    class Manager:
        def list_accounts(self):
            return [{
                "id": "acc_1", "name": "main", "status": "active",
                "icloud_email": "owner@icloud.com",
                "cookies": {"TOKEN": "secret"}, "app_password": "secret-password",
            }]

        def update_cookies(self, acc_id, cookie_input):
            return {
                "id": acc_id, "name": "main", "status": "active",
                "real_email": "owner@example.com", "alias_total": 2,
                "alias_active": 1,
            }

        def deactivate_alias(self, acc_id, anonymous_id):
            return {"alias_total": 2, "alias_active": 1}

        def delete_alias(self, acc_id, anonymous_id):
            return {"alias_total": 1, "alias_active": 1}

        def create_aliases_for_account(self, acc_id, count=1, label=""):
            return [{"ok": True, "email": "alias@icloud.com", "account_id": acc_id}]

        def get_all_aliases(self):
            return [{
                "account_id": "acc_1",
                "email": "alias@icloud.com",
                "active": True,
            }]

        def check_alias_mail(self, acc_id, alias, limit=20, days=7, force=False):
            return [{
                "id": "1", "from": "noreply@openai.com", "to": alias,
                "subject": "Your code", "preview": "123456",
                "date": "2026-07-29T12:00:00",
            }]

        def check_inbox(self, acc_id, limit=20, days=7, force=False):
            return []

    original = web_ui._account_mgr
    original_scheduler_thread = web_ui._scheduler_thread
    original_mail_tokens = web_ui._mail_tokens
    original_save_mail_tokens = web_ui._save_mail_tokens
    web_ui._account_mgr = Manager()
    web_ui._mail_tokens = {}
    web_ui._save_mail_tokens = lambda: None
    try:
        client = web_ui.app.test_client()
        class AliveThread:
            def is_alive(self): return True

        web_ui._scheduler_thread = AliveThread()
        duplicate_start = client.post("/api/scheduler/start")
        assert duplicate_start.status_code == 409
        assert duplicate_start.get_json()["ok"] is False

        accounts = client.get("/api/accounts").get_json()
        assert accounts["success"] is True
        assert accounts["data"][0]["id"] == "acc_1"
        assert "cookies" not in accounts["data"][0]
        assert "app_password" not in accounts["data"][0]
        assert accounts["data"][0]["mail_token"]

        updated = client.post(
            "/api/accounts/acc_1/cookies",
            json={"cookie_input": "TOKEN=new"},
        ).get_json()
        assert updated["ok"] is True
        assert updated["id"] == "acc_1"

        assert "从 Chrome 自动提取" in web_ui.UI_HTML
        assert "ICLOUD_HME_EXTENSION_UPDATE" in web_ui.UI_HTML

        deactivated = client.post(
            "/api/accounts/acc_1/aliases/alias_1/deactivate"
        ).get_json()
        assert deactivated["ok"] is True

        deleted = client.post(
            "/api/accounts/acc_1/aliases/alias_1/delete"
        ).get_json()
        assert deleted["ok"] is True
        assert "deactivateAlias" in web_ui.UI_HTML
        assert "deleteAlias" in web_ui.UI_HTML

        created = client.post(
            "/api/create",
            json={"account_id": "acc_1", "label": "OpenAI"},
        ).get_json()
        assert created["data"]["email"] == "alias@icloud.com"
        alias_token = created["data"]["token"]
        assert alias_token

        aliases = client.get("/api/aliases").get_json()
        assert aliases["aliases"][0]["token"] == alias_token

        inbox = client.get(
            "/api/inbox",
            query_string={"account_id": "acc_1", "alias": "alias@icloud.com"},
        ).get_json()
        assert inbox["data"]["messages"][0]["preview"] == "123456"

        code_response = client.get(
            "/api/code",
            query_string={"account_id": "acc_1", "email": "alias@icloud.com"},
        )
        assert code_response.status_code == 200
        code_data = code_response.get_json()
        assert code_data["success"] is True
        assert code_data["data"]["code"] == "123456"
        assert code_data["data"]["email"] == "alias@icloud.com"

        token_code = client.get(
            "/api/code",
            query_string={"token": alias_token},
        )
        assert token_code.status_code == 200
        token_data = token_code.get_json()["data"]
        assert token_data["code"] == "123456"
        assert token_data["token"] == alias_token
        assert "email" not in token_data

        invalid_token = client.get(
            "/api/code",
            query_string={"token": "missing"},
        )
        assert invalid_token.status_code == 404

        invalid_code = client.get("/api/code")
        assert invalid_code.status_code == 400
    finally:
        web_ui._account_mgr = original
        web_ui._scheduler_thread = original_scheduler_thread
        web_ui._mail_tokens = original_mail_tokens
        web_ui._save_mail_tokens = original_save_mail_tokens
    print("  PASS test_compat_api_contract")


if __name__ == "__main__":
    tests = [
        ("parse_cookie_header_string", test_parse_cookie_header_string),
        ("parse_cookie_json", test_parse_cookie_json),
        ("parse_cookie_editor_export", test_parse_cookie_editor_export),
        ("parse_empty_input", test_parse_empty_input),
        ("derive_icloud_email_primary", test_derive_icloud_email_primary),
        ("derive_icloud_email_appleid_is_icloud", test_derive_icloud_email_appleid_is_icloud),
        ("derive_icloud_email_third_party", test_derive_icloud_email_third_party),
        ("update_cookies_preserves_account", test_update_cookies_preserves_account),
        ("alias_deactivate_and_delete", test_alias_deactivate_and_delete),
        ("scheduler_beijing_window_and_shared_web_core", test_scheduler_beijing_window_and_shared_web_core),
        ("account_update_lock", test_account_update_lock),
        ("mail_cache_basic", test_mail_cache_basic),
        ("mail_reads_inbox_and_junk", test_mail_reads_inbox_and_junk),
        ("strip_html", test_strip_html),
        ("strip_html_with_link", test_strip_html_with_link),
        ("chrome_cookie_path_scans_profiles", test_chrome_cookie_path_scans_profiles),
        ("icloud_hme_421_message", test_icloud_hme_421_message),
        ("icloud_hme_account_info", test_icloud_hme_account_info),
        ("log_polling_does_not_hold_server_threads", test_log_polling_does_not_hold_server_threads),
        ("chrome_extension_manifest", test_chrome_extension_manifest),
        ("compat_api_contract", test_compat_api_contract),
    ]
    
    passed = 0
    failed = 0
    
    for name, fn in tests:
        try:
            fn()
            passed += 1
        except Exception as e:
            print(f"  FAIL {name}: {e}")
            failed += 1
    
    print(f"\n{'='*40}")
    print(f"结果: {passed} 通过, {failed} 失败")
    
    if failed:
        sys.exit(1)
