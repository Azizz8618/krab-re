#!/bin/sh
# Прогон наборов тестов КРАБ — каждый файл в своём процессе.
#
# Почему не одним процессом: все наборы работают под одним номером КРАБ
# (1234), у номера может быть только одна подчинённая задача, а линии ДКС
# не любят частых переподключений. Один pytest на все файлы оставляет
# состояние (номер на линии, занятая ПЗ), и следующий набор стартует
# «грязным». Отдельный процесс на файл — чистые сессии и предсказуемое время.
#
# Запуск: sh tests/run_all.sh
set -e

DIR=$(dirname "$0")
cd "$DIR"

# порядок от дешёвых к дорогим
FILES="test_krab_entry.py
test_krab_directives.py
test_krab_edit_form.py
test_krab_task_list.py"

TOTAL_START=$(date +%s)
FAILED=""

for f in $FILES; do
    START=$(date +%s)
    printf '\n=== %s ===\n' "$f"
    if python3 -u -m pytest "$f" -p no:cacheprovider -q; then
        printf '--- %s: OK (%ds)\n' "$f" "$(( $(date +%s) - START ))"
    else
        FAILED="$FAILED $f"
        printf '--- %s: СБОЙ (%ds)\n' "$f" "$(( $(date +%s) - START ))"
    fi
done

printf '\n=== итог за %ds ===\n' "$(( $(date +%s) - TOTAL_START ))"
if [ -n "$FAILED" ]; then
    printf 'с ошибками:%s\n' "$FAILED"
    exit 1
fi
printf 'все наборы прошли\n'