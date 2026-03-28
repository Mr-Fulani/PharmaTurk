#!/bin/bash

# Переход в директорию скрипта (чтобы docker compose находил docker-compose.yml)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Явное имя проекта — чтобы restart.sh и docker compose up/logs в другом терминале работали с одними контейнерами
# Подгружаем .env чтобы скрипт видел переменные (например COMPOSE_FILE)
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Имя проекта
export COMPOSE_PROJECT_NAME=mudaroba
# Если COMPOSE_FILE не задан в .env или окружении, используем базу + локальный override (стандартное поведение Docker Compose)
if [ -z "$COMPOSE_FILE" ]; then
    COMPOSE_FILE="docker-compose.yml"
    # Добавляем override только если он существует (стандарт Docker)
    if [ -f "docker-compose.override.yml" ]; then
        COMPOSE_FILE="${COMPOSE_FILE}:docker-compose.override.yml"
    fi
fi

# Превращаем строку с двоеточиями в массив флагов -f для командной строки
COMPOSE_FLAGS=""
IFS=':' read -ra ADDR <<< "$COMPOSE_FILE"
for i in "${ADDR[@]}"; do
    COMPOSE_FLAGS="$COMPOSE_FLAGS -f $i"
done

# Скрипт для перезапуска проекта PharmaTurk
# Использование: ./restart.sh [опции]
#
# Опции:
#   --clean          - Удалить volumes (база данных будет очищена)
#   --no-cache       - Пересобрать образы без кэша
#   --rebuild        - Полная пересборка (--clean + --no-cache)
#   --no-prune       - Не очищать неиспользуемые Docker ресурсы
#   --logs           - Показать логи после запуска
#   --fast, --quick  - Быстрый перезапуск: только stop + up без пересборки и prune (рекомендуется для повседневного рестарта)
#   --fast-rebuild   - Быстрая пересборка только frontend и backend (больше чем --fast, но быстрее чем полная сборка)
#   --help           - Показать справку

# set -e  # Отключено, чтобы скрипт продолжал работу даже если контейнеры не запущены

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Флаги
CLEAN_VOLUMES=false
NO_CACHE=false
SHOW_LOGS=false
NO_PRUNE=false
FAST=false
FAST_REBUILD=false

# Функция для вывода сообщений
info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

success() {
    echo -e "${GREEN}✓${NC} $1"
}

warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

error() {
    echo -e "${RED}✗${NC} $1"
}

# Функция справки
show_help() {
    cat << EOF
Скрипт для перезапуска проекта PharmaTurk

Использование:
    ./restart.sh [опции]

Опции:
    --clean          Удалить volumes (база данных будет очищена!)
    --no-cache       Пересобрать образы без кэша Docker
    --rebuild        Полная пересборка (--clean + --no-cache)
    --no-prune       Не очищать неиспользуемые Docker ресурсы (по умолчанию очистка включена)
    --logs           Показать логи после запуска
    --fast, --quick  Быстрый перезапуск: только остановка и запуск контейнеров, без пересборки и prune (для повседневного рестарта)
    --fast-rebuild   Быстрая пересборка только frontend и backend (быстрее, чем полная пересборка всех сервисов)
    --help           Показать эту справку

Примеры:
    ./restart.sh --quick --logs     # Быстрый перезапуск с логами (рекомендуется для повседневного рестарта)
    ./restart.sh --fast             # То же, что --quick (без логов)
    ./restart.sh                    # Обычный перезапуск (с пересборкой)
    ./restart.sh --no-cache         # Пересборка без кэша
    ./restart.sh --clean            # С очисткой базы данных
    ./restart.sh --rebuild --logs   # Полная пересборка с логами
    ./restart.sh --fast-rebuild     # Пересобрать только frontend и backend

EOF
}

# Парсинг аргументов
while [[ $# -gt 0 ]]; do
    case $1 in
        --clean)
            CLEAN_VOLUMES=true
            shift
            ;;
        --no-cache)
            NO_CACHE=true
            shift
            ;;
        --rebuild)
            CLEAN_VOLUMES=true
            NO_CACHE=true
            shift
            ;;
        --no-prune)
            NO_PRUNE=true
            shift
            ;;
        --logs)
            SHOW_LOGS=true
            shift
            ;;
        --fast|--quick)
            FAST=true
            shift
            ;;
        --fast-rebuild)
            FAST_REBUILD=true
            shift
            ;;
        --help|-h)
            show_help
            exit 0
            ;;
        *)
            error "Неизвестная опция: $1"
            echo "Используйте --help для справки"
            exit 1
            ;;
    esac
done

# Проверка наличия docker-compose
if ! command -v docker &> /dev/null; then
    error "Docker не установлен или не найден в PATH"
    exit 1
fi

if ! command -v docker compose &> /dev/null; then
    error "Docker Compose не установлен или не найден в PATH"
    exit 1
fi

info "Начинаем перезапуск проекта Mudaroba..."

# КАПИТАЛЬНАЯ ОЧИСТКА КЭША ПЕРЕД ОСТАНОВКОЙ
info "🧹 Очищаем весь кэш перед перезапуском..."
# Очистка кэша Next.js (с обработкой ошибок прав доступа)
if [ -d "frontend/.next" ]; then
    rm -rf frontend/.next 2>/dev/null || sudo rm -rf frontend/.next 2>/dev/null || true
    success "Кэш Next.js (.next) очищен"
fi
if [ -d "frontend/node_modules/.cache" ]; then
    rm -rf frontend/node_modules/.cache 2>/dev/null || sudo rm -rf frontend/node_modules/.cache 2>/dev/null || true
    success "Кэш node_modules очищен"
fi
# Очистка кэша Python
find backend -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find backend -type f -name "*.pyc" -delete 2>/dev/null || true
find backend -type f -name "*.pyo" -delete 2>/dev/null || true
success "Кэш Python очищен"
# Остановка контейнеров (всегда выполняем down — идемпотентно, если контейнеры не запущены)
info "Останавливаем контейнеры..."
if [ "$CLEAN_VOLUMES" = true ]; then
    warning "Удаляем volumes (база данных будет очищена!)"
    read -p "Вы уверены? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker compose -p pharmaturk $COMPOSE_FLAGS down -v --remove-orphans || true
        success "Контейнеры остановлены и volumes удалены"
    else
        info "Отменено пользователем"
        exit 0
    fi
else
    docker compose -p pharmaturk $COMPOSE_FLAGS down -t 1 --remove-orphans || true
        success "Контейнеры остановлены"
fi

# Docker compose up и logs -f в других терминалах не завершаются при down — отправляем SIGTERM.
# Часто запускают ./restart.sh --fast --logs: в первом терминале остаётся logs -f от прошлого запуска.
pkill -TERM -f "docker compose.* up" 2>/dev/null || true
pkill -TERM -f "docker compose.* logs" 2>/dev/null || true
pkill -TERM -f "docker-compose.* up" 2>/dev/null || true
pkill -TERM -f "docker-compose.* logs" 2>/dev/null || true

# Пауза: даём процессам время завершиться
sleep 3

# Очистка неиспользуемых Docker ресурсов (по умолчанию включена)
if [ "$NO_PRUNE" = false ] && [ "$FAST" = false ]; then
    info "Очищаем неиспользуемые Docker ресурсы..."
    PRUNED=$(docker system prune -a --volumes -f 2>&1 | grep -i "reclaimed" || echo "")
    if [ -n "$PRUNED" ]; then
        success "Очистка завершена: $PRUNED"
    else
        success "Очистка завершена (неиспользуемых ресурсов не найдено)"
    fi
else
    if [ "$FAST" = true ]; then
        info "FAST режим: пропускаем очистку docker system prune"
    else
        info "Пропускаем очистку неиспользуемых ресурсов (--no-prune)"
    fi
fi

# Дополнительная очистка при --no-cache
if [ "$NO_CACHE" = true ]; then
    info "Выполняем дополнительную очистку build cache..."
    docker builder prune -af --filter "until=24h" > /dev/null 2>&1 || true
    success "Build cache очищен"
fi

# Пересборка образов
info "Пересобираем Docker образы..."
# Логика сборки:
# - если указан --fast: пропускаем сборку (используем ранее собранные образы)
# - если указан --fast-rebuild: пересобираем только backend и frontend (быстрее полной сборки)
# - если указан --no-cache: пересобираем все образы без кэша
# - иначе: обычная полная сборка
if [ "$FAST" = true ] && [ "$FAST_REBUILD" = false ]; then
    info "FAST режим: пропускаем пересборку образов"
elif [ "$FAST_REBUILD" = true ]; then
    info "FAST-REBUILD: пересобираем backend и frontend"
    docker compose -p pharmaturk $COMPOSE_FLAGS build backend frontend || warning "Ошибка при быстрой пересборке backend/frontend"
elif [ "$NO_CACHE" = true ]; then
    docker compose -p pharmaturk $COMPOSE_FLAGS build --no-cache || warning "Ошибка при сборке образов без кэша"
else
    docker compose -p pharmaturk $COMPOSE_FLAGS build || warning "Ошибка при сборке образов"
fi

if [ "$FAST" = false ]; then
    success "Образы обработаны (при необходимости пересобраны)"
else
    success "FAST: пересборка пропущена"
fi

# Запуск контейнеров
info "Запускаем контейнеры..."
UP_OPTS="-d"
if [ "$FAST" = true ] && [ "$FAST_REBUILD" = false ]; then
    UP_OPTS="-d --no-build"
fi
docker compose -p pharmaturk $COMPOSE_FLAGS up $UP_OPTS
success "Контейнеры запущены"

# Краткая пауза: backend уже ждёт postgres (healthcheck), миграции выполняет entrypoint
info "Проверяем статус контейнеров..."
sleep 2
docker compose -p pharmaturk $COMPOSE_FLAGS ps

# AI RAG: подготовка Qdrant (опционально, при первом запуске или после добавления категорий/шаблонов)
# Раскомментируйте следующую строку, чтобы один раз заполнить RAG после старта:
# docker compose exec -T backend poetry run python manage.py setup_ai_rag

# Показ логов (если указано)
if [ "$SHOW_LOGS" = true ]; then
    info "Показываем логи (Ctrl+C для выхода)..."
    docker compose -p pharmaturk $COMPOSE_FLAGS logs -f
else
    info "Для просмотра логов используйте: docker compose logs -f"
    info ""
    info "Чтобы restart.sh останавливал логи в другом терминале, в терминале 1 запускайте из корня проекта:"
    info "  cd $SCRIPT_DIR && docker compose up"
    info "  или:  cd $SCRIPT_DIR && docker compose logs -f"
fi

success "Проект успешно перезапущен!"
info ""
info "Доступные сервисы:"
info "  - Backend API:    http://localhost:8000 (или ваш домен)"
info "  - Frontend:       $(if [[ "$COMPOSE_FILE" == *"prod"* ]]; then echo "http://localhost:80 (или ваш домен)"; else echo "http://localhost:3001"; fi)"
info "  - Admin Panel:    http://localhost:8000/admin/"
info "  - Swagger Docs:   http://localhost:8000/api/docs/"
info ""
info "  - PostgreSQL:     localhost:5433"
info "  - Redis:          localhost:6379"
info "  - OpenSearch:     localhost:9200"
info "  - Qdrant (AI):    localhost:6333"
info ""
info "Команды Django в Docker (запускать после старта контейнеров):"
info "  docker compose exec backend poetry run python manage.py <команда>"
info "  Примеры:"
info "    docker compose exec backend poetry run python manage.py seed_catalog_data  # категории и бренды (после потери БД)"
info "    docker compose exec backend poetry run python manage.py setup_ai_rag   # подготовка RAG (Qdrant)"
info "    docker compose exec backend poetry run python manage.py init_qdrant   # только коллекции Qdrant"
info "    docker compose exec backend poetry run python manage.py sync_categories"
info "    docker compose exec backend poetry run python manage.py import_templates"
info "    docker compose exec backend poetry run python manage.py benchmark_ai 5 # тест AI на 5 товарах"
info ""
info "Hot-reload включен:"
info "  - Backend: runserver (автоперезагрузка при изменении .py)"
info "  - Frontend: Next.js dev server (hot-reload для React)"
