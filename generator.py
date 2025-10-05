# -*- coding: utf-8 -*-
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, timedelta
import calendar
import hashlib
from typing import Dict, List, Tuple, Optional, Iterable

# Ключи типов смен (должны совпадать с config)
DAY_A, DAY_B = "day_a", "day_b"
NIGHT_A, NIGHT_B = "night_a", "night_b"
M8_A, M8_B = "m8_a", "m8_b"
E8_A, E8_B = "e8_a", "e8_b"
N4_A, N4_B = "n4_a", "n4_b"
N8_A, N8_B = "n8_a", "n8_b"
VAC_WD8, VAC_WE0 = "vac_wd8", "vac_we0"
OFF = "off"

@dataclass
class ShiftType:
    key: str
    code: str
    office: Optional[str]
    start: Optional[str]
    end: Optional[str]
    hours: int
    is_working: bool
    label: str

@dataclass
class Employee:
    id: str
    name: str
    is_trainee: bool = False
    mentor_id: Optional[str] = None
    ytd_overtime: int = 0
    seed4: int = 0           # фаза 0..3 (Д, Н, В, В)

@dataclass
class Assignment:
    employee_id: str
    date: date
    shift_key: str
    effective_hours: int
    source: str  # 'template' | 'autofix' | 'override'
    recolored_from_night: bool = False

class Generator:
    def __init__(self, config: Dict):
        self.cfg = config
        self.shift_types: Dict[str, ShiftType] = {
            k: ShiftType(
                key=k,
                code=v["code"],
                office=v["office"],
                start=v.get("start"),
                end=v.get("end"),
                hours=int(v["hours"]),
                is_working=bool(v["is_working"]),
                label=v["label"],
            )
            for k, v in self.cfg["shift_types"].items()
        }

    # ---------- Коды/классификация ----------
    def code_of(self, shift_key: str) -> str:
        return self.shift_types[shift_key].code

    @staticmethod
    def _is_day_code(code: str) -> bool:
        c = (code or "").upper()
        return c in {"DA", "DB", "M8A", "M8B", "E8A", "E8B"}

    @staticmethod
    def _is_night_code(code: str) -> bool:
        c = (code or "").upper()
        return c in {"NA", "NB", "N4A", "N4B", "N8A", "N8B"}

    @staticmethod
    def _is_off_code(code: str) -> bool:
        c = (code or "").upper()
        return c in {"OFF", "VAC8", "VAC0"}

    @staticmethod
    def _office_from_code(code: str) -> Optional[str]:
        c = (code or "").upper()
        if not c or c in {"OFF", "VAC8", "VAC0"}:
            return None
        return "A" if c.endswith("A") else ("B" if c.endswith("B") else None)

    # ---------- Даты ----------
    @staticmethod
    def ym_to_year_month(ym: str) -> Tuple[int, int]:
        y, m = ym.split("-")
        return int(y), int(m)

    @staticmethod
    def month_bounds(year: int, month: int) -> Tuple[date, date]:
        first = date(year, month, 1)
        last_day = calendar.monthrange(year, month)[1]
        last = date(year, month, last_day)
        return first, last

    @staticmethod
    def iter_month_days(year: int, month: int) -> Iterable[date]:
        d0, d1 = Generator.month_bounds(year, month)
        d = d0
        while d <= d1:
            yield d
            d += timedelta(days=1)

    # ---------- Сиды ----------
    @staticmethod
    def stable_hash_int(s: str) -> int:
        return int(hashlib.sha1(s.encode("utf-8")).hexdigest(), 16)

    def seed_employee(self, e: Employee) -> None:
        h = self.stable_hash_int(e.id)
        e.seed4 = h % 4

    # ---------- Эпоха ротации (якорь цикла) ----------
    def rotation_epoch_for(self, year: int) -> date:
        """
        Возвращает дату-«якорь» для расчёта фаз.
        По умолчанию — 1 января указанного года (политика: new_year_reset).
        """
        policy = self.cfg.get("rotation_epoch_policy", "new_year_reset")
        if policy == "new_year_reset":
            return date(year, 1, 1)
        # fallback на случай других политик — используем 1 января
        return date(year, 1, 1)

    # ---------- Фаза цикла ----------
    @staticmethod
    def phase_for_day(seed4: int, days_from_epoch: int) -> int:
        """
        Фазы 0..3 соответствуют: 0=Day, 1=Night, 2=Off, 3=Off.
        """
        return (seed4 + days_from_epoch) % 4

    # ---------- Восстановление состояния на 1-е число ----------
    # state = (phase0 ∈ {0,1,2,3}, next_day_office_parity ∈ {0(A),1(B)})
    def _infer_state_from_tail(
        self,
        tail_codes: List[str],
        seed_phase: int,
        bootstrap_office_parity: int,
    ) -> Tuple[int, int]:
        """
        tail_codes: список кодов (макс 4) последних дней прошл. месяца для сотрудника (по возрастанию дат).
        Правила:
         - Последний день был DAY → 1-е число = phase=1 (NIGHT)
         - Последний день был NIGHT (в т.ч. N4*) → 1-е = phase=2 (OFF)
         - Если последний был OFF, и предпоследний NIGHT → 1-е = phase=3
         - Иначе (OFF,OFF …) → 1-е = phase=0 (DAY)
        next_day_office_parity: строим по последней дневной в хвосте:
         - если последняя DAY была в офисе A → следующая дневная должна быть B (parity=1)
         - если была в офисе B → следующая дневная A (parity=0)
         - если дневных в хвосте нет → используем bootstrap_office_parity
        """
        phase0 = seed_phase % 4  # fallback
        if tail_codes:
            last = tail_codes[-1].upper()
            if self._is_day_code(last):
                phase0 = 1  # после DAY идёт NIGHT
            elif self._is_night_code(last):
                phase0 = 2  # после NIGHT идёт OFF
            else:
                # OFF/отпуск: смотрим на предпоследний
                prev = tail_codes[-2].upper() if len(tail_codes) >= 2 else ""
                if self._is_night_code(prev):
                    phase0 = 3
                else:
                    phase0 = 0

        # next_day_office_parity
        next_par = bootstrap_office_parity
        for c in reversed(tail_codes):
            if self._is_day_code(c):
                last_off = self._office_from_code(c)
                if last_off == "A":
                    next_par = 1  # после DAY_A следующая дневная в B
                elif last_off == "B":
                    next_par = 0  # после DAY_B следующая дневная в A
                break
        return phase0, next_par

    # ---------- Генерация месяца ----------
    def generate_month(
        self,
        month_spec: Dict,
        carry_in: Optional[List[Assignment]] = None,
        prev_tail_by_emp: Optional[Dict[str, List[str]]] = None,
    ) -> Tuple[List[Employee], Dict[date, List[Assignment]], List[Assignment]]:
        ym = month_spec["month_year"]
        y, m = self.ym_to_year_month(ym)
        _, last = self.month_bounds(y, m)
        norm = int(month_spec["norm_hours_month"]) if month_spec.get("norm_hours_month") else 0

        # Сотрудники
        employees = [
            Employee(
                id=rec["id"], name=rec["name"],
                is_trainee=bool(rec.get("is_trainee", False)),
                mentor_id=rec.get("mentor_id"),
                ytd_overtime=int(rec.get("ytd_overtime", 0)),
            )
            for rec in self.cfg["employees"]
        ]
        for e in employees:
            self.seed_employee(e)  # используем только как fallback фазы

        # Инициализация расписания
        schedule: Dict[date, List[Assignment]] = {d: [] for d in self.iter_month_days(y, m)}

        first_day = date(y, m, 1)

        # Инициализируем состояние по хвосту прошлого месяца (до 4 дней)
        # Ставим bootstrap: равномерные фазы 0,1,2,3 и начальная дневная A/B пополам по списку
        phase_map: Dict[str, int] = {}
        next_day_parity: Dict[str, int] = {}  # 0->A, 1->B
        for i, e in enumerate(employees):
            tail = (prev_tail_by_emp or {}).get(e.id, [])
            seed_phase = i % 4  # равномерно 0,1,2,3 между 8 сотрудниками
            bootstrap_par = 0 if (i % 2 == 0) else 1
            p0, par = self._infer_state_from_tail(
                tail,
                seed_phase=seed_phase,
                bootstrap_office_parity=bootstrap_par,
            )
            phase_map[e.id] = p0
            next_day_parity[e.id] = par

        # Разруливаем паритет A/B внутри каждой фазовой корзины (для сотрудников без хвоста)
        buckets: Dict[int, List[Employee]] = {0: [], 1: [], 2: [], 3: []}
        for e in employees:
            buckets[phase_map[e.id]].append(e)
        for group in buckets.values():
            idx_free = 0
            for e in group:
                if (prev_tail_by_emp or {}).get(e.id):
                    continue  # паритет восстановлен из хвоста
                next_day_parity[e.id] = 0 if (idx_free % 2 == 0) else 1
                idx_free += 1

        # Применяем carry-in — только для актуальных сотрудников.
        # ВАЖНО: если 1-го стоит N8*, 1-е трактуем как NIGHT (phase=1),
        # чтобы последовательность начала месяца оставалась N, O, O, D.
        if carry_in:
            existing = {e.id for e in employees}
            for a in carry_in:
                if a.employee_id not in existing:
                    continue
                if a.date in schedule:
                    schedule[a.date] = [x for x in schedule[a.date] if x.employee_id != a.employee_id]
                    schedule[a.date].append(a)
                # Если это 1-е число и код N8A/N8B — корректируем стартовую фазу на NIGHT.
                if a.date == first_day:
                    code = self.code_of(a.shift_key).upper()
                    if code in {"N8A", "N8B"}:
                        # Почему не OFF? Потому что сам факт наличия N8 на 1-е — это вторая часть ночи,
                        # и "потреблённая" фаза здесь должна быть NIGHT. Дальше генератор инкрементирует
                        # фазу на +1 для каждого дня (включая день со скипом из-за carry-in),
                        # что даст корректную цепочку: N (1-е) -> O (2-е) -> O (3-е) -> D (4-е).
                        phase_map[a.employee_id] = 1  # NIGHT
                        # паритет дневного офиса не меняем: он касается только DAY и будет применён при первом D

        # Построение шаблона по дням
        carry_out: List[Assignment] = []  # N8* на 1-е след. месяца

        for d in self.iter_month_days(y, m):
            for e in employees:
                ph = phase_map[e.id]
                # ВНИМАНИЕ: отпуск НЕ применяется здесь. Перекраска делается postprocess'ом.

                # если на этот день уже стоит carry-in (например N8A) — пропускаем генерацию
                if any(a.employee_id == e.id for a in schedule[d]):
                    phase_map[e.id] = (ph + 1) % 4
                    continue

                if ph == 0:  # DAY
                    # Дневной офис берём из next_day_parity и сразу инвертируем на следующий цикл
                    office = "A" if next_day_parity[e.id] == 0 else "B"
                    key = DAY_A if office == "A" else DAY_B
                    st = self.shift_types[key]
                    schedule[d].append(Assignment(e.id, d, key, st.hours, source="template"))
                    # Следующий цикл: дневной офис противоположный
                    next_day_parity[e.id] = 1 - next_day_parity[e.id]

                elif ph == 1:  # NIGHT
                    # Ночь текущего цикла всегда в офисе = текущему next_day_parity (см. вывод в обсуждении)
                    offc = "A" if next_day_parity[e.id] == 0 else "B"
                    key = NIGHT_A if offc == "A" else NIGHT_B
                    # Если последняя дата месяца — ставим N4* и готовим N8* в следующий месяц
                    if d == last:
                        key4 = N4_A if key == NIGHT_A else N4_B
                        st4 = self.shift_types[key4]
                        schedule[d].append(Assignment(e.id, d, key4, st4.hours, source="template"))
                        # carry-out в след. месяц: N8*
                        key8 = N8_A if key == NIGHT_A else N8_B
                        st8 = self.shift_types[key8]
                        next_year = last.year + (1 if last.month == 12 else 0)
                        next_month = 1 if last.month == 12 else last.month + 1
                        carry_out.append(
                            Assignment(
                                e.id,
                                date(next_year, next_month, 1),
                                key8,
                                st8.hours,
                                source="template",
                            )
                        )
                    else:
                        st = self.shift_types[key]
                        schedule[d].append(Assignment(e.id, d, key, st.hours, source="template"))

                else:  # OFF
                    st = self.shift_types[OFF]
                    schedule[d].append(Assignment(e.id, d, OFF, st.hours, source="template"))

                phase_map[e.id] = (ph + 1) % 4

        # Управление перелимитом часов (короткие смены, приоритет в выходные)
        self.enforce_hours_caps(employees, schedule, norm)

        return employees, schedule, carry_out

    # ---------- Ограничение часов (M8/E8 с приоритетом выходных) ----------
    def enforce_hours_caps(self, employees: List[Employee], schedule: Dict[date, List[Assignment]], norm_month: int):
        monthly_cap = norm_month + int(self.cfg.get("monthly_overtime_max", 0))
        yearly_cap = int(self.cfg.get("yearly_overtime_max", 0))

        def month_hours(eid: str) -> int:
            return sum(r.effective_hours for rows in schedule.values() for r in rows if r.employee_id == eid)

        def yearly_ok(e: Employee, after_hours: int) -> bool:
            overtime = max(0, after_hours - norm_month)
            return (e.ytd_overtime + overtime) <= yearly_cap

        # Сопоставление DAY→короткая (выходные — вечер E8*, будни — утро M8*)
        def short_key_for(dd: date, day_key: str) -> Optional[str]:
            is_weekend = dd.weekday() >= 5
            if day_key == DAY_A:
                return E8_A if is_weekend else M8_A
            if day_key == DAY_B:
                return E8_B if is_weekend else M8_B
            return None

        for e in employees:
            cur = month_hours(e.id)
            if cur <= monthly_cap and yearly_ok(e, cur):
                continue
            # Сначала рассматриваем выходные
            candidates: List[Tuple[date, Assignment]] = []
            for dd in sorted(schedule.keys(), key=lambda x: (x.weekday() < 5, x)):  # выходные сначала
                for rr in schedule[dd]:
                    if rr.employee_id == e.id and rr.shift_key in (DAY_A, DAY_B):
                        candidates.append((dd, rr))
            for dd, rr in candidates:
                skey = short_key_for(dd, rr.shift_key)
                if not skey:
                    continue
                st = self.shift_types[skey]
                rr.shift_key = skey
                rr.effective_hours = st.hours
                rr.source = rr.source if rr.source != "template" else "autofix"
                cur = month_hours(e.id)
                if cur <= monthly_cap and yearly_ok(e, cur):
                    break
