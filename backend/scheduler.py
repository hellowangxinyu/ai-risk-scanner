"""每日自动扫描调度：三护栏——①已有运行中批次跳过 ②宕机补跑（纯函数判定）③默认 02:00。"""
import threading
import traceback
from datetime import datetime

import db
from logic import should_catch_up


class AutoScanScheduler(threading.Thread):
    INTERVAL_SECONDS = 30

    def __init__(self):
        super().__init__(daemon=True, name="auto-scan-scheduler")
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        while not self._stop_event.wait(self.INTERVAL_SECONDS):
            try:
                self.tick()
            except Exception:  # noqa: BLE001 调度器永不因单次异常退出
                traceback.print_exc()

    def tick(self):
        settings = db.get_settings()
        if settings.get("auto_scan_enabled") != "1":
            return
        now = datetime.now()
        if not should_catch_up(
            settings.get("last_auto_scan_date", ""),
            now,
            settings.get("auto_scan_time", "02:00"),
        ):
            return
        # 护栏①：已有运行中批次 → 本次跳过，下个 tick 再试
        from scanner import due_customer_ids, has_running_batch, start_batch

        if has_running_batch():
            return
        # 先记账再执行，避免执行期间重复触发
        db.update_settings({"last_auto_scan_date": now.strftime("%Y-%m-%d")})
        ids = due_customer_ids()
        if not ids:
            return
        try:
            start_batch(ids, trigger="自动")
        except Exception:  # noqa: BLE001 护栏冲突等，下个 tick 再试
            traceback.print_exc()
