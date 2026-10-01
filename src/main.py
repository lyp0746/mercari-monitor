import argparse
import asyncio
import signal
import sys
import os

_project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_dir not in sys.path:
    sys.path.insert(0, _project_dir)


def run_gui():
    from src.gui import MonitorApp
    app = MonitorApp()
    app.run()


def run_headless(platforms=None, keywords=None):
    from src.database import Database
    from src.notifier import Notifier
    from src.api.monitor_factory import create_all_monitors, create_monitor
    from src.monitors import PLATFORM_MONITORS, PLATFORM_NAMES
    from src.telegram_bot_service import init_bot_service, start_bot_polling, stop_bot_polling

    db = Database()
    notifier = Notifier(db)

    token = db.get_setting("telegram_token", "")
    chat_id = db.get_setting("telegram_chat_id", "")
    bot_enabled = db.get_setting("telegram_bot_enabled", "false") == "true"
    if token and chat_id:
        notifier.telegram_enabled = True
        notifier.telegram_token = token
        notifier.telegram_chat_id = chat_id
        print(f"[通知] Telegram 推送已启用 (Chat ID: {chat_id})")

        if bot_enabled:
            bot_service = init_bot_service(notifier)
            start_bot_polling()
            print("[Bot] Telegram Bot命令服务已启动")
        else:
            print("[Bot] Telegram Bot命令服务未启用（可在设置中开启）")
    else:
        print("[通知] 未配置 Telegram，仅输出到控制台")

    if keywords:
        for kw in keywords:
            parts = kw.split("@", 1)
            word = parts[0]
            platform = parts[1] if len(parts) > 1 else "mercari_jp"
            if platform not in PLATFORM_MONITORS:
                print(f"[错误] 未知平台: {platform}，可用: {', '.join(PLATFORM_MONITORS.keys())}")
                sys.exit(1)
            existing = db.get_keywords(platform)
            if not any(k["keyword"] == word for k in existing):
                db.add_keyword(word, platform)
                print(f"[关键词] 已添加: {word} @ {PLATFORM_NAMES.get(platform, platform)}")

    monitors = []
    active_platforms = platforms or list(PLATFORM_MONITORS.keys())
    for p in active_platforms:
        if p not in PLATFORM_MONITORS:
            print(f"[错误] 未知平台: {p}")
            sys.exit(1)
        name = PLATFORM_NAMES.get(p, p)
        kws = db.get_keywords(p)
        if not kws:
            print(f"[{name}] 无关键词，跳过")
            continue
        kw_list = ", ".join(k["keyword"] for k in kws)
        print(f"[{name}] 启动监控 · 关键词: {kw_list}")
        m = create_monitor(p, db, notifier, log_cb=print)
        if m:
            monitors.append(m)

    if not monitors:
        print("[错误] 没有可监控的平台，请先添加关键词")
        sys.exit(1)

    async def _run():
        tasks = [asyncio.create_task(m.start()) for m in monitors]
        stop_event = asyncio.Event()

        def _signal_handler():
            print("\n[停止] 正在关闭所有监控...")
            stop_event.set()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _signal_handler)
            except NotImplementedError:
                pass

        try:
            await stop_event.wait()
        except KeyboardInterrupt:
            pass

        for m in monitors:
            m.stop()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for m in monitors:
            await m.cleanup()

        stop_bot_polling()
        print("[Bot] Telegram Bot命令服务已停止")
        print("[完成] 所有监控已停止")

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass


def main():
    parser = argparse.ArgumentParser(
        description="Mercari Monitor — 多平台二手商品实时监控"
    )
    parser.add_argument(
        "--headless", action="store_true",
        help="无 GUI 模式运行（适合服务器部署）"
    )
    parser.add_argument(
        "--platform", "-p", action="append", dest="platforms",
        help="指定监控平台（可多次使用），如 -p mercari_jp -p bunjang"
    )
    parser.add_argument(
        "--keyword", "-k", action="append", dest="keywords",
        help="添加关键词（格式: 关键词@平台），如 -k ナイキ@mercari_jp -k 나이키@bunjang"
    )
    args = parser.parse_args()

    if args.headless:
        run_headless(platforms=args.platforms, keywords=args.keywords)
    else:
        run_gui()


if __name__ == "__main__":
    main()