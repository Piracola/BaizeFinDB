"""Tkinter GUI for the BaizeFinDB Windows client MVP."""

from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
import webbrowser
from collections.abc import Callable
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

try:
    from . import client_api, smoke_check
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from clients.windows import client_api, smoke_check

WINDOW_TITLE = "BaizeFinDB Windows Client"
DEFAULT_OPS_LOOKBACK_HOURS = 24
MIN_OPS_LOOKBACK_HOURS = 1
MAX_OPS_LOOKBACK_HOURS = 168


def parse_ops_lookback_hours(raw_value: str) -> int:
    value = raw_value.strip()
    try:
        lookback_hours = int(value)
    except ValueError as exc:
        msg = "OPS Lookback 必须是 1 到 168 之间的整数小时。"
        raise ValueError(msg) from exc

    if not MIN_OPS_LOOKBACK_HOURS <= lookback_hours <= MAX_OPS_LOOKBACK_HOURS:
        msg = "OPS Lookback 必须是 1 到 168 之间的整数小时。"
        raise ValueError(msg)

    return lookback_hours


class BaizeFinDBClientApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.server_url = tk.StringVar(
            value=os.environ.get("BAIZEFINDB_SERVER_URL", client_api.DEFAULT_SERVER_URL),
        )
        self.user_key = tk.StringVar(
            value=os.environ.get("BAIZEFINDB_USER_KEY", client_api.DEFAULT_USER_KEY),
        )
        self.signal_id = tk.StringVar(value=os.environ.get("BAIZEFINDB_SIGNAL_ID", "1"))
        self.ops_lookback_hours = tk.StringVar(value=str(DEFAULT_OPS_LOOKBACK_HOURS))
        self.telegram_chat_id = tk.StringVar(
            value=os.environ.get("BAIZEFINDB_TELEGRAM_CHAT_ID", ""),
        )
        self.telegram_secret = tk.StringVar(value=os.environ.get("BAIZEFINDB_TELEGRAM_SECRET", ""))
        self.status_text = tk.StringVar(value="就绪")
        self.buttons: list[ttk.Button] = []
        self._button_index = 0

        self._build_ui()

    def _build_ui(self) -> None:
        self.root.title(WINDOW_TITLE)
        self.root.geometry("860x620")
        self.root.minsize(720, 480)

        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(7, weight=1)

        ttk.Label(main, text="Server URL").grid(row=0, column=0, sticky=tk.W, padx=(0, 8))
        url_entry = ttk.Entry(main, textvariable=self.server_url)
        url_entry.grid(row=0, column=1, sticky=tk.EW)

        ttk.Label(main, text="User Key").grid(row=1, column=0, sticky=tk.W, padx=(0, 8))
        user_entry = ttk.Entry(main, textvariable=self.user_key)
        user_entry.grid(row=1, column=1, sticky=tk.EW)

        ttk.Label(main, text="Signal ID").grid(row=2, column=0, sticky=tk.W, padx=(0, 8))
        signal_entry = ttk.Entry(main, textvariable=self.signal_id, width=18)
        signal_entry.grid(row=2, column=1, sticky=tk.W)

        ttk.Label(main, text="OPS Lookback (hours)").grid(
            row=3,
            column=0,
            sticky=tk.W,
            padx=(0, 8),
        )
        ops_lookback_entry = ttk.Entry(main, textvariable=self.ops_lookback_hours, width=18)
        ops_lookback_entry.grid(row=3, column=1, sticky=tk.W)

        ttk.Label(main, text="Telegram Chat ID").grid(
            row=4,
            column=0,
            sticky=tk.W,
            padx=(0, 8),
        )
        chat_entry = ttk.Entry(main, textvariable=self.telegram_chat_id, width=24)
        chat_entry.grid(row=4, column=1, sticky=tk.W)

        ttk.Label(main, text="Telegram Secret").grid(
            row=5,
            column=0,
            sticky=tk.W,
            padx=(0, 8),
        )
        secret_entry = ttk.Entry(main, textvariable=self.telegram_secret, show="*")
        secret_entry.grid(row=5, column=1, sticky=tk.EW)

        button_frame = ttk.Frame(main)
        button_frame.grid(row=6, column=0, columnspan=2, sticky=tk.EW, pady=(10, 10))

        self._add_button(button_frame, "检查状态", self.check_status)
        self._add_button(button_frame, "运行状态", self.view_ops_overview)
        self._add_button(button_frame, "运维历史", self.view_ops_history)
        self._add_button(button_frame, "就绪自检", self.view_ops_readiness)
        self._add_button(button_frame, "首用诊断", self.run_first_use_smoke_check)
        self._add_button(button_frame, "数据源状态", self.view_tushare_status)
        self._add_button(button_frame, "数据源自检", self.view_tushare_readiness)
        self._add_button(button_frame, "刷新雷达", self.refresh_radar)
        self._add_button(button_frame, "查看信号", self.view_signals)
        self._add_button(button_frame, "查看持仓", self.view_holdings)
        self._add_button(button_frame, "查看自选", self.view_watchlist)
        self._add_button(button_frame, "查看报告", self.view_reports)
        self._add_button(button_frame, "查看日报", self.view_daily_report)
        self._add_button(button_frame, "查看周报", self.view_weekly_report)
        self._add_button(button_frame, "生成评分", self.view_signal_scores)
        self._add_button(button_frame, "查看绑定", self.view_telegram_bindings)
        self._add_button(button_frame, "绑定 Chat", self.bind_telegram_chat)
        self._add_button(button_frame, "禁用 Chat", self.disable_telegram_chat)
        self._add_button(button_frame, "打开 Web 面板", self.open_web_panel)

        self.output = scrolledtext.ScrolledText(main, wrap=tk.WORD, height=24)
        self.output.grid(row=7, column=0, columnspan=2, sticky=tk.NSEW)
        self.output.insert(
            tk.END,
            "BaizeFinDB Windows 客户端 MVP\n\n"
            "输入 API 地址和 User Key 后选择操作。雷达等级、生命周期和审查状态均来自后端 API。\n",
        )
        self.output.configure(state=tk.DISABLED)

        status_bar = ttk.Label(main, textvariable=self.status_text, anchor=tk.W)
        status_bar.grid(row=8, column=0, columnspan=2, sticky=tk.EW, pady=(8, 0))

    def _add_button(self, parent: ttk.Frame, label: str, command: Callable[[], None]) -> None:
        button = ttk.Button(parent, text=label, command=command)
        row, column = divmod(self._button_index, 5)
        button.grid(row=row, column=column, sticky=tk.W, padx=(0, 8), pady=(0, 6))
        self._button_index += 1
        self.buttons.append(button)

    def check_status(self) -> None:
        def worker() -> str:
            try:
                payload = client_api.fetch_health(self._normalized_server_url())
                return client_api.format_health(payload)
            except client_api.BaizeApiError as exc:
                if isinstance(exc.payload, dict):
                    health_text = client_api.format_health(exc.payload)
                    return f"{health_text}\n\n{client_api.format_api_error(exc)}"
                raise

        self._run_worker("检查 API 状态", worker)

    def view_ops_overview(self) -> None:
        try:
            lookback_hours = self._normalized_ops_lookback_hours()
        except ValueError as exc:
            messagebox.showerror(WINDOW_TITLE, str(exc))
            return

        def worker() -> str:
            overview = client_api.fetch_ops_overview(
                self._normalized_server_url(),
                lookback_hours=lookback_hours,
            )
            return client_api.format_ops_overview(overview)

        self._run_worker("读取运行状态", worker)

    def view_ops_history(self) -> None:
        try:
            lookback_hours = self._normalized_ops_lookback_hours()
        except ValueError as exc:
            messagebox.showerror(WINDOW_TITLE, str(exc))
            return

        def worker() -> str:
            history = client_api.fetch_ops_history(
                self._normalized_server_url(),
                lookback_hours=lookback_hours,
                limit=20,
            )
            return client_api.format_ops_history(history)

        self._run_worker("读取运维历史", worker)

    def view_ops_readiness(self) -> None:
        try:
            lookback_hours = self._normalized_ops_lookback_hours()
        except ValueError as exc:
            messagebox.showerror(WINDOW_TITLE, str(exc))
            return

        def worker() -> str:
            readiness = client_api.fetch_ops_readiness(
                self._normalized_server_url(),
                lookback_hours=lookback_hours,
            )
            return client_api.format_ops_readiness(readiness)

        self._run_worker("读取运行就绪自检", worker)

    def run_first_use_smoke_check(self) -> None:
        try:
            lookback_hours = self._normalized_ops_lookback_hours()
        except ValueError as exc:
            messagebox.showerror(WINDOW_TITLE, str(exc))
            return

        def worker() -> str:
            report = smoke_check.run_smoke_check(
                server_url=self._normalized_server_url(),
                user_key=self._normalized_user_key(),
                ops_readiness_lookback_hours=lookback_hours,
            )
            return smoke_check.format_summary(report)

        self._run_worker("运行首用诊断", worker)

    def view_tushare_status(self) -> None:
        def worker() -> str:
            payload = client_api.fetch_tushare_status(self._normalized_server_url())
            return client_api.format_tushare_status(payload)

        self._run_worker("读取数据源状态", worker)

    def view_tushare_readiness(self) -> None:
        def worker() -> str:
            payload = client_api.fetch_tushare_readiness(self._normalized_server_url())
            return client_api.format_tushare_readiness(payload)

        self._run_worker("读取数据源自检", worker)

    def refresh_radar(self) -> None:
        def worker() -> str:
            overview = client_api.fetch_radar_overview(self._normalized_server_url())
            return client_api.format_radar_overview(overview)

        self._run_worker("刷新雷达总览", worker)

    def view_signals(self) -> None:
        def worker() -> str:
            signals = client_api.fetch_signals(self._normalized_server_url())
            return client_api.format_signals(signals)

        self._run_worker("读取信号列表", worker)

    def view_holdings(self) -> None:
        def worker() -> str:
            holdings = client_api.fetch_holdings(
                self._normalized_server_url(),
                user_key=self._normalized_user_key(),
            )
            return client_api.format_holdings(holdings)

        self._run_worker("读取持仓", worker)

    def view_watchlist(self) -> None:
        def worker() -> str:
            items = client_api.fetch_watchlist(
                self._normalized_server_url(),
                user_key=self._normalized_user_key(),
            )
            return client_api.format_watchlist(items)

        self._run_worker("读取自选", worker)

    def view_reports(self) -> None:
        def worker() -> str:
            reports = client_api.fetch_reports(
                self._normalized_server_url(),
                user_key=self._normalized_user_key(),
            )
            return client_api.format_reports(reports)

        self._run_worker("读取报告", worker)

    def view_daily_report(self) -> None:
        self._view_periodic_report("daily", "读取日报")

    def view_weekly_report(self) -> None:
        self._view_periodic_report("weekly", "读取周报")

    def _view_periodic_report(self, period: str, action: str) -> None:
        def worker() -> str:
            report = client_api.fetch_periodic_report(
                self._normalized_server_url(),
                user_key=self._normalized_user_key(),
                period=period,
            )
            return client_api.format_periodic_report(report)

        self._run_worker(action, worker)

    def view_signal_scores(self) -> None:
        try:
            signal_id = self._normalized_signal_id()
        except ValueError as exc:
            messagebox.showerror(WINDOW_TITLE, str(exc))
            return

        def worker() -> str:
            score_run = client_api.score_signal(
                self._normalized_server_url(),
                signal_id,
            )
            return client_api.format_scores(score_run)

        self._run_worker(f"生成信号 #{signal_id} 评分", worker)

    def view_telegram_bindings(self) -> None:
        def worker() -> str:
            bindings = client_api.fetch_telegram_bindings(
                self._normalized_server_url(),
                secret_token=self._normalized_telegram_secret(),
            )
            return client_api.format_telegram_bindings(bindings)

        self._run_worker("读取 Telegram 绑定", worker)

    def bind_telegram_chat(self) -> None:
        try:
            chat_id = self._normalized_telegram_chat_id()
        except ValueError as exc:
            messagebox.showerror(WINDOW_TITLE, str(exc))
            return

        def worker() -> str:
            binding = client_api.upsert_telegram_binding(
                self._normalized_server_url(),
                chat_id=chat_id,
                user_key=self._normalized_user_key(),
                display_name="Windows client",
                is_allowed=True,
                secret_token=self._normalized_telegram_secret(),
            )
            return client_api.format_telegram_bindings([binding])

        self._run_worker(f"绑定 Telegram chat {chat_id}", worker)

    def disable_telegram_chat(self) -> None:
        try:
            chat_id = self._normalized_telegram_chat_id()
        except ValueError as exc:
            messagebox.showerror(WINDOW_TITLE, str(exc))
            return

        def worker() -> str:
            binding = client_api.update_telegram_binding(
                self._normalized_server_url(),
                chat_id=chat_id,
                is_allowed=False,
                secret_token=self._normalized_telegram_secret(),
            )
            return client_api.format_telegram_bindings([binding])

        self._run_worker(f"禁用 Telegram chat {chat_id}", worker)

    def open_web_panel(self) -> None:
        try:
            url = client_api.build_url(self._normalized_server_url(), "/")
        except ValueError as exc:
            messagebox.showerror(WINDOW_TITLE, str(exc))
            return

        webbrowser.open(url)
        self.status_text.set(f"已打开 Web 面板：{url}")

    def _normalized_server_url(self) -> str:
        return client_api.normalize_base_url(self.server_url.get())

    def _normalized_user_key(self) -> str:
        value = self.user_key.get().strip()
        return value or client_api.DEFAULT_USER_KEY

    def _normalized_signal_id(self) -> int:
        value = self.signal_id.get().strip()
        try:
            signal_id = int(value)
        except ValueError as exc:
            msg = "Signal ID 必须是正整数。"
            raise ValueError(msg) from exc

        if signal_id <= 0:
            msg = "Signal ID 必须是正整数。"
            raise ValueError(msg)

        return signal_id

    def _normalized_ops_lookback_hours(self) -> int:
        return parse_ops_lookback_hours(self.ops_lookback_hours.get())

    def _normalized_telegram_chat_id(self) -> int:
        value = self.telegram_chat_id.get().strip()
        try:
            chat_id = int(value)
        except ValueError as exc:
            msg = "Telegram Chat ID 必须是非零整数。"
            raise ValueError(msg) from exc

        if chat_id == 0:
            msg = "Telegram Chat ID 必须是非零整数。"
            raise ValueError(msg)

        return chat_id

    def _normalized_telegram_secret(self) -> str | None:
        value = self.telegram_secret.get().strip()
        return value or None

    def _run_worker(self, action: str, worker: Callable[[], str]) -> None:
        try:
            self._normalized_server_url()
        except ValueError as exc:
            messagebox.showerror(WINDOW_TITLE, str(exc))
            return

        self._set_busy(True)
        self.status_text.set(f"{action}中...")

        def target() -> None:
            try:
                result = worker()
            except Exception as exc:  # noqa: BLE001
                result = client_api.format_api_error(exc)
                status = f"{action}失败"
            else:
                status = f"{action}完成"

            self.root.after(0, lambda: self._finish_worker(status, result))

        threading.Thread(target=target, daemon=True).start()

    def _finish_worker(self, status: str, text: str) -> None:
        self._write_output(text)
        self.status_text.set(status)
        self._set_busy(False)

    def _write_output(self, text: str) -> None:
        self.output.configure(state=tk.NORMAL)
        self.output.delete("1.0", tk.END)
        self.output.insert(tk.END, text)
        self.output.configure(state=tk.DISABLED)

    def _set_busy(self, busy: bool) -> None:
        state = tk.DISABLED if busy else tk.NORMAL
        for button in self.buttons:
            button.configure(state=state)


def main() -> None:
    root = tk.Tk()
    root._baizefindb_app = BaizeFinDBClientApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
