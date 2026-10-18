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
# Каждый КЛАСС — отдельный процесс, а не только каждый файл: в общем
# прогоне набора правки падали только классы, идущие последними (18 из 24,
# хотя каждый из них по отдельности проходит 8/8). Причина — состояние
# машины накапливается по ходу прогона; разбивка по классам обнуляет его.
CLASSES="test_krab_entry.py
test_krab_directives.py::Directives
test_krab_directives.py::SchoolBlock
test_krab_edit_form.py::EditTextFile
test_krab_edit_form.py::RedEditing
test_krab_edit_form.py::EditingDirectives
test_krab_output.py::OutputDirectives
test_krab_output.py::MacDirective
test_krab_output.py::AcpuPrint
test_krab_task_list.py
test_vvod_zka.py"

# Перед прогоном — освободить сбойные зоны номера. Файлы тестов живут на
# них после сеанса, и при исчерпании комплекта ИМЯ отвечает
# «НЕТ ЗОН ДЛЯ УПРЯТ»: тесты падают ещё до своих проверок. Чистка идёт
# одной сессией (пара ИМЯ X / ИМЯ X на каждый файл). Пропустить:
#   KRAB_SKIP_SBO_CLEAN=1 sh tests/run_all.sh
if [ "${KRAB_SKIP_SBO_CLEAN:-0}" != "1" ]; then
    printf '=== очистка сбойных зон ===
'
    python3 -u ../tools/clear_sbo.py --rounds 40 || \
        printf 'не удалось очистить сбойные зоны — наборы могут упасть на ИМЯ
'
fi

TOTAL_START=$(date +%s)
FAILED=""

for f in $CLASSES; do
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