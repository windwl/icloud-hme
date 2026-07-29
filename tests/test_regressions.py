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
    ]
    
    cache.set_inbox("test_acc", emails)
    cached = cache.get_inbox("test_acc")
    
    # 应该有 2 封（第 3 封 id 重复被去重）
    assert len(cached) == 2, f"期望 2 封，实际 {len(cached)}"
    
    # 清理
    cache.clear_account("test_acc")
    assert len(cache.get_inbox("test_acc")) == 0
    print("  PASS test_mail_cache_basic")


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
    import tempfile
    import icloud_hme

    old_local_appdata = os.environ.get("LOCALAPPDATA")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            cookie = Path(tmp) / "Google" / "Chrome" / "User Data" / "Profile 1" / "Network" / "Cookies"
            cookie.parent.mkdir(parents=True)
            cookie.touch()
            os.environ["LOCALAPPDATA"] = tmp
            assert Path(icloud_hme._get_chrome_cookie_path()) == cookie
    finally:
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
    web_ui._logs.clear()
    print("  PASS test_log_polling_does_not_hold_server_threads")


def test_compat_api_contract():
    """主项目需要的 accounts/create/inbox API 契约"""
    import web_ui

    received_cookie_inputs = []

    class Manager:
        def list_accounts(self):
            return [{
                "id": "acc_1", "name": "main", "status": "active",
                "cookies": {"TOKEN": "secret"}, "app_password": "secret-password",
            }]

        def update_cookies(self, acc_id, cookie_input):
            received_cookie_inputs.append(cookie_input)
            return {
                "id": acc_id, "name": "main", "status": "active",
                "real_email": "owner@example.com", "alias_total": 2,
                "alias_active": 1,
            }

        def create_aliases_for_account(self, acc_id, count=1, label=""):
            return [{"ok": True, "email": "alias@icloud.com", "account_id": acc_id}]

        def check_alias_mail(self, acc_id, alias, limit=20, days=7, force=False):
            return [{
                "id": "1", "from": "noreply@openai.com", "to": alias,
                "subject": "Your code", "preview": "123456",
                "date": "2026-07-29T12:00:00",
            }]

        def check_inbox(self, acc_id, limit=20, days=7, force=False):
            return []

    original = web_ui._account_mgr
    original_extract = web_ui.extract_chrome_cookies
    web_ui._account_mgr = Manager()
    web_ui.extract_chrome_cookies = lambda: {"TOKEN": "from-chrome"}
    try:
        client = web_ui.app.test_client()
        accounts = client.get("/api/accounts").get_json()
        assert accounts["success"] is True
        assert accounts["data"][0]["id"] == "acc_1"
        assert "cookies" not in accounts["data"][0]
        assert "app_password" not in accounts["data"][0]

        updated = client.post(
            "/api/accounts/acc_1/cookies",
            json={"cookie_input": "TOKEN=new"},
        ).get_json()
        assert updated["ok"] is True
        assert updated["id"] == "acc_1"

        chrome_updated = client.post(
            "/api/accounts/acc_1/cookies",
            json={"source": "chrome"},
        ).get_json()
        assert chrome_updated["ok"] is True
        assert json.loads(received_cookie_inputs[-1]) == {"TOKEN": "from-chrome"}
        assert "从 Chrome 自动提取" in web_ui.UI_HTML

        created = client.post(
            "/api/create",
            json={"account_id": "acc_1", "label": "OpenAI"},
        ).get_json()
        assert created["data"]["email"] == "alias@icloud.com"

        inbox = client.get(
            "/api/inbox",
            query_string={"account_id": "acc_1", "alias": "alias@icloud.com"},
        ).get_json()
        assert inbox["data"]["messages"][0]["preview"] == "123456"
    finally:
        web_ui._account_mgr = original
        web_ui.extract_chrome_cookies = original_extract
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
        ("account_update_lock", test_account_update_lock),
        ("mail_cache_basic", test_mail_cache_basic),
        ("strip_html", test_strip_html),
        ("strip_html_with_link", test_strip_html_with_link),
        ("chrome_cookie_path_scans_profiles", test_chrome_cookie_path_scans_profiles),
        ("icloud_hme_421_message", test_icloud_hme_421_message),
        ("icloud_hme_account_info", test_icloud_hme_account_info),
        ("log_polling_does_not_hold_server_threads", test_log_polling_does_not_hold_server_threads),
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
