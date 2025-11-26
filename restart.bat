@echo off
REM Скрипт для перезапуска проекта PharmaTurk (Windows)
REM Использование: restart.bat [опции]
REM
REM Опции:
REM   --clean          - Удалить volumes (база данных будет очищена)
REM   --no-cache       - Пересобрать образы без кэша
REM   --rebuild        - Полная пересборка (--clean + --no-cache)
REM   --logs           - Показать логи после запуска
REM   --help           - Показать справку

setlocal enabledelayedexpansion

set CLEAN_VOLUMES=0
set NO_CACHE=0
set SHOW_LOGS=0

REM Парсинг аргументов
:parse_args
if "%~1"=="" goto end_parse
if "%~1"=="--clean" (
    set CLEAN_VOLUMES=1
    shift
    goto parse_args
)
if "%~1"=="--no-cache" (
    set NO_CACHE=1
    shift
    goto parse_args
)
if "%~1"=="--rebuild" (
    set CLEAN_VOLUMES=1
    set NO_CACHE=1
    shift
    goto parse_args
)
if "%~1"=="--logs" (
    set SHOW_LOGS=1
    shift
    goto parse_args
)
if "%~1"=="--help" (
    goto show_help
)
echo Неизвестная опция: %~1
echo Используйте --help для справки
exit /b 1

:end_parse

echo Начинаем перезапуск проекта PharmaTurk...

REM Остановка контейнеров
echo Останавливаем контейнеры...
docker compose down

REM Удаление volumes (если указано)
if %CLEAN_VOLUMES%==1 (
    echo.
    echo ВНИМАНИЕ: Будет удалена база данных!
    set /p CONFIRM="Вы уверены? (y/N): "
    if /i "!CONFIRM!"=="y" (
        docker compose down -v
        echo Volumes удалены
    ) else (
        echo Отменено пользователем
        exit /b 0
    )
)

REM Очистка кэша (если указано)
if %NO_CACHE%==1 (
    echo Очищаем неиспользуемые образы...
    docker system prune -f
    echo Кэш очищен
)

REM Пересборка образов
echo Пересобираем Docker образы...
if %NO_CACHE%==1 (
    docker compose build --no-cache
) else (
    docker compose build
)
echo Образы пересобраны

REM Запуск контейнеров
echo Запускаем контейнеры...
docker compose up -d
echo Контейнеры запущены

REM Ожидание готовности
echo Ожидаем готовности сервисов...
timeout /t 5 /nobreak >nul

REM Проверка статуса
echo Проверяем статус контейнеров...
docker compose ps

REM Показ логов (если указано)
if %SHOW_LOGS%==1 (
    echo Показываем логи (Ctrl+C для выхода)...
    docker compose logs -f
) else (
    echo Для просмотра логов используйте: docker compose logs -f
)

echo.
echo Проект успешно перезапущен!
echo.
echo Доступные сервисы:
echo   - Backend API:    http://localhost:8000
echo   - Frontend:       http://localhost:3001
echo   - Admin Panel:    http://localhost:8000/admin/
echo   - Swagger Docs:   http://localhost:8000/api/docs/
echo   - PostgreSQL:     localhost:5433
echo   - Redis:          localhost:6379
echo   - OpenSearch:     localhost:9200

exit /b 0

:show_help
echo Скрипт для перезапуска проекта PharmaTurk
echo.
echo Использование:
echo     restart.bat [опции]
echo.
echo Опции:
echo     --clean          Удалить volumes (база данных будет очищена!)
echo     --no-cache       Пересобрать образы без кэша Docker
echo     --rebuild        Полная пересборка (--clean + --no-cache)
echo     --logs           Показать логи после запуска
echo     --help           Показать эту справку
echo.
echo Примеры:
echo     restart.bat                    # Обычный перезапуск
echo     restart.bat --no-cache         # Пересборка без кэша
echo     restart.bat --clean            # С очисткой базы данных
echo     restart.bat --rebuild --logs   # Полная пересборка с логами
exit /b 0

