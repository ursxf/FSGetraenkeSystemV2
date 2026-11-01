"""Admin statistics: purchases over time, per product and per user.

All purchases of the selected period are loaded once and aggregated in Python.
This keeps the grouping by *local* day/hour independent of the database and is
fast enough for the amount of data a drinks system produces.
"""

import calendar
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from flask import Blueprint, current_app, render_template, request
from flask_login import login_required

from .helpers import admin_permission
from ..db import db
from ..db.models import Product, Revenue, User

stats_bp = Blueprint('stats', __name__, url_prefix='/stats')

WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
MONTHS = list(calendar.month_abbr)[1:]
TOP_LIMIT = 10
STREAK_LIMIT = 5
BUDDY_LIMIT = 10
BUDDY_WINDOW = timedelta(minutes=10)  # two purchases this close together count as "drinking together"
WRAPPED_MONTHS = 2  # the Wrapped of the previous semester can be seen during the first months of a semester

# Product filter groups shown above the product list in the filter select
PRODUCT_GROUPS = {
    'all': 'All products',
    'drinks': 'All drinks',
    'alc': 'Alcoholic drinks',
    'nonalc': 'Non-alcoholic drinks',
    'food': 'Food',
}


@dataclass
class Purchase:
    date: datetime  # local time
    user: int
    product: int
    amount: int  # price in cents (positive)


@dataclass
class Ranking:
    id: int
    name: str
    count: int = 0
    amount: int = 0
    share: float = 0.0
    favorite: Optional[str] = None  # users only: most bought product in the selection


@dataclass
class Stats:
    count: int = 0
    amount: int = 0
    days: int = 0
    active_days: int = 0
    users: int = 0
    per_day: float = 0.0
    busiest_day: Optional[tuple[date, int]] = None
    timeline: list[tuple[str, int]] = field(default_factory=list)
    weekdays: list[tuple[str, float]] = field(default_factory=list)
    hours: list[tuple[str, int]] = field(default_factory=list)
    products: list[Ranking] = field(default_factory=list)
    users_ranking: list[Ranking] = field(default_factory=list)


@dataclass
class Comparison:
    label: str  # e.g. "2025" or "Nov 2025"
    partial: bool  # compared only up to the same day, because the current period is still running
    count: int
    amount: int
    per_day: float

    @staticmethod
    def delta(current: float, previous: float) -> Optional[float]:
        """Relative change in percent, None if there is nothing to compare with."""
        return (current - previous) / previous * 100 if previous else None


@dataclass
class Streak:
    name: str
    days: int
    start: date
    end: date
    ongoing: bool


@dataclass
class Buddies:
    ids: tuple[int, int]
    names: tuple[str, str]
    days: int  # number of days on which both bought within BUDDY_WINDOW of each other


@dataclass
class YearSummary:
    year: int
    count: int
    days: int
    per_day: float
    busiest_day: Optional[tuple[date, int]]


def _local_tz() -> ZoneInfo:
    return ZoneInfo(current_app.config.get('STATS_TIMEZONE', 'Europe/Berlin'))


def _to_local(value: datetime, tz: ZoneInfo) -> datetime:
    if value.tzinfo is None:  # stored without timezone -> treat as UTC
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(tz)


def _product_condition(selection: str):  # noqa: ANN202
    if selection == 'drinks':
        return ~Product.is_food
    if selection == 'alc':
        return Product.has_alc & ~Product.is_food
    if selection == 'nonalc':
        return ~Product.has_alc & ~Product.is_food
    if selection == 'food':
        return Product.is_food
    if selection.isdigit():
        return Product.id == int(selection)
    return None


def _load_purchases(tz: ZoneInfo, product_selection: str) -> list[Purchase]:
    """Load all purchases (revenues with a product) matching the product selection."""
    stmt = db.select(Revenue.date, Revenue.user, Revenue.product, Revenue.amount).join(Product, Revenue.product == Product.id)
    condition = _product_condition(product_selection)
    if condition is not None:
        stmt = stmt.where(condition)

    return [
        Purchase(date=_to_local(row.date, tz), user=row.user, product=row.product, amount=-row.amount)
        for row in db.session.execute(stmt)
        if row.date is not None
    ]


def _period_bounds(year: Optional[int], month: Optional[int]) -> tuple[Optional[date], Optional[date]]:
    if year is None:
        return None, None
    if month is None:
        return date(year, 1, 1), date(year + 1, 1, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return date(year, month, 1), end


def _elapsed_days(first: date, end: date, today: date) -> int:
    """Number of days from *first* up to *end* (excl.), but not beyond today."""
    last = min(end, today + timedelta(days=1))
    return max((last - first).days, 0)


def _busiest_day(per_day: Counter) -> Optional[tuple[date, int]]:
    if not per_day:
        return None
    # On a tie the earlier day wins
    day = min(per_day, key=lambda d: (-per_day[d], d))
    return day, per_day[day]


def _rankings(purchases: list[Purchase], key: str, names: dict[int, str], total: int) -> list[Ranking]:
    rankings: dict[int, Ranking] = {}
    for purchase in purchases:
        entity = getattr(purchase, key)
        ranking = rankings.setdefault(entity, Ranking(id=entity, name=names.get(entity, f'#{entity}')))
        ranking.count += 1
        ranking.amount += purchase.amount
    for ranking in rankings.values():
        ranking.share = ranking.count / total if total else 0.0
    return sorted(rankings.values(), key=lambda r: (-r.count, r.name.lower()))


def _compute(
    purchases: list[Purchase],
    year: Optional[int],
    month: Optional[int],
    today: date,
    first_day: date,
    product_names: dict[int, str],
    user_names: dict[int, str],
) -> Stats:
    stats = Stats(count=len(purchases), amount=sum(p.amount for p in purchases))

    # Days are counted from the first purchase on, so a year in which the system
    # went live is not averaged over days on which it did not exist yet.
    period_start, end = _period_bounds(year, month)
    start = first_day if period_start is None else max(period_start, first_day)
    if end is None:
        end = today + timedelta(days=1)
    stats.days = _elapsed_days(start, end, today)

    per_day = Counter(p.date.date() for p in purchases)
    stats.active_days = len(per_day)
    stats.users = len({p.user for p in purchases})
    stats.per_day = stats.count / stats.days if stats.days else 0.0
    stats.busiest_day = _busiest_day(per_day)

    # Timeline: months of a year, days of a month, or years for "all time"
    if year is None:
        per_year = Counter(p.date.year for p in purchases)
        stats.timeline = [(str(y), per_year[y]) for y in range(first_day.year, today.year + 1)]
    elif month is None:
        per_month = Counter(p.date.month for p in purchases)
        stats.timeline = [(MONTHS[m - 1], per_month[m]) for m in range(1, 13)]
    else:
        per_dom = Counter(p.date.day for p in purchases)
        stats.timeline = [(str(d), per_dom[d]) for d in range(1, calendar.monthrange(year, month)[1] + 1)]

    # Average per weekday: purchases on that weekday / number of such days in the period
    weekday_days = Counter((start + timedelta(days=i)).weekday() for i in range(stats.days))
    per_weekday = Counter(p.date.weekday() for p in purchases)
    stats.weekdays = [
        (name, per_weekday[i] / weekday_days[i] if weekday_days[i] else 0.0) for i, name in enumerate(WEEKDAYS)
    ]

    per_hour = Counter(p.date.hour for p in purchases)
    stats.hours = [(f'{h:02d}', per_hour[h]) for h in range(24)]

    stats.products = _rankings(purchases, 'product', product_names, stats.count)
    stats.users_ranking = _rankings(purchases, 'user', user_names, stats.count)

    favorites: dict[int, Counter] = defaultdict(Counter)
    for purchase in purchases:
        favorites[purchase.user][purchase.product] += 1
    for ranking in stats.users_ranking:
        product_id, _ = min(favorites[ranking.id].items(), key=lambda item: (-item[1], product_names.get(item[0], '')))
        ranking.favorite = product_names.get(product_id, f'#{product_id}')

    return stats


def _year_summaries(purchases: list[Purchase], today: date) -> list[YearSummary]:
    if not purchases:
        return []
    first = min(p.date.date() for p in purchases)
    summaries = []
    for year in range(today.year, first.year - 1, -1):
        year_purchases = [p for p in purchases if p.date.year == year]
        start = max(date(year, 1, 1), first)
        days = _elapsed_days(start, date(year + 1, 1, 1), today)
        summaries.append(
            YearSummary(
                year=year,
                count=len(year_purchases),
                days=days,
                per_day=len(year_purchases) / days if days else 0.0,
                busiest_day=_busiest_day(Counter(p.date.date() for p in year_purchases)),
            )
        )
    return summaries


def _shift_year(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year + years)
    except ValueError:  # 29 February
        return day.replace(year=day.year + years, day=28)


def _comparison(
    all_purchases: list[Purchase], year: Optional[int], month: Optional[int], today: date, first_day: date
) -> Optional[Comparison]:
    """Same period one year earlier. A running period is compared up to the same day."""
    start, end = _period_bounds(year, month)
    if start is None or end is None:
        return None
    partial = end > today + timedelta(days=1)
    if partial:
        end = today + timedelta(days=1)
    prev_start, prev_end = _shift_year(start, -1), _shift_year(end, -1)
    if prev_end <= first_day:  # system did not exist yet
        return None

    previous = [p for p in all_purchases if prev_start <= p.date.date() < prev_end]
    days = _elapsed_days(max(prev_start, first_day), prev_end, today)
    label = str(prev_start.year) if month is None else f'{MONTHS[month - 1]} {prev_start.year}'
    return Comparison(
        label=label,
        partial=partial,
        count=len(previous),
        amount=sum(p.amount for p in previous),
        per_day=len(previous) / days if days else 0.0,
    )


def _streaks(
    purchases: list[Purchase], open_days: list[date], user_names: dict[int, str], running: bool
) -> list[Streak]:
    """Longest run of consecutive *open days* (days on which anything was bought) per user.

    Days on which nobody bought anything (weekends, holidays) do not break a streak.
    A streak is ongoing if the period is still running and it reaches the latest open day.
    """
    days_per_user: dict[int, set[date]] = defaultdict(set)
    for purchase in purchases:
        days_per_user[purchase.user].add(purchase.date.date())

    streaks = []
    for user, days in days_per_user.items():
        best: Optional[tuple[int, date, date]] = None
        run, run_start = 0, None
        for day in open_days:
            if day in days:
                run_start = day if run == 0 else run_start
                run += 1
                if best is None or run > best[0]:
                    best = (run, run_start, day)  # type: ignore[assignment]
            else:
                run = 0
        if best is not None and best[0] >= 2:
            streaks.append(
                Streak(
                    name=user_names.get(user, f'#{user}'),
                    days=best[0],
                    start=best[1],
                    end=best[2],
                    ongoing=running and best[2] == open_days[-1],
                )
            )
    return sorted(streaks, key=lambda s: (-s.days, s.end))[:STREAK_LIMIT]


def _buddies(purchases: list[Purchase], user_names: dict[int, str], user: Optional[int] = None) -> list[Buddies]:
    """Pairs of users who often buy within BUDDY_WINDOW of each other, counted as days together.

    *purchases* must contain the purchases of all users. With *user* only pairs including that user are returned.
    """
    together: dict[tuple[int, int], set[date]] = defaultdict(set)
    ordered = sorted(purchases, key=lambda p: p.date)
    for i, purchase in enumerate(ordered):
        for other in ordered[i + 1 :]:
            if other.date - purchase.date > BUDDY_WINDOW:
                break
            if other.user != purchase.user:
                pair = (min(purchase.user, other.user), max(purchase.user, other.user))
                together[pair].add(purchase.date.date())

    buddies = [
        Buddies(ids=(a, b), names=(user_names.get(a, f'#{a}'), user_names.get(b, f'#{b}')), days=len(days))
        for (a, b), days in together.items()
        if user is None or user in (a, b)
    ]
    return sorted(buddies, key=lambda b: (-b.days, b.names))[:BUDDY_LIMIT]


@dataclass(frozen=True)
class Semester:
    """Wintersemester: 1 Oct to 31 Mar, Sommersemester: 1 Apr to 30 Sep."""

    winter: bool
    year: int  # year in which the semester starts

    @classmethod
    def of(cls, day: date) -> 'Semester':
        if day.month >= 10:
            return cls(True, day.year)
        if day.month >= 4:
            return cls(False, day.year)
        return cls(True, day.year - 1)

    @classmethod
    def parse(cls, key: Optional[str]) -> Optional['Semester']:
        """Parse keys like "ws2026" or "ss2026"."""
        if not key or len(key) != 6 or key[:2] not in ('ws', 'ss') or not key[2:].isdigit():
            return None
        return cls(key[:2] == 'ws', int(key[2:]))

    @property
    def key(self) -> str:
        return f'{"ws" if self.winter else "ss"}{self.year}'

    @property
    def name(self) -> str:
        if self.winter:
            return f'Wintersemester {self.year % 100:02d}/{(self.year + 1) % 100:02d}'
        return f'Sommersemester {self.year % 100:02d}'

    @property
    def start(self) -> date:
        return date(self.year, 10 if self.winter else 4, 1)

    @property
    def end(self) -> date:
        """First day after the semester."""
        return date(self.year + 1, 4, 1) if self.winter else date(self.year, 10, 1)

    @property
    def previous(self) -> 'Semester':
        return Semester(False, self.year) if self.winter else Semester(True, self.year - 1)

    def __contains__(self, day: date) -> bool:
        return self.start <= day < self.end


def local_today() -> date:
    return datetime.now(_local_tz()).date()


def wrapped_window(today: date) -> tuple[Optional[Semester], date]:
    """The semester whose Wrapped is open to everyone today (None outside the window) and a date.

    During the first WRAPPED_MONTHS months of a semester everyone can see the Wrapped of the previous one.
    Inside the window the date is the last day of the window, outside it the day the next window opens.
    """
    current = Semester.of(today)
    start = current.start
    window_end = date(start.year + (start.month + WRAPPED_MONTHS - 1) // 12, (start.month + WRAPPED_MONTHS - 1) % 12 + 1, 1)
    if today < window_end:
        return current.previous, window_end - timedelta(days=1)
    return None, current.end


@dataclass
class Wrapped:
    """A user's personal semester in review."""

    semester: Semester
    name: str
    count: int
    amount: int
    active_days: int
    top_products: list[tuple[str, int]]
    favorite_share: float
    busiest_day: tuple[date, int]
    weekday: str
    hour: int
    persona: tuple[str, str]  # (emoji, title)
    first_purchase: tuple[datetime, str]
    rank: int
    users: int  # users with at least one purchase in that semester
    streak: Optional[Streak]
    buddy: Optional[tuple[str, int]]
    change: Optional[float]  # purchases compared with the previous semester in percent


def _persona(hour: int) -> tuple[str, str]:
    if hour < 5:
        return '🦉', 'Night Owl'
    if hour < 12:
        return '🐦', 'Early Bird'
    if hour < 17:
        return '☀️', 'Afternoon Regular'
    if hour < 21:
        return '🌆', 'Evening Sipper'
    return '🦉', 'Night Owl'


def wrapped_semesters(user_id: int) -> list[Semester]:
    """Finished semesters in which the user bought something, newest first."""
    tz = _local_tz()
    current = Semester.of(datetime.now(tz).date())
    stmt = db.select(Revenue.date).where(Revenue.user == user_id, Revenue.product.isnot(None))
    semesters = {Semester.of(_to_local(d, tz).date()) for d in db.session.execute(stmt).scalars() if d is not None}
    return sorted((s for s in semesters if s.end <= current.start), key=lambda s: s.start, reverse=True)


def build_wrapped(user_id: int, semester: Semester) -> Optional[Wrapped]:
    """Compute the semester in review of *user_id*, None if the user bought nothing in *semester*."""
    tz = _local_tz()
    product_names = dict(db.session.execute(db.select(Product.id, Product.name)).all())
    user_names = dict(db.session.execute(db.select(User.id, User.name)).all())

    everything = _load_purchases(tz, 'all')
    semester_all = [p for p in everything if p.date.date() in semester]
    mine = sorted((p for p in semester_all if p.user == user_id), key=lambda p: p.date)
    if not mine:
        return None

    per_product = Counter(p.product for p in mine)
    top_products = sorted(per_product.items(), key=lambda item: (-item[1], product_names.get(item[0], '')))[:3]
    per_weekday = Counter(p.date.weekday() for p in mine)
    per_hour = Counter(p.date.hour for p in mine)
    hour = min(per_hour, key=lambda h: (-per_hour[h], h))

    per_user = Counter(p.user for p in semester_all)
    rank = 1 + sum(1 for count in per_user.values() if count > per_user[user_id])

    open_days = sorted({p.date.date() for p in semester_all})
    streaks = _streaks(mine, open_days, user_names, running=False)
    buddies = _buddies(semester_all, user_names, user=user_id)
    buddy = None
    if buddies:
        other = buddies[0].ids[1] if buddies[0].ids[0] == user_id else buddies[0].ids[0]
        buddy = (user_names.get(other, f'#{other}'), buddies[0].days)

    previous = sum(1 for p in everything if p.user == user_id and p.date.date() in semester.previous)
    first_ever = min(p.date.date() for p in everything)
    change = Comparison.delta(len(mine), previous) if first_ever < semester.start else None

    return Wrapped(
        semester=semester,
        name=user_names.get(user_id, f'#{user_id}'),
        count=len(mine),
        amount=sum(p.amount for p in mine),
        active_days=len({p.date.date() for p in mine}),
        top_products=[(product_names.get(pid, f'#{pid}'), count) for pid, count in top_products],
        favorite_share=top_products[0][1] / len(mine),
        busiest_day=_busiest_day(Counter(p.date.date() for p in mine)),  # type: ignore[arg-type]
        weekday=calendar.day_name[min(per_weekday, key=lambda d: (-per_weekday[d], d))],
        hour=hour,
        persona=_persona(hour),
        first_purchase=(mine[0].date, product_names.get(mine[0].product, '?')),
        rank=rank,
        users=len(per_user),
        streak=streaks[0] if streaks else None,
        buddy=buddy,
        change=change,
    )


def _parse_int(value: Optional[str], minimum: int, maximum: int) -> Optional[int]:
    if value is None or not value.isdigit():
        return None
    number = int(value)
    return number if minimum <= number <= maximum else None


@stats_bp.route('/')
@login_required
@admin_permission.require(http_exception=401)
def index() -> str:
    tz = _local_tz()
    today = datetime.now(tz).date()

    # Period: ?year=2026&month=3, ?year=all for all time; default is the current year
    year_param = request.args.get('year', str(today.year))
    year = None if year_param == 'all' else (_parse_int(year_param, 2000, 2100) or today.year)
    month = _parse_int(request.args.get('month'), 1, 12) if year is not None else None

    product_selection = request.args.get('products', 'all')
    if product_selection not in PRODUCT_GROUPS and not product_selection.isdigit():
        product_selection = 'all'

    product_names = dict(db.session.execute(db.select(Product.id, Product.name)).all())
    user_names = dict(db.session.execute(db.select(User.id, User.name)).all())

    # Optional user filter: ?user=<id>
    selected_user = _parse_int(request.args.get('user'), 1, 2**31)
    if selected_user not in user_names:
        selected_user = None

    everyone = _load_purchases(tz, product_selection)  # all users, needed for the drinking buddies
    all_purchases = everyone if selected_user is None else [p for p in everyone if p.user == selected_user]
    start, end = _period_bounds(year, month)
    purchases = [p for p in all_purchases if start is None or start <= p.date.date() < end]  # type: ignore[operator]

    first_day = min((p.date.date() for p in all_purchases), default=today)
    stats = _compute(purchases, year, month, today, first_day, product_names, user_names)
    years = _year_summaries(all_purchases, today)
    comparison = _comparison(all_purchases, year, month, today, first_day)

    # Open days for the streaks: days on which anything at all was bought (independent of product and user filter)
    everything = everyone if product_selection == 'all' else _load_purchases(tz, 'all')
    open_days = sorted(
        {p.date.date() for p in everything if start is None or start <= p.date.date() < end}  # type: ignore[operator]
    )
    running = end is None or end > today
    streaks = _streaks(purchases, open_days, user_names, running) if open_days else []
    period_everyone = [p for p in everyone if start is None or start <= p.date.date() < end]  # type: ignore[operator]
    buddies = _buddies(period_everyone, user_names, user=selected_user)

    first_year = min((p.date.year for p in everything), default=today.year)
    products = db.session.execute(db.select(Product).order_by(Product.name)).scalars().all()
    users = db.session.execute(db.select(User).order_by(User.name)).scalars().all()

    return render_template(
        'stats/index.html',
        stats=stats,
        years=years,
        comparison=comparison,
        streaks=streaks,
        buddies=buddies,
        buddy_minutes=int(BUDDY_WINDOW.total_seconds() // 60),
        year=year,
        month=month,
        today=today,
        year_options=list(range(today.year, first_year - 1, -1)),
        month_names=list(calendar.month_name)[1:],
        product_selection=product_selection,
        product_groups=PRODUCT_GROUPS,
        products=products,
        users=users,
        selected_user=selected_user,
        selected_user_name=user_names.get(selected_user) if selected_user else None,
        top_limit=TOP_LIMIT,
    )
