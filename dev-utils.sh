#!/bin/bash

# Утилиты для разработки PharmaTurk
# Использование: source dev-utils.sh или . dev-utils.sh

# Цвета
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Функции для работы с проектом

# Перезапуск backend
restart_backend() {
    echo -e "${BLUE}Перезапускаем backend...${NC}"
    docker compose restart backend
    echo -e "${GREEN}Backend перезапущен${NC}"
}

# Перезапуск frontend
restart_frontend() {
    echo -e "${BLUE}Перезапускаем frontend...${NC}"
    docker compose restart frontend
    echo -e "${GREEN}Frontend перезапущен${NC}"
}

# Показать логи
logs() {
    local service=${1:-""}
    if [ -z "$service" ]; then
        docker compose logs -f
    else
        docker compose logs -f "$service"
    fi
}

# Выполнить команду в backend контейнере
backend_exec() {
    docker compose exec backend "$@"
}

# Выполнить команду в frontend контейнере
frontend_exec() {
    docker compose exec frontend "$@"
}

# Django команды
manage() {
    docker compose exec backend poetry run python manage.py "$@"
}

# Создать миграции
makemigrations() {
    manage makemigrations "$@"
}

# Применить миграции
migrate() {
    manage migrate "$@"
}

# Создать суперпользователя
createsuperuser() {
    manage createsuperuser
}

# Django shell
shell() {
    manage shell
}

# Собрать статику
collectstatic() {
    manage collectstatic --noinput
}

# Показать статус контейнеров
status() {
    docker compose ps
}

# Очистить кэш Python
clear_python_cache() {
    echo -e "${BLUE}Очищаем кэш Python...${NC}"
    find . -type d -name __pycache__ -exec rm -r {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete 2>/dev/null || true
    find . -type f -name "*.pyo" -delete 2>/dev/null || true
    echo -e "${GREEN}Кэш Python очищен${NC}"
}

# Очистить кэш Next.js
clear_next_cache() {
    echo -e "${BLUE}Очищаем кэш Next.js...${NC}"
    rm -rf frontend/.next 2>/dev/null || true
    rm -rf frontend/node_modules/.cache 2>/dev/null || true
    echo -e "${GREEN}Кэш Next.js очищен${NC}"
}

# Очистить все кэши
clear_all_cache() {
    clear_python_cache
    clear_next_cache
    echo -e "${BLUE}Очищаем Docker кэш...${NC}"
    docker system prune -f
    echo -e "${GREEN}Все кэши очищены${NC}"
}

# Показать использование дискового пространства
disk_usage() {
    echo -e "${BLUE}Использование дискового пространства:${NC}"
    docker system df
}

# Показать справку
show_dev_help() {
    cat << EOF
${GREEN}Утилиты для разработки PharmaTurk${NC}

${BLUE}Основные команды:${NC}
  restart_backend          - Перезапустить backend
  restart_frontend          - Перезапустить frontend
  logs [service]            - Показать логи (всех или конкретного сервиса)
  status                    - Показать статус контейнеров

${BLUE}Django команды:${NC}
  manage <command>          - Выполнить manage.py команду
  makemigrations [app]      - Создать миграции
  migrate                   - Применить миграции
  createsuperuser           - Создать суперпользователя
  shell                     - Открыть Django shell
  collectstatic             - Собрать статику

${BLUE}Очистка:${NC}
  clear_python_cache        - Очистить кэш Python
  clear_next_cache          - Очистить кэш Next.js
  clear_all_cache           - Очистить все кэши

${BLUE}Другое:${NC}
  backend_exec <command>    - Выполнить команду в backend контейнере
  frontend_exec <command>   - Выполнить команду в frontend контейнере
  disk_usage                - Показать использование дискового пространства

${YELLOW}Примеры:${NC}
  . dev-utils.sh
  logs backend
  makemigrations users
  migrate
  shell
  clear_all_cache

EOF
}

# Показать справку при загрузке
if [ "${BASH_SOURCE[0]}" != "${0}" ]; then
    # Скрипт загружен через source
    echo -e "${GREEN}Утилиты для разработки загружены!${NC}"
    echo -e "Используйте ${BLUE}show_dev_help${NC} для справки"
fi

