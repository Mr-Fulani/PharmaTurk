#!/bin/bash

# Скрипт для перезапуска проекта PharmaTurk
# Использование: ./restart.sh [опции]
#
# Опции:
#   --clean          - Удалить volumes (база данных будет очищена)
#   --no-cache       - Пересобрать образы без кэша
#   --rebuild        - Полная пересборка (--clean + --no-cache)
#   --no-prune       - Не очищать неиспользуемые Docker ресурсы
#   --logs           - Показать логи после запуска
#   --help           - Показать справку

set -e  # Остановить при ошибке

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
    --help           Показать эту справку

Примеры:
    ./restart.sh                    # Обычный перезапуск
    ./restart.sh --no-cache         # Пересборка без кэша
    ./restart.sh --clean            # С очисткой базы данных
    ./restart.sh --rebuild --logs   # Полная пересборка с логами

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

info "Начинаем перезапуск проекта PharmaTurk..."

# Остановка контейнеров
info "Останавливаем контейнеры..."
docker compose down

# Удаление volumes (если указано)
if [ "$CLEAN_VOLUMES" = true ]; then
    warning "Удаляем volumes (база данных будет очищена!)"
    read -p "Вы уверены? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker compose down -v
        success "Volumes удалены"
    else
        info "Отменено пользователем"
        exit 0
    fi
fi

# Очистка неиспользуемых Docker ресурсов (по умолчанию включена)
if [ "$NO_PRUNE" = false ]; then
    info "Очищаем неиспользуемые Docker ресурсы..."
    PRUNED=$(docker system prune -a --volumes -f 2>&1 | grep -i "reclaimed" || echo "")
    if [ -n "$PRUNED" ]; then
        success "Очистка завершена: $PRUNED"
    else
        success "Очистка завершена (неиспользуемых ресурсов не найдено)"
    fi
else
    info "Пропускаем очистку неиспользуемых ресурсов (--no-prune)"
fi

# Дополнительная очистка при --no-cache
if [ "$NO_CACHE" = true ]; then
    info "Выполняем дополнительную очистку build cache..."
    docker builder prune -af --filter "until=24h" > /dev/null 2>&1 || true
    success "Build cache очищен"
fi

# Пересборка образов
info "Пересобираем Docker образы..."
if [ "$NO_CACHE" = true ]; then
    docker compose build --no-cache
else
    docker compose build
fi
success "Образы пересобраны"

# Запуск контейнеров
info "Запускаем контейнеры..."
docker compose up -d
success "Контейнеры запущены"

# Ожидание готовности сервисов
info "Ожидаем готовности сервисов..."
sleep 5

# Проверка статуса
info "Проверяем статус контейнеров..."
docker compose ps

# Ожидание готовности базы данных
info "Ожидаем готовности базы данных..."
for i in {1..30}; do
    if docker compose exec -T postgres pg_isready -U pharmaturk > /dev/null 2>&1; then
        success "База данных готова"
        break
    fi
    if [ $i -eq 30 ]; then
        warning "База данных не готова после 30 попыток"
    else
        sleep 1
    fi
done

# Создание и применение миграций Django
info "Создаем и применяем миграции Django..."
if docker compose ps backend | grep -q "Up"; then
    if docker compose exec -T backend poetry run python manage.py makemigrations; then
        success "Миграции созданы (если были изменения моделей)"
    else
        warning "Ошибка при создании миграций (возможно, контейнер еще не готов)"
    fi
    if docker compose exec -T backend poetry run python manage.py migrate --noinput; then
        success "Миграции применены"
    else
        warning "Ошибка при применении миграций (возможно, контейнер еще не готов)"
    fi
else
    warning "Backend контейнер не запущен, миграции не созданы и не применены"
fi

# Показ логов (если указано)
if [ "$SHOW_LOGS" = true ]; then
    info "Показываем логи (Ctrl+C для выхода)..."
    docker compose logs -f
else
    info "Для просмотра логов используйте: docker compose logs -f"
fi

success "Проект успешно перезапущен!"
info ""
info "Доступные сервисы:"
info "  - Backend API:    http://localhost:8000"
info "  - Frontend:       http://localhost:3001"
info "  - Admin Panel:    http://localhost:8000/admin/"
info "  - Swagger Docs:   http://localhost:8000/api/docs/"
info "  - PostgreSQL:     localhost:5433"
info "  - Redis:          localhost:6379"
info "  - OpenSearch:     localhost:9200"
info ""
info "Hot-reload включен:"
info "  - Изменения в backend и frontend подхватываются автоматически"
info "  - Backend использует runserver (автоперезагрузка при изменении .py файлов)"
info "  - Frontend использует Next.js dev server (hot-reload для React компонентов)"

