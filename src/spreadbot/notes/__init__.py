"""Dealer-note reader: a free-text note (fi/sv/en, typos, corrections) becomes one LegNote per leg.

Pipeline: normalise -> split into pieces (sentences, then commas) -> give each piece a kind by its
keywords -> read the piece's day and clock time -> fold the facts into the legs.
Standard library only; plain regexes, well under 1 ms a note.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

DAY = 1440


@dataclass
class LegNote:
    ready_at: int | None = None        # earliest minute the car can be collected; None = as stated
    after_payment: bool = False        # handover only after payment (a `release` event will come)
    pickup_hours: tuple[int, int] | None = None    # real (opens, closes) of the pickup site, if it differs
    delivery_hours: tuple[int, int] | None = None  # same for the delivery site
    deadline: int | None = None        # tighter absolute deadline (world minute) from the note
    manual: bool = False               # manual gearbox -> needs a manual licence
    plates: bool = False               # car has no plates -> withPlates
    summer_tyres: bool = False         # cannot be driven in snow
    uncertain: bool = False            # something time-related we could not resolve


def _rx(p: str) -> re.Pattern[str]:
    return re.compile(p)


# ---- vocabulary (on normalised text: lower case, ä/å -> a, ö -> o) --------------------------------
PAY = _rx(r"maks\w*|payment|\bpaid\b|\bpays?\b|betal\w*|rahoit\w*|financ\w*|finansi\w*")
HANDOVER = _rx(r"luovu\w*|ensin|\bfirst\b|\bafter\b|jal\w*ke+n|releas\w*|hand ?over|lamna\w*|utlamn\w*|\befter\b"
               r"|forst|until|before|ennen|\bkun\b|\bwhen\b|\bonce\b|vasta|\bsaa\b|\bfrom\b|alkaen|pending|odott\w*"
               r"|kesken|vantar|unpaid|maksamat\w*")
READY = _rx(r"\bva+l+(?:mi|im)\w*|noudettavi\w*|haettavi\w*|\bready\b|\bredy\b|\bavailable\b"
            r"|\bklar\w*|\b(?:voi|saa)\s+(?:nou|hak)\w*|kan hamtas|luovu\w*|hand ?over"
            r"|lamnas ut|utlamn\w*")
CLOSE = _rx(r"kiinni|\bsulje\w*|\bsulke\w*|\bclos\w*|\bstang\w*|\basti\b|saakka|\buntil\b|\btill?\b"
            r"|ei ketaan|nobody|no one|\bingen\b")
OPEN = _rx(r"\bauki\b|\bopen\w*|\boppe\w*|\boppna\w*|aukeaa|avautu\w*|avoinna")
FROM = _rx(r"a+l+kaen|jal\w*ke+n|\bfrom\b|\bafter\b|onwards|\bfran\b|\befter\b|framat|\bvasta\b|\bforst\b"
           r"|not until|only from|lahtien|aikaisintaan|earliest|tidigast")
NOT_BEFORE = _rx(r"(?:\bnot|\bei|\binte|\bej)\s+(?:ennen|before|fore|innan|earlier|aiemmin|tidigare)")
PICKUP = _rx(r"haettava\b|\bhaku\b|\bhak[ea]\w*|\bhae\w*|\bnouto\w*|noudettava\b|\bnoud[ae]\w*|\bnout\w*"
             r"|collect\w*|pick ?-?up\w*|\bhamt\w*")
BEFORE = _rx(r"ennen|\bb[ef]{1,3}o?r?e\b|\bby\b|viim\w*|\bfore\b|innan|senast|latest|mennessa")
DELIV = _rx(r"\bpe+ril+\w*|vastaan\w*|v\w?staan\w*|\bkohde\w*|\bkohtee\w*|toimit\w*|destin\w*"
            r"|\br\w{0,2}c\w{0,3}v(?:e|ing|ed)\w*|recipient|deliver\w*|arriv\w*|framme|mottag\w*|lever[ae]\w*|drop.?off|deadline|takaraja"
            r"|\bdue\b|be there|on site|needs? (?:it|the car)|tarvit\w*|behov\w*")
PHONE = _rx(r"\b(?:soita\w*|call\w*|ring|ringa\w*|ilmoita\w*|text|sms|tekstaa)\b.*")
ANAPHOR = _rx(r"\b(?:sita|sen|that|det|then|silloin|sitten|da)\b")  # 'by then', 'sen jalkeen'
WINTER_OFF = _rx(r"(?:winter|talvi|vinter)\w*\s+(?:\w+\s+){0,2}?(?:not|missing|puuttu\w*|ei|saknas|ej|inte)\b")
CORR = _rx(r"^(?:korjaus|korj|correction|corr|rattelse|sorry|oops|i mean|tarkoitan|siis|ei kun|nej|menar"
           r"|forlat|anteeksi|pahoittelut|edit)\b")
SATURDAY = _rx(r"lauantai\w*|\bla\b|saturday|\bsat\b|lordag\w*|\blor\b|viikonlop\w*|weekend|helg\w*")
PART_OF_DAY = _rx(r"aamu\w*|iltap\w*|ilta\w*|morning|afternoon|evening|formiddag\w*|eftermiddag\w*|kvall\w*")
DENY_BEFORE = _rx(r"(?:\bnot|\bei|\beika|\binte|\bej|\bnej|\bno|rather than|instead of|istallet for)\s+"
                  r"(?:a\s+|at\s+|klo\s*|kl\.?\s*|kello\s*|klockan\s*)?\(?$")
DENY_AFTER = _rx(r"^\s*(?:sijaan|asemesta|instead)\b")

MANUAL = _rx(r"\bman+u+(?:a+l|e+l)\w*|kasivaiht\w*|stick ?shift")
NOT_AUTO = _rx(r"(?:\bnot|\bno|\bei|\binte|\bej)\s+(?:an?\s+|en\s+)?automa\w*")
NEG_WORD = _rx(r"(?:\bnot|\bno|\bei|\binte|\bej|\bnon)\s+(?:a\s+|an\s+|en\s+)?$")
PLATES = _rx(r"\bp+l+a+t+e+s?\b|kilv\w*|kilp(?:i|ia|ien|e)\b|rekkar\w*|skylt\w*|nummerplat\w*")
SUMMER = _rx(r"\bs[um]{2,5}er\b|kesa\w*(?:ren|kum)\w*|sommar\w*(?:dack|hjul)\w*")
NO_WINTER = _rx(r"(?:\bno|\bei|\binga|\bwithout|\bilman)\s+(?:winter\w*|talvi\w*|vinter\w*)")
MOUNTED = _rx(r"\bstill\b|\bviel?a\b|\balla\b|renkailla\b|fortfarande|sitter pa|\bpa sommar\w*|\bmounted\b|\bfitted\b")
LOOSE = _rx(r"trunk|\bboot\b|\bback\b|takakont\w*|tavarati\w*|kontissa|kontti\w*|bakluck\w*|bagage\w*|mukaan"
            r"|mukana|kyydissa|go with|take along|foljer med|ska med|vantei\w*|\bset\b|sarja\w*|i bilen"
            r"|in the car|lisaksi|extra|spare|\d+ kesa")

# ---- days --------------------------------------------------------------------------------------
TOMORROW = r"t[aeiou]?m+[aeiou]*r+[aeiou]*r*[aeiou]*w+|tmr|2morr?ow"
RELDAY = [
    (_rx(r"\bylihuom\w*|\bi ?overmorgon\b|\bovermorgon\b|\bovermorrow\b"), 2),
    (_rx(rf"\bhu*o+m+e+n+\w*|\bhuomis\w*|\bi ?morgon\b|\bi ?morr[oa]n?\b|\b(?:{TOMORROW})\b"), 1),
    (_rx(r"\btanaan\b|\bidag\b|\bi dag\b|\btoday\b|\btonight\b|\bi ?kvall\b"), 0),
]
WD_FULL = _rx(r"\b(maanantai|monday|mandag|tiistai|tuesday|tisdag|keskiviikko|wednesday|onsdag|torstai|thursday"
              r"|torsdag|perjantai|friday|fredag|lauantai|saturday|lordag|sunnuntai|sunday|sondag)\w*")
WD_IDX = {"maanantai": 0, "monday": 0, "mandag": 0, "tiistai": 1, "tuesday": 1, "tisdag": 1, "keskiviikko": 2,
          "wednesday": 2, "onsdag": 2, "torstai": 3, "thursday": 3, "torsdag": 3, "perjantai": 4, "friday": 4,
          "fredag": 4, "lauantai": 5, "saturday": 5, "lordag": 5, "sunnuntai": 6, "sunday": 6, "sondag": 6,
          "ma": 0, "ti": 1, "ke": 2, "to": 3, "pe": 4, "la": 5, "su": 6, "mon": 0, "tue": 1, "tues": 1,
          "wed": 2, "weds": 2, "thu": 3, "thur": 3, "thurs": 3, "fri": 4, "sat": 5, "sun": 6, "man": 0, "tis": 1,
          "ons": 2, "tor": 3, "tors": 3, "fre": 4, "lor": 5, "son": 6}
WD_ANY = r"(?:maanantai|tiistai|keskiviikko|torstai|perjantai|lauantai|sunnuntai|mandag|fredag|lordag|sondag)\w*" \
         r"|monday|friday|saturday|sunday|mon|fri|sat|sun|man|fre|lor|son|ma|pe|la|su"
WD_RANGE = _rx(rf"\b(?:{WD_ANY})\.?(?:\s*(?:-|to|till|thru|through)\s*|\s+)(?:{WD_ANY})\b")

# ---- clock times ---------------------------------------------------------------------------------
_HM = r"(\d{1,2})(?:[.:](\d{2}))?"
_AP = r"(?:\s*([ap])\.?m\b\.?)?"
RANGE = _rx(rf"(?<![\w.:]){_HM}{_AP}\s*(?:-|to|till|until|och|ja|and)\s*(?:klo\s*|kl\.?\s*)?{_HM}{_AP}(?![\d.:]?\d)"
            rf"|(?<![\w.:]){_HM}:?(?:sta|lta)\s+(?:klo\s*)?{_HM}:?(?:een|aan|hin|seen)\b")
TIME = _rx(r"(?<![\w.:,])(\d{1,4})(?:[.:](\d{2}))?(?![\d]|[.:]\d)(?:\s*([ap])\.?m\b\.?)?")
UNIT_AFTER = _rx(r"^\s*(?:min\w*|h\b|tunti\w*|timm\w*|hour\w*|km|kpl|%|eur|€|paiv\w*|day\w*|dag\w*|x\b)")
TIME_PRE = _rx(r"(?:\bklo|\bkl|\bkello|\bklockan|\bat|\bby|\bfrom|\buntil|\btill|\bbefore|\bafter|\bennen|\bfore"
               r"|\befter|\binnan|\bfran|\bsenast|\btidigast|\bnoin|\bca|\bvid|\bhuomenna|\btanaan|\btomorrow"
               r"|\btmrw|\btoday|\bmorgon|\bidag|\bylihuomenna|\w+(?:ai|aina|day|dag)|\baikaisintaan|\bviim\w*"
               r"|\bearliest|\blatest|\blahtien|\b(?:ma|ti|ke|to|pe|la|su|mon|tues?|weds?|thu|thurs?|fri|sat|sun))"
               r"\.?\s*$")
TIME_POST = _rx(r"^\s*(?:a+l+kaen|jal\w*ke+n|asti|saakka|mennessa|och framat|framat|o'?clock|latest|onwards|sharp)\b")
WORD_NUM = [(12, r"kaksitoista|kahde\w*toista|kahteentoista|kahtatoista|twelve|tolv"),
            (11, r"yksitoista|yhde\w*toista|yhteentoista|yhtatoista|eleven|elva"),
            (10, r"kymmen\w*|ten|tio"), (9, r"yhdeksa\w*|nine|nio"), (8, r"kahdeksa\w*|eight|atta"),
            (7, r"seitsema\w*|seven|sju"), (6, r"kuusi|kuude\w*|kuuteen|kuutta|six|sex"),
            (5, r"viisi|viide\w*|viiteen|viitta|five|fem"), (4, r"nelja\w*|four|fyra"), (3, r"kolme\w*|three|tre"),
            (2, r"kaksi|kahde(?:lta|sta|n)|kahteen|kahta|two|tva"), (1, r"yksi|yhde(?:lta|sta|n)|yhteen|yhta|one|ett")]
WORD_RX = [(n, _rx(rf"^(?:{p})$")) for n, p in WORD_NUM]
WORD_TIME = _rx(r"\b(?:(puoli|puolta|half past|half|halv|quarter past|quarter to|kvart over|kvart i|varttia vaille"
                r"|varttia yli|vartin yli)\s+)?(" + "|".join(p for _, p in WORD_NUM) + r")\b")
WORD_SHIFT = {"puoli": -30, "puolta": -30, "half": -30, "halv": -30, "half past": 30, "quarter past": 15,
              "quarter to": -15, "kvart over": 15, "kvart i": -15, "varttia vaille": -15, "varttia yli": 15,
              "vartin yli": 15}
# What may follow a short weekday ('to. klo 10.30', 'pe yhdesta alkaen', 'Korjaus: pe.'): a time or the end.
NEXT_TIME = (r"\s*(?:klo|kl\b|kello|klockan|at\b|\d{1,2}[.:]\d{2}|\d{1,2}\s*(?:[ap]\.?m\b|alkaen|jalkeen|asti"
             r"|mennessa)|puol\w*|half\b|halv\b|(?:" + "|".join(p for _, p in WORD_NUM) + r")\b)")
WD_SHORT = _rx(r"\b(tues|thurs|thur|weds|mon|tue|wed|thu|fri|sat|sun|man|tis|ons|tors|tor|fre|lor|son"
               rf"|ma|ti|ke|to|pe|la|su)\b(\.?)(?={NEXT_TIME}|\s*\d|\s*,|\s*$)")

_TRANS = str.maketrans({"ä": "a", "å": "a", "ö": "o", "–": "-", "—": "-", "’": "'", "é": "e"})
_ABBR = {"viim", "n", "oik", "t", "klo", "kl", "nro", "esim", "ns", "ca", "noin", "puh", "tel", "nr", "no"}
_WD_ABBR = {"to", "ma", "ti", "ke", "pe", "la", "su", "mon", "tue", "tues", "wed", "thu", "thur", "thurs", "fri",
            "sat", "sun"}


def _norm(text: str) -> str:
    text = re.sub(r"\s+", " ", text.lower().translate(_TRANS)).strip()
    return re.sub(rf"\b(?:the )?day after (?:{TOMORROW})\b", "overmorrow", text)  # not 'after' = from


def _sentences(text: str) -> list[str]:
    """Split at . ! ? ; and ' / ', but not after an abbreviation such as 'viim.', nor after a short weekday
    that a time follows ('to. klo 10.30'; but 'Korjaus: pe. 2 sarjaa' splits)."""
    out, start = [], 0
    for m in re.finditer(r"[.!?;]+(?=\s|$)|\s/\s", text):
        prev = re.search(r"(\w+)$", text[start:m.start()])
        word = prev.group(1) if prev and m.group() == "." else ""
        if word in _ABBR or (word in _WD_ABBR and re.match(NEXT_TIME, text[m.end():])):
            continue
        out.append(text[start:m.start()])
        start = m.end()
    out.append(text[start:])
    return [s.strip() for s in out if s.strip()]


def _kind(p: str) -> str | None:
    """The fact a piece states, by keyword priority."""
    p = NOT_BEFORE.sub(" from ", p)  # 'ei ennen klo 13' = from 13
    if PAY.search(p) and HANDOVER.search(p):
        return "release"
    if READY.search(p):
        return "ready"
    if CLOSE.search(p):
        return "close"
    if FROM.search(p) and (OPEN.search(p) or DELIV.search(p)):
        return "open"
    if OPEN.search(p):
        return "openish"
    if PICKUP.search(p) and BEFORE.search(p):
        return "close"
    if DELIV.search(p):
        return "deadline"
    if FROM.search(p):
        return "ready"
    return None


def _pieces(sentence: str) -> list[str]:
    """Comma / 'and' parts. A part without a fact of its own ('ei kun klo 9', 'sorry, i mean 8pm')
    joins the part before it, so a correction lands on the fact it corrects."""
    out: list[str] = []
    parts = re.split(r"(,\s+|\s+(?:ja|and|och|mutta|but|seka)\s+(?=\D))", sentence)
    for sep, part in zip([""] + parts[1::2], parts[0::2]):
        part = PHONE.sub("", part).strip()
        if not part:
            continue
        if out and (_kind(part) is None or CORR.match(part)):
            out[-1] += sep + part
        else:
            out.append(part)
    return out


def _hm(h: str, m: str | None, ap: str | None) -> int | None:
    hour, minute = int(h), int(m or 0)
    if ap:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if ap == "p" else 0)
    return hour * 60 + minute if hour <= 24 and minute < 60 else None


def _denied(text: str, start: int, end: int) -> bool:
    """'not 3pm', '(ei huomenna)', '15 sijaan': the note denies this day or time."""
    return bool(DENY_BEFORE.search(text[max(0, start - 40):start]) or DENY_AFTER.match(text[end:end + 20]))


def _ranges(p: str) -> tuple[list[tuple[int, int, bool]], str]:
    """Opening-hour ranges ('9-16', 'klo 7.00-17.00', '7am - 8pm', '8:sta 21:een') as (opens, closes, saturday),
    and the piece without them. A range is Saturday's when 'la'/'Saturday' stands right before or after it."""
    found = []
    last = 0
    for m in RANGE.finditer(p):
        g = m.groups()
        if g[0]:
            a, b = _hm(g[0], g[1], g[2]), _hm(g[3], g[4], g[5])
        else:  # '8:sta 21:een'
            a, b = _hm(g[6], g[7], None), _hm(g[8], g[9], None)
        # opening hours start at 05:00 or later; '2-3 days' or '4-5 km' is no range
        if a is None or b is None or not 300 <= a < b or UNIT_AFTER.match(p[m.end():]):
            continue
        sat = bool(SATURDAY.search(p[last:m.start()]) or SATURDAY.search(re.split(r",|\d", p[m.end():])[0]))
        found.append((a, b, sat))
        last = m.end()
        p = p[:m.start()] + " " * (m.end() - m.start()) + p[m.end():]
    return found, p


def _times(p: str) -> tuple[list[int], bool]:
    """Clock times in a piece, in order, without denied ones. Also: whether an hour word was ambiguous."""
    out: list[tuple[int, int]] = []
    odd = False
    for m in TIME.finditer(p):
        h, mm, ap = m.groups()
        before, after = p[max(0, m.start() - 40):m.start()], p[m.end():m.end() + 40]
        if len(h) == 4:  # 'kello 1330'
            if mm or not TIME_PRE.search(before):
                continue
            h, mm = h[:2], h[2:]
        elif len(h) == 3:
            continue
        if UNIT_AFTER.match(after):
            continue
        if not (mm or ap or TIME_PRE.search(before) or TIME_POST.match(after)):
            continue
        t = _hm(h, mm, ap)
        if t is not None and not _denied(p, m.start(), m.end()):
            out.append((m.start(), t))
    for m in re.finditer(r"\b(?:noon|midday|keskipaiva\w*|mitt pa dagen)\b", p):
        if not _denied(p, m.start(), m.end()):
            out.append((m.start(), 720))
    for m in WORD_TIME.finditer(p):
        shift, word = m.group(1), m.group(2)
        n = next(n for n, rx in WORD_RX if rx.match(word))
        before, after = p[max(0, m.start() - 40):m.start()], p[m.end():m.end() + 40]
        if not (shift or word.endswith("lta") or TIME_PRE.search(before) or TIME_POST.match(after)):
            continue
        if _denied(p, m.start(), m.end()):
            continue
        hour = n if n >= 9 else n + 12  # working hour 9..17 with that number ("two" = 14:00)
        odd |= 6 <= n <= 8
        out.append((m.start(), hour * 60 + WORD_SHIFT.get(shift or "", 0)))
    return [t for _, t in sorted(out)], odd


def _day(p: str, arr_wd: int, lang: str) -> int | None:
    """Days after arrival named in the piece (last undenied mention wins); None when it names none."""
    p = WD_RANGE.sub(" ", p)
    hits: list[tuple[int, int]] = []
    taken: list[tuple[int, int]] = []
    for rx, off in RELDAY:
        for m in rx.finditer(p):
            if any(a < m.end() and m.start() < b for a, b in taken):
                continue
            taken.append(m.span())
            if not _denied(p, m.start(), m.end()):
                hits.append((m.start(), off))
    wds = [(m.start(), m.end(), WD_IDX[m.group(1)]) for m in WD_FULL.finditer(p)]
    for m in WD_SHORT.finditer(p):
        w = m.group(1)
        if len(w) == 2 and lang == "en" and not m.group(2) and "klo" not in p[m.end():m.end() + 5]:
            continue  # 'to 5pm' in English
        wds.append((m.start(), m.end(), WD_IDX[w]))
    for s, e, wd in wds:
        if not _denied(p, s, e):
            off = (wd - arr_wd) % 7
            hits.append((s, off + 7 if off < 2 else off))  # a weekday is 2..6 days after arrival
    return max(hits)[1] if hits else None


def _facts(text: str, arr: int, lang: str) -> tuple[list[tuple], set[str]]:
    """(kind, site, value) facts and car flags of one note."""
    facts: list[tuple] = []
    flags: set[str] = set()
    arr_day, arr_wd = arr // DAY, (arr // DAY) % 7
    prev: list[str] = []
    last: tuple[int | None, int] | None = None  # (day, time) of the last piece that named a time
    orphan: tuple | None = None  # 'uncertain' of a time no fact used yet ('maksaa klo 12.30, luovutus sen jalkeen')
    for sent in _sentences(_norm(text)):
        for m in MANUAL.finditer(sent):
            if not NEG_WORD.search(sent[:m.start()]):
                flags.add("manual")
        if NOT_AUTO.search(sent):  # 'ei automaatti' = manual
            flags.add("manual")
        paid = bool(PAY.search(sent) and HANDOVER.search(sent))  # 'payment pending, handover from 11'
        if paid:
            facts.append(("release", None, None, -1))
        if PLATES.search(sent):
            flags.add("plates")
        if NO_WINTER.search(sent) or WINTER_OFF.search(sent) \
                or (SUMMER.search(sent) and (MOUNTED.search(sent) or not LOOSE.search(sent))):
            flags.add("summer")
        pieces = _pieces(sent)
        if prev and pieces and CORR.match(pieces[0]) and _kind(pieces[0]) is None:
            pieces = [prev[-1] + ", " + pieces[0]] + pieces[1:]  # 'korjaus: klo 20.' corrects the fact before
            facts[:] = [f for f in facts if f[-1] != len(prev) - 1]
        for piece in pieces:
            idx = len(prev)
            prev.append(piece)
            kind = _kind(piece)
            if kind is None and paid and PAY.search(piece):
                kind = "release"  # 'rahoitus vahvistuu huomenna 13.30': the payment time is the handover time
            site = "delivery" if DELIV.search(piece) else "pickup"
            ranges, rest = _ranges(piece)
            weekday = [r[:2] for r in ranges if not r[2]]
            if weekday:
                facts.append(("hours", site, weekday[-1], idx))
            if len(weekday) < len(ranges):  # Saturday hours: not modelled
                facts.append(("uncertain", None, None, idx))
            times, odd = _times(rest)
            if odd:
                facts.append(("uncertain", None, None, idx))
            day = _day(rest, arr_wd, lang)
            if kind == "release":
                facts.append(("release", None, None, idx))
            if times:
                t = times[-1]  # a correction comes last: 'klo 8, ei kun klo 9'
                last = (day, t)
            elif kind in ("ready", "release", "deadline", "close", "open") and last and ANAPHOR.search(rest):
                day, t = (day if day is not None else last[0]), last[1]  # 'must be there by then'
                if orphan in facts:
                    facts.remove(orphan)
            else:
                if kind in ("ready", "release", "deadline") and (day or PART_OF_DAY.search(rest)) \
                        and not ANAPHOR.search(rest):
                    facts.append(("uncertain", None, None, idx))
                    if kind != "deadline" and day:  # 'valmis vasta torstaina': not before that day
                        facts.append((kind, None, (arr_day + day) * DAY, idx))
                continue
            if kind in ("ready", "release", "deadline"):
                facts.append((kind, None, (arr_day + (day or 0)) * DAY + t, idx))
            elif kind in ("close", "open"):
                facts.append((kind, site, t, idx))
            else:
                orphan = ("uncertain", None, None, idx)
                facts.append(orphan)
    return facts, flags


def read_note(request: dict) -> list[LegNote]:
    """One LegNote per leg of a PriceRequest (dict as in `price_request`). Never raises.

    Every fact goes to the first leg, the dealer's car: in a trade-in the world applies the note to the new
    car only (reveal of other weeks: plates and pickup hours on leg 0, nothing on the old car's leg)."""
    try:
        return _read(request)
    except Exception:  # fail safe: a note we cannot read must not stop quoting
        legs = request.get("legs") or [] if isinstance(request, dict) else []
        return [LegNote(uncertain=True) for _ in legs]


def _read(request: dict) -> list[LegNote]:
    legs = request.get("legs") or []
    out = [LegNote() for _ in legs]
    note = request.get("note") or {}
    facts, flags = _facts(note.get("text") or "", int(request["arrivedAt"]), note.get("language") or "")
    if not legs:
        return out
    latest = max((o["deadline"] for o in request.get("options") or []), default=None)
    ready = release = deadline = None
    after_payment = uncertain = False
    hours: dict[str, list[int | None]] = {"pickup": [None, None], "delivery": [None, None]}
    for kind, site, val, _ in facts:
        if kind == "ready":
            ready = val if ready is None else max(ready, val)  # two ready times: the later one
        elif kind == "release":
            after_payment = True
            release = val if val is not None else release
        elif kind == "deadline":
            deadline = val if deadline is None else min(deadline, val)
        elif kind == "hours":
            hours[site] = [val[0], val[1]]
        elif kind == "close":
            hours[site][1] = val
        elif kind == "open":
            hours[site][0] = val
        else:
            uncertain = True
    uncertain |= after_payment and release is None and ready is None  # paid handover, time unknown
    if deadline is not None and (latest is None or deadline < latest):
        uncertain |= deadline <= request["arrivedAt"]
    else:
        deadline = None  # not tighter than every option: the note sets no deadline
    pu, de = legs[0]["pickup"], legs[0]["delivery"]
    t = max(x for x in (ready, release, -1) if x is not None)
    out[0] = LegNote(ready_at=t if t > pu["window"]["from"] else None, after_payment=after_payment,
                     pickup_hours=_site_hours(pu, hours["pickup"]), delivery_hours=_site_hours(de, hours["delivery"]),
                     deadline=deadline, manual="manual" in flags, plates="plates" in flags,
                     summer_tyres="summer" in flags)
    for ln in out:
        ln.uncertain = uncertain
    return out


def _site_hours(stop: dict, said: list[int | None]) -> tuple[int, int] | None:
    """Real (opens, closes) of a dealer site when the note's hours differ from the stated ones."""
    stated = stop.get("hours")
    if stop.get("privateAddress") or not stated or said == [None, None]:
        return None
    real = (said[0] if said[0] is not None else stated["opens"], said[1] if said[1] is not None else stated["closes"])
    return real if real != (stated["opens"], stated["closes"]) and real[0] < real[1] else None
