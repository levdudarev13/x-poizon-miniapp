"""Точка входа — запуск бота."""
import asyncio
import logging
import os
import sys
import warnings
warnings.filterwarnings("ignore", message=".*per_message.*", category=UserWarning)
from dotenv import load_dotenv
from telegram import MenuButtonWebApp, WebAppInfo
from telegram.ext import Application, MessageHandler, filters
from telegram.request import HTTPXRequest

_test_mode = "--test" in sys.argv
env_file = ".env.test" if _test_mode else ".env"
os.environ.setdefault("BOT_ENV_FILE", env_file)
load_dotenv(env_file)
if _test_mode:
    print(">>> ТЕСТОВЫЙ РЕЖИМ (.env.test) <<<")
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(stream=open(sys.stdout.fileno(), mode='w', encoding='utf-8', closefd=False))],
)
log = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

if not BOT_TOKEN:
    log.error("BOT_TOKEN не задан в .env")
    sys.exit(1)


async def on_startup(app: Application):
    import database as db
    await db.init_db()
    from config import MINI_APP_URL

    from services import exchange_rate as er
    rate = await er.get_rate()
    if rate:
        log.info(f"Курс: 1 CNY = {rate.cny_rub:.4f} RUB ({rate.age_human})")
    else:
        log.warning("Не удалось получить курс при старте")

    if MINI_APP_URL:
        try:
            await app.bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="Open Mini App",
                    web_app=WebAppInfo(url=MINI_APP_URL),
                )
            )
            log.info("Telegram menu button updated with current MINI_APP_URL")
        except Exception:
            log.exception("Failed to update Telegram menu button")


def main():
    request = HTTPXRequest(connect_timeout=30.0, read_timeout=60.0, write_timeout=60.0, media_write_timeout=120.0)
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .request(request)
        .post_init(on_startup)
        .build()
    )

    # ── Регистрация обработчиков ─────────────────────────────────────────
    from handlers.commands import build_command_handlers, handle_unexpected_message
    from handlers.conversation import build_conversation_handler
    from handlers.cart import build_cart_handlers
    from handlers.history import build_history_handlers
    from handlers.settings import build_settings_handlers
    from handlers.admin_orders import build_admin_orders_handlers, build_admin_carts_handlers, handle_admin_notify_text
    from handlers.messages import build_messages_conv_handler, build_messages_handlers
    from handlers.mode import build_mode_handlers
    from config import ADMIN_USER_IDS as _ADMIN_IDS

    # Команды (start, help) — регистрируем первыми
    for h in build_command_handlers():
        app.add_handler(h, group=0)

    # Ввод номеров товаров для уведомлений (admin) — group=0, до cart MessageHandler
    if _ADMIN_IDS:
        from telegram.ext import MessageHandler, filters
        app.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND & filters.User(user_id=list(_ADMIN_IDS)),
                handle_admin_notify_text,
            ),
            group=0,
        )

    # Корзина и история (независимые команды и коллбэки)
    for h in build_cart_handlers():
        app.add_handler(h, group=1)
    for h in build_history_handlers():
        app.add_handler(h, group=1)
    # Заявки (admin) — в group=1
    for h in build_admin_orders_handlers():
        app.add_handler(h, group=1)
    # Просмотр корзин (admin) — в group=1
    for h in build_admin_carts_handlers():
        app.add_handler(h, group=1)
    # Настройки — в group=3, чтобы текстовый хендлер не конфликтовал с корзиной
    for h in build_settings_handlers():
        app.add_handler(h, group=3)

    # Главный диалоговый поток (group=2, после команд)
    app.add_handler(build_conversation_handler(), group=2)

    # Поток сообщений пользователей (group=5) + независимые callback-хендлеры (group=1)
    app.add_handler(build_messages_conv_handler(), group=5)
    for h in build_messages_handlers():
        app.add_handler(h, group=1)

    # Переключение режима (group=1)
    for h in build_mode_handlers():
        app.add_handler(h, group=1)


    async def error_handler(update, context):
        import traceback
        log.error("Unhandled exception:\n%s", "".join(traceback.format_exception(type(context.error), context.error, context.error.__traceback__)))

    app.add_error_handler(error_handler)

    log.info("Бот запускается…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    # Защита от запуска нескольких экземпляров
    import tempfile, atexit
    _lock_path = os.path.join(tempfile.gettempdir(), "buyer_bot.lock")
    try:
        _lock_f = open(_lock_path, "x")
        _lock_f.write(str(os.getpid()))
        _lock_f.flush()
        atexit.register(lambda: os.unlink(_lock_path))
    except FileExistsError:
        # Проверяем, жив ли процесс из lock-файла
        try:
            with open(_lock_path) as _lf:
                _old_pid = int(_lf.read().strip())
            import psutil
            if psutil.pid_exists(_old_pid):
                log.error(f"Бот уже запущен (PID {_old_pid}). Завершение.")
                sys.exit(1)
            else:
                # Старый процесс мёртв — перезаписываем lock
                os.unlink(_lock_path)
                _lock_f = open(_lock_path, "x")
                _lock_f.write(str(os.getpid()))
                _lock_f.flush()
                atexit.register(lambda: os.unlink(_lock_path))
        except Exception:
            os.unlink(_lock_path)

    # Windows: нужен SelectorEventLoop для aiosqlite
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    main()
