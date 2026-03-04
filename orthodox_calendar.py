#!/usr/bin/env python3
"""
Скрипт расчёта православных праздников и постов, выгрузка в два .ics-файла:
- orthodox_feasts.ics — праздники,
- orthodox_fasts.ics — посты (продолжительные, однодневные, ср/пт).

На вход: начальный год и конечный год (включительно).
"""

from datetime import date, timedelta, datetime
import os

try:
    from dateutil.easter import easter, EASTER_ORTHODOX

    def orthodox_easter(year: int) -> date:
        """Расчёт даты православной Пасхи (через dateutil)."""
        return easter(year, method=EASTER_ORTHODOX)
except ImportError:

    def orthodox_easter(year: int) -> date:
        """
        Расчёт даты православной Пасхи по юлианскому календарю.
        Резервный вариант без dateutil. Корректно для 1900-2099.
        """
        a, b, c = year % 4, year % 7, year % 19
        d = (19 * c + 15) % 30
        e = (2 * a + 4 * b - d + 34) % 7
        f = d + e + 114
        day = (f % 31) + 1
        month = f // 31
        jd = date(year, month, day)
        q = 10 + ((year // 100 - 15) * 3) // 4  # григорианская поправка
        return jd + timedelta(days=q)


def _dates_in_range(start: date, end: date):
    """Все даты в диапазоне [start, end] включительно."""
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def format_week_range(monday: date) -> str:
    """Форматирует неделю как 'Пн ДД.ММ - Вс ДД.ММ'."""
    sunday = monday + timedelta(days=6)
    return f"{monday.strftime('%d.%m')} - {sunday.strftime('%d.%m')}"


def _escape_ical_text(text: str) -> str:
    """Экранирует текст для полей iCalendar (RFC 5545): \\ \\; \\, и переносы -> \\n."""
    # Сохраняем \\n (намеренный перенос), иначе replace("\\\\") превратит в \\\\n
    text = text.replace("\\n", "\x00")  # placeholder
    text = text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    return text.replace("\x00", "\\n")


def make_ics_event(uid: str, start: date, end: date, summary: str, description: str = "") -> str:
    """
    Создаёт один VEVENT в формате iCalendar.

    start / end — включительно (для много-дневных событий).
    В iCalendar DTEND для целодневных событий указывает на день «после» конца,
    поэтому тут добавляем +1 день.
    """
    dtstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    dtstart = start.strftime("%Y%m%d")
    dtend = (end + timedelta(days=1)).strftime("%Y%m%d")

    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{dtstamp}",
        f"DTSTART;VALUE=DATE:{dtstart}",
        f"DTEND;VALUE=DATE:{dtend}",
        f"SUMMARY:{_escape_ical_text(summary)}",
    ]
    if description:
        lines.append(f"DESCRIPTION:{_escape_ical_text(description)}")
    lines.append("END:VEVENT")
    return "\r\n".join(lines) + "\r\n"


def _emit_spans(
    fast_events: list[str],
    year: int,
    prefix: str,
    day_rules: list[tuple[date, str, str]],
    ev_counter: list[int],
) -> None:
    """Объединяет последовательные дни с одинаковым правилом в одно событие."""
    i = 0
    while i < len(day_rules):
        d_start, s, desc = day_rules[i]
        j = i + 1
        while j < len(day_rules) and day_rules[j][1] == s and day_rules[j][2] == desc:
            j += 1
        d_end = day_rules[j - 1][0]
        ev_counter[0] += 1
        fast_events.append(make_ics_event(f"{year}-{prefix}-{ev_counter[0]}@orthodox-fasts", d_start, d_end, s, desc))
        i = j


def write_ics_file(events: list[str], filename: str) -> None:
    """Записывает список VEVENT в .ics-файл."""
    # Удаляем старый файл, если есть
    try:
        if os.path.exists(filename):
            os.remove(filename)
    except OSError:
        pass

    header = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Andrey//Orthodox OrthodoxCalendar//RU",
    ]
    footer = ["END:VCALENDAR"]
    content = "\r\n".join(header) + "\r\n" + "".join(events) + "".join(f + "\r\n" for f in footer)

    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)


def main():
    start_year = int(input("Начальный год: "))
    end_year = int(input("Конечный год: "))

    if start_year > end_year:
        start_year, end_year = end_year, start_year

    # Степени строгости постов: (название, описание). Строгие посты — отдельно.
    FAST_TYPES = {
        "post": ("Пост", "Постный день (без мясного, молочки и яиц)\nhttps://azbyka.ru/recept/\nhttps://azbyka.ru/days/p-posty-v-sredu-i-pjatnitsu"),
        "fish": ("Рыба", "Без мясного, молочки и яиц\nhttps://azbyka.ru/recept/"),
        "fish_roe": ("Рыбная икра", "Горячая пища с растительным маслом + рыбная икра\nhttps://azbyka.ru/recept/"),
        "no_oil": ("Без масла", "Горячая пища без масла\nhttps://azbyka.ru/recept/"),
        "with_oil": ("С маслом", "Горячая пища с растительным маслом\nhttps://azbyka.ru/recept/"),
        "dry": ("Сухоядение", "Холодная пища (вода, хлеб, фрукты, овощи, компоты)\nhttps://azbyka.ru/recept/osnovy-suhojadenija/\nhttps://azbyka.ru/suxoyadenie"),
    }

    # Неподвижные праздники (по новому стилю)
    fixed_feasts = [
        (
            "Рождество",
            1,
            7,
            "Рождество Господа Бога и Спаса нашего Иисуса Христа",
        ),
        (
            "По пло́ти обре́зание",
            1,
            14,
            "По пло́ти обре́зание Господа Бога и Спасителя нашего Иисуса Христа",
        ),
        (
            "Крещение",
            1,
            19,
            "Святое Богоявление. Крещение Господа Бога и Спаса нашего Иисуса Христа",
        ),
        (
            "Сретение Господне",
            2,
            15,
            "Сретение Господа Бога и Спаса нашего Иисуса Христа",
        ),
        (
            "Благовещение Пресвятой Богородицы",
            4,
            7,
            "Великий Вторник",
        ),
        (
            "Рождество Пророка Иоанна",
            7,
            7,
            "Рождество честно́го славного Пророка, Предтечи и Крестителя Господня Иоанна",
        ),
        (
            "Славных Петра и Павла",
            7,
            12,
            "Славных и всехвальных первоверховных апостолов Петра и Павла",
        ),
        (
            "Преображение Господне",
            8,
            19,
            "Преображение Господа Бога и Спаса нашего Иисуса Христа",
        ),
        (
            "Успение Богородицы",
            8,
            28,
            "Успение Пресвятой Владычицы нашей Богородицы и Приснодевы Марии",
        ),
        (
            "Усекновение Пророка Иоанна",
            9,
            11,
            "Усекновение главы Пророка, Предтечи и Крестителя Господня Иоанна",
        ),
        (
            "Рождество Богородицы",
            9,
            21,
            "Рождество Пресвятой Владычицы нашей Богородицы и Приснодевы Марии",
        ),
        (
            "Воздви́жение Креста Господня",
            9,
            27,
            "Воздви́жение Честно́го и Животворящего Креста Господня",
        ),
        (
            "Покров Богородицы",
            10,
            14,
            "Покров Пресвятой Владычицы нашей Богородицы и Приснодевы Марии",
        ),
        (
            "Введение во Храм Богородицы",
            12,
            4,
            "Введение (Вход) во Храм Пресвятой Владычицы нашей Богородицы и Приснодевы Марии",
        ),
    ]

    # Отдельные списки событий:
    # - посты (недели поста)
    # - праздники (Пасха и т.п.)
    fast_events: list[str] = []
    feast_events: list[str] = []

    # Однодневные посты (фиксированные даты)
    one_day_fasts = [
        (
            "Строгий пост - Крещенский сочельник",
            1,
            18,
            "Степень строгости зависит от дня седмицы: если сочельник попадает в понедельник – пятницу, то по Уставу разрешается только ужин с подсолнечным маслом и вином; если же в субботу или воскресенье, то разрешается две трапезы: небольшой обед после литургии и ужин вечером (по Уставу после великой вечерни)",
        ),
        (
            "Строгий пост - Усекновение главы Иоанна Предтечи",
            9,
            11,
            "По монастырскому уставу день – средний с точки зрения пищи. С одной стороны, в этот день совершается литургия и потому строгого поста в буквальном смысле здесь не бывает, пища разрешается с «вином и елеем». С другой стороны, рыба на трапезе не допускается.",
        ),
        (
            "Строгий пост - Воздвижение Креста Господня",
            9,
            27,
            "По монастырскому уставу день – средний с точки зрения пищи. С одной стороны, в этот день совершается литургия и потому строгого поста в буквальном смысле здесь не бывает, пища разрешается с «вином и елеем». С другой стороны, рыба на трапезе не допускается.",
        ),
    ]

    for year in range(start_year, end_year + 1):
        pascha = orthodox_easter(year)
        trinity = pascha + timedelta(days=49)
        palm_sunday = pascha - timedelta(days=7)
        lazarus_saturday = palm_sunday - timedelta(days=1)
        good_friday = pascha - timedelta(days=2)

        # Великий пост: понедельник за 48 дней до Пасхи
        lent_monday = pascha - timedelta(days=48)

        # Сплошные седмицы (отсутствие поста в ср/пт)
        continuous_weeks: set[date] = set()
        # Святки 7–18 янв
        for d in _dates_in_range(date(year, 1, 7), date(year, 1, 18)):
            continuous_weeks.add(d)
        # Мытаря и фарисея: заканчивается за 2 недели до ВП — неделя до Пн за 3 недели до ВП
        mytar_end = lent_monday - timedelta(days=15)  # воскр. за 2 нед. до ВП
        mytar_start = mytar_end - timedelta(days=6)
        for d in _dates_in_range(mytar_start, mytar_end):
            continuous_weeks.add(d)
        # Сырная (Масленица) — неделя перед ВП
        cheese_start = lent_monday - timedelta(days=7)
        cheese_end = lent_monday - timedelta(days=1)
        for d in _dates_in_range(cheese_start, cheese_end):
            continuous_weeks.add(d)
        # Пасхальная — неделя после Пасхи
        for d in _dates_in_range(pascha, pascha + timedelta(days=6)):
            continuous_weeks.add(d)
        # Троицкая — понедельник после Троицы до воскресенья после Троицы (+1 день)
        for d in _dates_in_range(trinity + timedelta(days=1), trinity + timedelta(days=7)):
            continuous_weeks.add(d)

        # Даты, входящие в продолжительные посты (ср/пт внутри не добавляем отдельно)
        prolonged_fast_dates: set[date] = set()
        # ВП
        for d in _dates_in_range(lent_monday, pascha - timedelta(days=1)):
            prolonged_fast_dates.add(d)
        # Апостольский: Пн после Троицы до 11 июля
        apostolic_start = trinity + timedelta(days=8)  # понедельник после седмицы Троицы
        apostolic_end = date(year, 7, 11)
        for d in _dates_in_range(apostolic_start, apostolic_end):
            prolonged_fast_dates.add(d)
        # Успенский 14–27 авг
        for d in _dates_in_range(date(year, 8, 14), date(year, 8, 27)):
            prolonged_fast_dates.add(d)
        # Рождественский 28 ноя – 6 янв (хвост прошлого года: 1–6 янв; начало текущего: 28 ноя – 31 дек)
        for d in _dates_in_range(date(year, 1, 1), date(year, 1, 6)):
            prolonged_fast_dates.add(d)
        for d in _dates_in_range(date(year, 11, 28), date(year, 12, 31)):
            prolonged_fast_dates.add(d)

        print(f"\n{'='*50}")
        print(f"  {year} год")
        print("=" * 50)
        weekdays_ru = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
        print(f"  Пасха: {pascha.strftime('%d.%m.%Y')} ({weekdays_ru[pascha.weekday()]})")
        print(f"  ВП: {lent_monday.strftime('%d.%m')} - {(pascha - timedelta(days=1)).strftime('%d.%m')}")

        # --- Масленица ---
        summary_masl = "Без мяса - Масленица"
        descr_masl = f"Неделя перед Великим Постом (без мяса)\\nhttps://azbyka.ru/days/{cheese_start.strftime('%Y-%m-%d')}"
        uid_masl = f"{year}-maslenitsa@orthodox-fasts"
        fast_events.append(make_ics_event(uid_masl, cheese_start, cheese_end, summary_masl, descr_masl))

        # --- Великий пост (объединяем: Пн-Вт, Сб-Вс в нед. 1–5; строгий Пн-Вт в нед. 1) ---
        gl_rules: list[tuple[date, str, str]] = []
        for week_num in range(1, 8):
            w_mon = lent_monday + timedelta(days=(week_num - 1) * 7)
            w_sun = w_mon + timedelta(days=6)
            for d in _dates_in_range(w_mon, w_sun):
                if d >= pascha:
                    continue
                wd = d.weekday()
                if d == good_friday:
                    desc = "Устав повелевает полное воздержание от пищи в течение всего дня; но, по традиции, воздерживаются от пищи до окончания выноса Плащаницы (обычно эта служба заканчивается в 15-16 часов)"
                    url = f"https://azbyka.ru/days/{d.strftime('%Y-%m-%d')}"
                    gl_rules.append((d, "Строгий пост - Страстная пятница", f"{desc}\\n{url}"))
                    continue
                if d.month == 4 and d.day == 7:
                    t = FAST_TYPES["fish"]
                    gl_rules.append((d, f"{t[0]} - Благовещение Пресвятой Богородицы", t[1]))
                    continue
                if d == palm_sunday:
                    t = FAST_TYPES["fish"]
                    gl_rules.append((d, f"{t[0]} - Вербное воскресенье", t[1]))
                    continue
                if d == lazarus_saturday:
                    t = FAST_TYPES["fish_roe"]
                    gl_rules.append((d, f"{t[0]} - Лазарева суббота", t[1]))
                    continue
                if week_num == 1 and wd in (0, 1, 3):
                    gl_rules.append((d, "Строгий пост - Неделя 1-я Великого поста. Торжество Православия", "Полное воздержание от пищи"))
                    continue
                if wd in (0, 1, 3):
                    gl_rules.append((d, f"{FAST_TYPES['no_oil'][0]} - Неделя {week_num}-я Великого поста", FAST_TYPES["no_oil"][1]))
                elif wd in (2, 4):
                    gl_rules.append((d, f"{FAST_TYPES['dry'][0]} - Неделя {week_num}-я Великого поста", FAST_TYPES["dry"][1]))
                else:
                    gl_rules.append((d, f"{FAST_TYPES['with_oil'][0]} - Неделя {week_num}-я Великого поста", FAST_TYPES["with_oil"][1]))
        _emit_spans(fast_events, year, "gl", gl_rules, [0])

        # --- Апостольский пост (объединяем Сб-Вт: рыба) ---
        apost_rules = []
        for d in _dates_in_range(apostolic_start, apostolic_end):
            wd = d.weekday()
            if wd in (2, 4):
                apost_rules.append((d, f"{FAST_TYPES['with_oil'][0]} - Апостольский пост", FAST_TYPES["with_oil"][1]))
            else:
                apost_rules.append((d, f"{FAST_TYPES['fish'][0]} - Апостольский пост", FAST_TYPES["fish"][1]))
        _emit_spans(fast_events, year, "apost", apost_rules, [0])

        # --- Успенский пост 14–27 авг (объединяем Пн-Вт и Сб-Вс) ---
        dorm_rules = []
        for d in _dates_in_range(date(year, 8, 14), date(year, 8, 27)):
            wd = d.weekday()
            if wd in (0, 1, 3):
                dorm_rules.append((d, f"{FAST_TYPES['no_oil'][0]} - Успенский пост", FAST_TYPES["no_oil"][1]))
            elif wd in (2, 4):
                dorm_rules.append((d, f"{FAST_TYPES['dry'][0]} - Успенский пост", FAST_TYPES["dry"][1]))
            else:
                dorm_rules.append((d, f"{FAST_TYPES['with_oil'][0]} - Успенский пост", FAST_TYPES["with_oil"][1]))
        _emit_spans(fast_events, year, "dorm", dorm_rules, [0])

        # --- Рождественский пост (объединяем: 28.11-19.12 сб-вт; 20.12-1.01 и 2-6.01 пн-вт и сб-вс) ---
        def _in_range(d: date, start: date, end: date) -> bool:
            return start <= d <= end

        nat_rules: list[tuple[date, str, str]] = []
        for d in _dates_in_range(date(year, 11, 28), date(year, 12, 31)):
            wd = d.weekday()
            if _in_range(d, date(year, 11, 28), date(year, 12, 19)):
                if wd in (2, 4):
                    t = FAST_TYPES["with_oil"]
                    nat_rules.append((d, f"{t[0]} - Рождественский пост", t[1]))
                else:
                    t = FAST_TYPES["fish"]
                    nat_rules.append((d, f"{t[0]} - Рождественский пост", t[1]))
            else:
                if wd in (2, 4):
                    t = FAST_TYPES["no_oil"]
                    nat_rules.append((d, f"{t[0]} - Рождественский пост", t[1]))
                elif wd in (0, 1, 3):
                    t = FAST_TYPES["with_oil"]
                    nat_rules.append((d, f"{t[0]} - Рождественский пост", t[1]))
                else:
                    t = FAST_TYPES["fish"]
                    nat_rules.append((d, f"{t[0]} - Рождественский пост", t[1]))
        for d in _dates_in_range(date(year + 1, 1, 1), date(year + 1, 1, 6)):
            wd = d.weekday()
            if d.day == 1:
                if wd in (2, 4):
                    t = FAST_TYPES["no_oil"]
                    nat_rules.append((d, f"{t[0]} - Рождественский пост", t[1]))
                elif wd in (0, 1, 3):
                    t = FAST_TYPES["with_oil"]
                    nat_rules.append((d, f"{t[0]} - Рождественский пост", t[1]))
                else:
                    t = FAST_TYPES["fish"]
                    nat_rules.append((d, f"{t[0]} - Рождественский пост", t[1]))
            else:
                if wd in (0, 1, 3):
                    t = FAST_TYPES["no_oil"]
                    nat_rules.append((d, f"{t[0]} - Рождественский пост", t[1]))
                elif wd in (2, 4):
                    t = FAST_TYPES["dry"]
                    nat_rules.append((d, f"{t[0]} - Рождественский пост", t[1]))
                else:
                    t = FAST_TYPES["with_oil"]
                    nat_rules.append((d, f"{t[0]} - Рождественский пост", t[1]))
        _emit_spans(fast_events, year, "nat", nat_rules, [0])

        # --- Однодневные посты ---
        for name, month, day, descr in one_day_fasts:
            d = date(year, month, day)
            url = f"https://azbyka.ru/days/{d.strftime('%Y-%m-%d')}"
            fast_events.append(make_ics_event(f"{year}-1d-{month:02d}{day:02d}@orthodox-fasts", d, d, name, f"{descr}\\n{url}"))

        # --- Среда и пятница (кроме сплошных и продолжительных) ---
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)
        for d in _dates_in_range(year_start, year_end):
            if d.weekday() not in (2, 4):
                continue
            if d in continuous_weeks or d in prolonged_fast_dates:
                continue
            # однодневные посты в ср/пт уже добавлены выше
            if (d.month, d.day) in ((1, 18), (9, 11), (9, 27)):
                continue
            t = FAST_TYPES["post"]
            s = f"{t[0]} - Среда" if d.weekday() == 2 else f"{t[0]} - Пятница"
            desc = t[1]
            fast_events.append(make_ics_event(f"{year}-wf-{d.strftime('%j')}@orthodox-fasts", d, d, s, desc))

        # Вербное воскресенье (7 дней до Пасхи)
        palm_sunday = pascha - timedelta(days=7)
        palm_date_str = palm_sunday.strftime("%Y-%m-%d")
        palm_summary = "Вербное воскресенье"
        palm_description = (
            f"Неделя пальмовых ветвей - Вход Господень в Иерусалим\\n"
            f"https://azbyka.ru/days/{palm_date_str}"
        )
        uid_palm = f"{year}-palm-sunday@orthodox-feasts"
        feast_events.append(
            make_ics_event(uid_palm, palm_sunday, palm_sunday, palm_summary, palm_description)
        )

        # Пасха (один день) — праздник
        pascha_date_str = pascha.strftime("%Y-%m-%d")
        summary_pascha = f"Пасха ({year})"
        description_pascha = (
            f"Светлое Христово Воскресение\\n"
            f"https://azbyka.ru/days/{pascha_date_str}"
        )
        uid_pascha = f"{year}-pascha@orthodox-feasts"
        feast_events.append(make_ics_event(uid_pascha, pascha, pascha, summary_pascha, description_pascha))

        # Вознесение Господне (40-й день после Пасхи — литургически, через 39 дней)
        ascension = pascha + timedelta(days=39)
        asc_date_str = ascension.strftime("%Y-%m-%d")
        summary_asc = "Вознесение Господне"
        description_asc = f"Вознесение Господне\\nhttps://azbyka.ru/days/{asc_date_str}"
        uid_asc = f"{year}-ascension@orthodox-feasts"
        feast_events.append(
            make_ics_event(uid_asc, ascension, ascension, summary_asc, description_asc)
        )

        # День Святой Троицы (49-й день после Пасхи)
        trinity = pascha + timedelta(days=49)
        trinity_date_str = trinity.strftime("%Y-%m-%d")
        summary_trinity = "День Святой Троицы"
        description_trinity = f"Пятидесятница\\nhttps://azbyka.ru/days/{trinity_date_str}"
        uid_trinity = f"{year}-trinity@orthodox-feasts"
        feast_events.append(
            make_ics_event(uid_trinity, trinity, trinity, summary_trinity, description_trinity)
        )

        # Неподвижные праздники этого года
        for idx, (name, month, day, descr) in enumerate(fixed_feasts, start=1):
            d = date(year, month, day)
            d_str = d.strftime("%Y-%m-%d")
            url = f"https://azbyka.ru/days/{d_str}"
            description = f"{descr}\\n{url}"
            uid = f"{year}-fixed-{idx}@orthodox-feasts"
            feast_events.append(make_ics_event(uid, d, d, name, description))

    # Запись .ics-файлов (раздельно)
    write_ics_file(fast_events, "orthodox_fasts.ics")
    write_ics_file(feast_events, "orthodox_feasts.ics")

    print("\nСозданы файлы:")
    print("  - 'orthodox_fasts.ics'  (календарь постов)")
    print("  - 'orthodox_feasts.ics' (календарь праздников)")
    print("Их можно по отдельности импортировать в разные календари Google.")


if __name__ == "__main__":
    main()
