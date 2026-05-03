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
    from . import client_api
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from clients.windows import client_api

WINDOW_TITLE = "BaizeFinDB Windows Client"


class BaizeFinDBClientApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.server_url = tk.StringVar(
            value=os.environ.get("BAIZEFINDB_SERVER_URL", client_api.DEFAULT_SERVER_URL),
        )
        self.user_key = tk.StringVar(
            value=os.environ.get("BAIZEFINDB_USER_KEY", client_api.DEFAULT_USER_KEY),
        )
        self.status_text = tk.StringVar(value="就绪")
        self.buttons: list[ttk.Button] = []

        self._build_ui()

    def _build_ui(self) -> None:
        self.root.title(WINDOW_TITLE)
        self.root.geometry("860x620")
        self.root.minsize(720, 480)

        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(3, weight=1)

        ttk.Label(main, text="Server URL").grid(row=0, column=0, sticky=tk.W, padx=(0, 8))
        url_entry = ttk.Entry(main, textvariable=self.server_url)
        url_entry.grid(row=0, column=1, sticky=tk.EW)

        ttk.Label(main, text="User Key").grid(row=1, column=0, sticky=tk.W, padx=(0, 8))
        user_entry = ttk.Entry(main, textvariable=self.user_key)
        user_entry.grid(row=1, column=1, sticky=tk.EW)

        button_frame = ttk.Frame(main)
        button_frame.grid(row=2, column=0, columnspan=2, sticky=tk.EW, pady=(10, 10))

        self._add_button(button_frame, "检查状态", self.check_status)
        self._add_button(button_frame, "刷新雷达", self.refresh_radar)
        self._add_button(button_frame, "查看信号", self.view_signals)
        self._add_button(button_frame, "查看持仓", self.view_holdings)
        self._add_button(button_frame, "查看自选", self.view_watchlist)
        self._add_button(button_frame, "打开 Web 面板", self.open_web_panel)

        self.output = scrolledtext.ScrolledText(main, wrap=tk.WORD, height=24)
        self.output.grid(row=3, column=0, columnspan=2, sticky=tk.NSEW)
        self.output.insert(
            tk.END,
            "BaizeFinDB Windows 客户端 MVP\n\n"
            "输入 API 地址和 User Key 后选择操作。雷达等级、生命周期和审查状态均来自后端 API。\n",
        )
        self.output.configure(state=tk.DISABLED)

        status_bar = ttk.Label(main, textvariable=self.status_text, anchor=tk.W)
        status_bar.grid(row=4, column=0, columnspan=2, sticky=tk.EW, pady=(8, 0))

    def _add_button(self, parent: ttk.Frame, label: str, command: Callable[[], None]) -> None:
        button = ttk.Button(parent, text=label, command=command)
        button.pack(side=tk.LEFT, padx=(0, 8))
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
