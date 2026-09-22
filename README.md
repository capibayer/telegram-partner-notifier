# Telegram Partner Notifier

Минимальный Telegram-бот для массовой рассылки уведомлений партнерам по email, привязанному к названию Telegram-чата.

## Установка

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Заполните `.env` значениями:

```env
BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
MANAGER_IDS=123456789,987654321
```

## Запуск

```bash
python bot.py
```

## Основные возможности

- автоматическое распознавание email в названии чата;
- хранение связи email → chat_id в SQLite;
- кнопочная панель менеджера: рассылка, чаты, история и помощь;
- история последних десяти рассылок с датой и результатами доставки;
- выдача и отзыв доступа дополнительным менеджерам через кнопку «Менеджеры»;
- владельцы из `MANAGER_IDS` управляют правами, а выданные права хранятся в SQLite;
- многоступенчатый сценарий рассылки с подтверждением;
- логирование и состояние диалога.

## Доступ менеджеров

Пользователи из `MANAGER_IDS` в `.env` являются владельцами. После запуска они получают
кнопку «Менеджеры»: через неё можно выдать доступ по числовому Telegram ID или отозвать
выданный ранее доступ. Новый менеджер должен открыть личный чат с ботом и отправить `/start`
один раз, после чего увидит кнопочную панель.

## Постоянный запуск на macOS

Конфигурация [deploy/com.rocketprofit.partner-notifier.plist](deploy/com.rocketprofit.partner-notifier.plist)
запускает бота после входа в macOS и автоматически перезапускает его при сбое. Установите её:

```bash
cd /Users/rocketprofit/Projects/telegram_partner_notifier
mkdir -p logs
cp deploy/com.rocketprofit.partner-notifier.plist ~/Library/LaunchAgents/
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.rocketprofit.partner-notifier.plist 2>/dev/null || true
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.rocketprofit.partner-notifier.plist
```

Проверка статуса:

```bash
launchctl print gui/$(id -u)/com.rocketprofit.partner-notifier
```

Аватар для Telegram находится в [assets/rocketprofit-avatar.svg](assets/rocketprofit-avatar.svg)
и [assets/rocketprofit-avatar.png](assets/rocketprofit-avatar.png).

## Railway

Проект подготовлен для Railway через Dockerfile. После импорта репозитория в Railway:

1. В разделе Variables задайте `BOT_TOKEN` и `MANAGER_IDS`.
2. Добавьте Volume и подключите его по пути `/data`.
3. Оставьте `DATA_DIR=/data`.

Токен нельзя добавлять в GitHub или файл `.env.example`.
