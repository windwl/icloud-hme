#!/usr/bin/env python3
"""iCloud HME 统一调度核心与命令行入口。"""

import argparse, json, logging, os, random, signal, sys, threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path: sys.path.insert(0, str(HERE))
from account_manager import AccountManager

LOG_DIR, RESULT_DIR = HERE / "logs", HERE / "results"
STATE_FILE = HERE / "scheduler_state.json"
BEIJING_TZ = timezone(timedelta(hours=8), "Asia/Shanghai")
WINDOW_START_HOUR, WINDOW_END_HOUR = 7, 20
ROUND_INTERVAL_RANGE = (3600, 5400)
ALIAS_DELAY_RANGE, ACCOUNT_DELAY_RANGE = (15, 45), (120, 300)
LIMIT_KEYWORDS = ["limit", "exceeded", "maximum", "too many", "quota", "cannot create", "unavailable", "try again later", "rate limit", "429", "已达上限", "超过限制"]
SESSION_KEYWORDS = ["401", "403", "421", "cookie", "session", "validate", "会话"]


def beijing_now(now: Optional[datetime] = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None: current = current.astimezone()
    return current.astimezone(BEIJING_TZ)


def is_active_window(now: Optional[datetime] = None) -> bool:
    return WINDOW_START_HOUR <= beijing_now(now).hour < WINDOW_END_HOUR


def next_window_start(now: Optional[datetime] = None) -> datetime:
    current = beijing_now(now)
    if current.hour < WINDOW_START_HOUR:
        return current.replace(hour=WINDOW_START_HOUR, minute=0, second=0, microsecond=0)
    tomorrow = current + timedelta(days=1)
    return tomorrow.replace(hour=WINDOW_START_HOUR, minute=0, second=0, microsecond=0)


def setup_logging(verbose: bool = True) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True); RESULT_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("icloud_scheduler"); logger.setLevel(logging.DEBUG); logger.handlers.clear()
    file_handler = logging.FileHandler(str(LOG_DIR / f"scheduler_{beijing_now().strftime('%Y%m%d')}.log"), encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    console = logging.StreamHandler(sys.stdout); console.setLevel(logging.INFO if verbose else logging.WARNING)
    console.setFormatter(logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(file_handler); logger.addHandler(console)
    return logger


def load_state() -> Dict:
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            state.setdefault("total_created", 0); state.setdefault("rounds", []); state.setdefault("last_error", None)
            return state
        except (json.JSONDecodeError, OSError): pass
    return {"total_created": 0, "rounds": [], "last_error": None}


def save_state(state: Dict):
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


class CreateRound:
    def __init__(self):
        self.start_time = beijing_now(); self.end_time: Optional[datetime] = None
        self.created: List[str] = []; self.created_by_account: Dict[str, int] = {}; self.errors: List[Dict] = []
        self.hit_limit = False; self.fatal_error: Optional[str] = None


def is_limit_error(error: str) -> bool:
    return any(keyword in error.lower() for keyword in LIMIT_KEYWORDS)


def run_one_round(mgr: AccountManager, logger, label: str = "", stop_event: Optional[threading.Event] = None) -> CreateRound:
    stop_event = stop_event or threading.Event(); result = CreateRound()
    accounts = [a for a in mgr.list_accounts() if a.get("status") == "active"]
    if not accounts:
        logger.warning("没有活跃账号"); result.end_time = beijing_now(); return result
    logger.info(f"新一轮：{len(accounts)} 个账号，每账号随机 3–5 个")
    for index, account in enumerate(accounts):
        if stop_event.is_set(): break
        account_id, account_name = account["id"], account.get("name", account["id"])
        target, created, errors = random.randint(3, 5), 0, 0
        logger.info(f"[{index + 1}/{len(accounts)}] {account_name} 目标 {target} 个")
        while created < target and errors < 3 and not stop_event.is_set():
            try:
                alias_label = label or f"{account_name} {beijing_now().strftime('%m%d%H%M')}-{created + 1}"
                items = mgr.create_aliases_for_account(account_id, count=1, label=alias_label)
                item = items[0] if items else {"ok": False, "error": "创建结果为空"}
                if item.get("ok") and item.get("email"):
                    created += 1; errors = 0; result.created.append(item["email"])
                    result.created_by_account[account_id] = result.created_by_account.get(account_id, 0) + 1
                    logger.info(f"[{account_name}] 创建成功 ({created}/{target}) {item['email']}")
                    if stop_event.wait(random.uniform(*ALIAS_DELAY_RANGE)): break
                    continue
                error = str(item.get("error") or "创建失败"); errors += 1
                result.errors.append({"account_id": account_id, "error": error})
                if is_limit_error(error): result.hit_limit = True; logger.info(f"[{account_name}] 已触达创建上限"); break
                logger.warning(f"[{account_name}] 创建失败: {error[:120]}")
            except Exception as exc:
                error = str(exc); errors += 1; result.errors.append({"account_id": account_id, "error": error})
                if is_limit_error(error): result.hit_limit = True; logger.info(f"[{account_name}] 已触达创建上限"); break
                if any(keyword in error.lower() for keyword in SESSION_KEYWORDS):
                    mgr.update_account(account_id, status="error", last_error=error[:300]); result.fatal_error = error
                    logger.error(f"[{account_name}] 会话失效: {error[:160]}"); break
                logger.warning(f"[{account_name}] 创建异常: {error[:120]}")
        if index < len(accounts) - 1 and not stop_event.is_set():
            if stop_event.wait(random.uniform(*ACCOUNT_DELAY_RANGE)): break
    result.end_time = beijing_now(); logger.info(f"本轮结束：创建 {len(result.created)} 个")
    return result


def save_round_result(result: CreateRound, logger):
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULT_DIR / f"round_{result.start_time.strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps({"start_time": result.start_time.isoformat(), "end_time": result.end_time.isoformat() if result.end_time else None, "created_count": len(result.created), "created": result.created, "errors": result.errors, "hit_limit": result.hit_limit, "fatal_error": result.fatal_error}, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"轮次结果已保存: {path.name}")


def run_scheduler(mgr: AccountManager, logger, stop_event: threading.Event, label_prefix: str = "", on_state=None):
    state = load_state(); round_number = state["rounds"][-1]["round"] if state["rounds"] else 0
    def publish(**changes):
        if on_state: on_state(changes)
    summary = mgr.get_summary()
    logger.info(f"调度器启动：{summary['account_count']} 个账号，{summary['active_accounts']} 个活跃")
    logger.info("策略：北京时间 07:00–20:00，轮间 60–90 分钟，每账号 3–5 个")
    publish(running=True, creating=False, total_created=state["total_created"], round_status="等待调度窗口")
    try:
        while not stop_event.is_set():
            now = beijing_now()
            if not is_active_window(now):
                target = next_window_start(now)
                publish(creating=False, round_status=f"非运行时段，{target.strftime('%m-%d %H:%M')} 开始", next_trigger=target.timestamp())
                stop_event.wait(min(1800, (target - now).total_seconds())); continue
            if mgr.get_summary()["active_accounts"] == 0:
                target = now + timedelta(minutes=30)
                publish(creating=False, round_status="没有活跃账号，30 分钟后重试", next_trigger=target.timestamp())
                stop_event.wait(1800); continue
            round_number += 1; label = f"{label_prefix}R{round_number} {now.strftime('%m%d%H%M')}".strip()
            publish(creating=True, round_status=f"第 {round_number} 轮创建中", next_trigger=None)
            result = run_one_round(mgr, logger, label=label, stop_event=stop_event); save_round_result(result, logger)
            count = len(result.created); state["total_created"] += count
            state["rounds"].append({"round": round_number, "time": now.isoformat(), "created": count, "by_account": result.created_by_account, "hit_limit": result.hit_limit})
            state["rounds"] = state["rounds"][-200:]; state["last_error"] = result.fatal_error; save_state(state)
            if stop_event.is_set(): break
            interval = random.randint(*ROUND_INTERVAL_RANGE); target = beijing_now() + timedelta(seconds=interval)
            publish(creating=False, created_delta=count, total_created=state["total_created"], current_round_created=count, round_status=f"本轮创建 {count} 个", next_trigger=target.timestamp(), last_error=result.fatal_error)
            logger.info(f"下轮时间：{target.strftime('%H:%M')}（{interval // 60} 分钟后）"); stop_event.wait(interval)
    finally:
        publish(running=False, creating=False, next_trigger=None, round_status="已停止")
        save_state(state); logger.info(f"调度器停止，累计创建 {state['total_created']} 个")


class Scheduler:
    def __init__(self, mgr: AccountManager, label_prefix: str = "", verbose: bool = True):
        self.mgr, self.label_prefix, self.logger = mgr, label_prefix, setup_logging(verbose)
        self.stop_event = threading.Event(); signal.signal(signal.SIGINT, self._handle_signal); signal.signal(signal.SIGTERM, self._handle_signal)
    def _handle_signal(self, signum, frame): self.logger.info(f"收到信号 {signum}，准备停止"); self.stop_event.set()
    def run(self): run_scheduler(self.mgr, self.logger, self.stop_event, label_prefix=self.label_prefix)


def main():
    parser = argparse.ArgumentParser(description="iCloud HME 多账号定时调度器")
    parser.add_argument("--label", default="", help="标签前缀"); parser.add_argument("--quiet", "-q", action="store_true", help="减少控制台输出"); parser.add_argument("--daemon", "-d", action="store_true", help="后台运行（非 Windows）")
    args = parser.parse_args(); manager = AccountManager(); summary = manager.get_summary()
    if summary["active_accounts"] == 0: print("没有活跃账号"); sys.exit(1)
    print(f"已加载 {summary['account_count']} 个账号（{summary['active_accounts']} 个活跃）")
    if args.daemon:
        if sys.platform == "win32": print("Windows 不支持 --daemon"); sys.exit(1)
        pid = os.fork()
        if pid > 0: print(f"后台进程 PID={pid}"); sys.exit(0)
        os.setsid(); os.umask(0)
    Scheduler(manager, label_prefix=args.label, verbose=not args.quiet).run()


if __name__ == "__main__": main()
