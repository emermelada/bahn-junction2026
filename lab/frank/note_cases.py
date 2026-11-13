"""Hand-written note cases, made from the rules in RULES.md and NOT from the corpus: a held-out check that
the reader learned the language rules rather than the corpus. Each case: (language, note, expected LegNote
fields that differ from the default, request options). Default request: arrives Tue 10:00, one leg between
two dealer sites open 7:00-20:00, latest option deadline next Mon 20:00.
"""
from __future__ import annotations

from spreadbot.notes import LegNote, read_note

D = 1440
TUE, WED, THU, FRI = 1, 2, 3, 4
HOURS = {"opens": 420, "closes": 1200, "weekdays": [0, 1, 2, 3, 4], "saturday": None}


def at(day: int, h: int, m: int = 0) -> int:
    return day * D + h * 60 + m


FRI_ARR, SAT_ARR = at(FRI, 14), at(5, 10)


def request(text: str, lang: str, ppriv: bool = False, dpriv: bool = False, arr: int = at(TUE, 10)) -> dict:
    def stop(place: str, private: bool) -> dict:
        return {"placeId": place, "privateAddress": private, "window": {"from": arr, "to": at(FRI, 20)},
                "hours": None if private else HOURS}
    return {"arrivedAt": arr, "legs": [{"car": {}, "pickup": stop("a", ppriv), "delivery": stop("b", dpriv)}],
            "options": [{"kind": "next_day", "deadline": at(WED, 20)},
                        {"kind": "within_3_days", "deadline": at(7, 20)}],
            "note": {"text": text, "language": lang}}


CASES = [
    ("fi", "Valmis vasta torstaina klo 12", dict(ready_at=at(THU,12))),
    ("sv", "Klar först på fredag kl 9", dict(ready_at=at(FRI,9))),
    ("en", "ready Thurs 2pm", dict(ready_at=at(THU,14))),
    ("fi", "valmis to klo 14", dict(ready_at=at(THU,14))),
    ("fi", "Noudettavissa ylihuomenna klo 10", dict(ready_at=at(THU,10))),
    ("sv", "kan hämtas i övermorgon kl 10", dict(ready_at=at(THU,10))),
    ("en", "ready the day after tomorrow at 10am", dict(ready_at=at(THU,10))),
    ("fi", "Auton saa vasta kahdelta", dict(ready_at=at(TUE,14))),
    ("fi", "Valmis puoli kolme", dict(ready_at=at(TUE,14,30))),
    ("sv", "Klar halv fyra", dict(ready_at=at(TUE,15,30))),
    ("en", "ready at half three", dict(ready_at=at(TUE,14,30))),
    ("en", "not ready before 3pm", dict(ready_at=at(TUE,15))),
    ("en", "ready tomorrow at 9:30, not 10:30", dict(ready_at=at(WED,9,30))),
    ("fi", "valmis huomenna klo 10. korjaus: klo 12", dict(ready_at=at(WED,12))),
    ("fi", "Perillä oltava viimeistään torstaina kello 14", dict(deadline=at(THU,14))),
    ("sv", "Leverans senast i morgon kl 15", dict(deadline=at(WED,15))),
    ("sv", "Leveras senast på torsdag klockan två", dict(deadline=at(THU,14))),
    ("en", "deliver by Friday 3 pm", dict(deadline=at(FRI,15))),
    ("fi", "Vastaanotto vain klo 16 asti", dict(delivery_hours=(420,960))),
    ("en", "We are open 9-16", dict(pickup_hours=(540,960))),
    ("sv", "Mottagaren stänger kl 17", dict(delivery_hours=(420,1020))),
    ("sv", "Öppet vardagar 10-15", dict(pickup_hours=(600,900))),
    ("sv", "Hämtas före kl 15", dict(pickup_hours=(420,900))),
    ("sv", "Bilen har manuell växellåda", dict(manual=True)),
    ("sv", "Bilen saknar registreringsskyltar, ta med provskyltar", dict(plates=True)),
    ("sv", "Bilen har fortfarande sommardäck", dict(summer_tyres=True)),
    ("sv", "Sommardäck i bagageutrymmet, ska med", dict()),
    ("sv", "Betalning först, bilen lämnas ut efter kl 13", dict(after_payment=True, ready_at=at(TUE,13))),
    ("en", "Payment pending, handover from tomorrow 11:00", dict(after_payment=True, ready_at=at(WED,11))),
    ("fi", "Ei kilpiä", dict(plates=True)),
    ("fi", "Talvirenkaat takakontissa, kesärenkaat alla", dict(summer_tyres=True)),
    ("fi", "Vaihteisto manuaali", dict(manual=True)),
    ("en", "Not a manual", dict()),
    ("en", "Ready Friday (not Thursday) 10:00", dict(ready_at=at(FRI,10))),
    ("fi", "tänään klo 15 jälkeen", dict(ready_at=at(TUE,15))),
    ("fi", "Perillä viimeistään huomenna kahdelta", dict(deadline=at(WED,14))),
    ("fi", "noudettavissa huomenna yhdeksästä alkaen", dict(ready_at=at(WED,9))),
    ("en", "at destination by tmrw noon", dict(deadline=at(WED,12))),
    ("fi", "Valmis vasta klo 16.15", dict(ready_at=at(TUE,16,15))),
    ("fi", "liike suljetaan klo 17", dict(pickup_hours=(420,1020))),
    ("sv", "Vi stänger 16:30", dict(pickup_hours=(420,990))),
    ("en", "Receiving 8am-4pm only", dict(delivery_hours=(480,960))),
    ("en", "Pickup only between 10 and 14", dict(pickup_hours=(600,840))),
    ("fi", "kello 13.30 jälkeen voi noutaa", dict(ready_at=at(TUE,13,30))),
    ("en", "Car is ready now", dict()),
    ("en", "Plates are missing", dict(plates=True)),
    ("en", "On summer tyres", dict(summer_tyres=True)),
    ("fi", "auto on kesärenkailla", dict(summer_tyres=True)),
    ("en", "Delivery hours Mon-Fri 8-16", dict(delivery_hours=(480,960))),
    ("en", "Must arrive before 2 pm today", dict(deadline=at(TUE,14))),
    ("en", "Deadline Friday 12:00", dict(deadline=at(FRI,12))),
    ("en", "needs to be there by Thursday 1pm", dict(deadline=at(THU,13))),
    ("en", "Pickup after 12 tomorrow", dict(ready_at=at(WED,12))),
    ("en", "Can be collected from 1 pm on Thursday", dict(ready_at=at(THU,13))),
    ("fi", "Valmis 14.00 jälkeen", dict(ready_at=at(TUE,14))),
    ("fi", "Valmis huomenna klo 10 ja perillä pe klo 16 mennessä", dict(ready_at=at(WED,10), deadline=at(FRI,16))),
    ("en", "ready at 11 and must be there by 4pm", dict(ready_at=at(TUE,11), deadline=at(TUE,16))),
    ("fi", "Nouto klo 8 ja klo 15 välillä", dict(pickup_hours=(480,900))),
    ("fi", "klo 7.30-16", dict(pickup_hours=(450,960))),
    ("fi", "Liike auki 8–16, la suljettu", dict(pickup_hours=(480,960))),
    ("en", "Receiving Mon-Fri until 3pm", dict(delivery_hours=(420,900))),
    ("en", "Pickup before noon", dict(pickup_hours=(420,720))),
    ("en", "Ready by 11", dict(ready_at=at(TUE,11))),
    ("fi", "Kesärenkaat mukana takakontissa", dict()),
    ("fi", "Rekisterikilvet irrotettu", dict(plates=True)),
    ("fi", "perillä klo 15 eikä 14", dict(deadline=at(TUE,15))),
    ("en", "arrive by 5pm rather than 4pm", dict(deadline=at(TUE,17))),
    ("en", "Ready Thur 9am", dict(ready_at=at(THU,9))),
    ("sv", "Klar på torsdag efter kl 11", dict(ready_at=at(THU,11))),
    ("fi", "Haettavissa pe. klo 8 alkaen", dict(ready_at=at(FRI,8))),
    ("fi", "Perillä viimeistään ylihuomenna klo 11.15", dict(deadline=at(THU,11,15))),
    ("en", "Collect between 9 and 15 only", dict(pickup_hours=(540,900))),
    ("en", "Shop open until 5pm", dict(pickup_hours=(420,1020))),
    ("en", "Workshop closes at 4.30pm", dict(pickup_hours=(420,990))),
    ("fi", "Valmis klo 9.00. Ref 1430", dict()),
    ("en", "Key box code 1530, ready at 9", dict()),
    ("fi", "4 kesärengasta takakontissa", dict()),
    ("en", "Manual gearbox, no plates, still on summer tyres", dict(manual=True, plates=True, summer_tyres=True)),
    ("fi", "Myyjä paikalla 15.00-18.00", dict(), {"ppriv": True}),
    ("en", "Owner home 14-17", dict(), {"ppriv": True}),
    # harmless: expect nothing
    ("fi", "Asiakas maksaa käteisellä toimituksen yhteydessä", dict()),
    ("fi", "Kuljettaja maksaa polttoaineen, kuitit talteen", dict()),
    ("fi", "Avaimet tiskiltä klo 8 jälkeen", dict()),
    ("sv", "Ring kunden 30 minuter innan", dict()),
    ("en", "Two sets of tyres, one on the back seat", dict()),
    ("fi", "Puhelin 040 123 4567", dict()),
    ("en", "Winter tyres in the boot", dict()),
    ("en", "Automatic gearbox", dict()),
    ("fi", "Tankattu täyteen, 2 avainta. Kiitos!", dict()),
    # facts
    ("fi", "Valmis aikaisintaan to 13", dict(ready_at=at(THU,13))),
    ("fi", "valmis n. klo 14", dict(ready_at=at(TUE,14))),
    ("sv", "Hämtas tidigast kl 13 på fredag", dict(ready_at=at(FRI,13))),
    ("fi", "Vastaanotto suljettu klo 15 jälkeen", dict(delivery_hours=(420,900))),
    ("sv", "Leverans måste ske före kl 14 i morgon", dict(deadline=at(WED,14))),
    ("sv", "Framme senast kl. 14.30 på torsdag", dict(deadline=at(THU,14,30))),
    ("fi", "Toimitus viimeistään perjantaina puoli kaksi", dict(deadline=at(FRI,13,30))),
    ("fi", "Perillä ennen klo 17 torstaina", dict(deadline=at(THU,17))),
    ("en", "Delivery by 1700 Thursday", dict(deadline=at(THU,17))),
    ("en", "Receiving hours 08-16", dict(delivery_hours=(480,960))),
    ("fi", "Aukioloajat ma-pe 8-16, la 10-14", dict(pickup_hours=(480,960))),
    ("en", "Open 8-16 weekdays, Saturdays 10-14", dict(pickup_hours=(480,960))),
    ("fi", "Maksu ensin. Auto luovutetaan torstaina klo 12", dict(after_payment=True, ready_at=at(THU,12))),
    ("fi", "Valmis torstaina klo 12. Korjaus: perjantaina.", dict(ready_at=at(FRI,12))),
    ("fi", "Perillä huomenna klo 16 - ei vaan klo 15", dict(deadline=at(WED,15))),
    ("en", "Delivery tomorrow before 3pm, correction 2pm", dict(deadline=at(WED,14))),
    ("sv", "Hämtas efter kl 12, ej före", dict(ready_at=at(TUE,12))),
    ("en", "sorry typo: must arrive by thu 15:00", dict(deadline=at(THU,15))),
    ("fi", "Haku vain arkisin 10–15", dict(pickup_hours=(600,900))),
    ("fi", "Noutopaikka auki 10-15", dict(pickup_hours=(600,900))),
    ("fi", "Vastaanotto: arkisin 8.30 - 16", dict(delivery_hours=(510,960))),
    ("sv", "Leverans kan ske 8-16", dict(delivery_hours=(480,960))),
    ("fi", "Käsivaihteinen", dict(manual=True)),
    ("en", "Requires manual licence (stick)", dict(manual=True)),
    ("fi", "Automaattivaihteisto", dict()),
    ("en", "Not automatic!", dict(manual=True)),
    ("fi", "Ei automaatti", dict(manual=True)),
    ("fi", "Siirtokilvet tarvitaan", dict(plates=True)),
    ("en", "No reg plates fitted", dict(plates=True)),
    ("en", "Summer tyres fitted", dict(summer_tyres=True)),
    ("fi", "Kesäkumit alla", dict(summer_tyres=True)),
    ("sv", "Sommarhjul monterade", dict(summer_tyres=True)),
    ("fi", "Ei talvirenkaita", dict(summer_tyres=True)),
    ("en", "Not ready until Thursday 9am", dict(ready_at=at(THU,9))),
    ("en", "won't be ready till tmrw 1pm", dict(ready_at=at(WED,13))),
    ("fi", "Auto valmistuu vasta perjantaina kymmeneltä", dict(ready_at=at(FRI,10))),
    ("sv", "Bilen blir klar på torsdag vid tolv", dict(ready_at=at(THU,12))),
    ("en", "Pick up from 4 pm on Friday, not earlier", dict(ready_at=at(FRI,16))),
    ("fi", "Saa hakea ylihuomenna kello 9.15 lähtien", dict(ready_at=at(THU,9,15))),
    ("en", "Customer needs it by Thursday 11:00", dict(deadline=at(THU,11))),
    ("fi", "Asiakas tarvitsee auton torstaina klo 11 mennessä", dict(deadline=at(THU,11))),
    ("fi", "valmis ma klo 12", dict(ready_at=at(7,12)), {"arr": FRI_ARR}),
    ("sv", "Klar på tisdag kl 10", dict(ready_at=at(8,10)), {"arr": FRI_ARR}),
    ("en", "ready tomorrow 10am", dict(ready_at=at(5,10)), {"arr": FRI_ARR}),
    ("fi", "Noudettavissa maanantaina klo 9", dict(ready_at=at(7,9)), {"arr": SAT_ARR}),
    ("en", "Ready Wed 8:00", dict(ready_at=at(9,8)), {"arr": FRI_ARR}),
    ("fi", "Haettava ennen klo 15", dict(), {"ppriv": True}),
    ("fi", "Vastaanotto klo 16 asti", dict(), {"dpriv": True}),
    # second round: variants of the holdout patterns, not taken from any note
    ("en", "must arrive by tommorow 15:00", dict(deadline=at(WED, 15))),
    ("en", "ready tomorow 11:00", dict(ready_at=at(WED, 11))),
    ("fi", "valmis huomeenna klo 12", dict(ready_at=at(WED, 12))),
    ("fi", "Liike sulkee klo 16", dict(pickup_hours=(420, 960))),
    ("fi", "Vastaanotto sulkeutuu klo 16.30", dict(delivery_hours=(420, 990))),
    ("fi", "kohde sulkee neljältä", dict(delivery_hours=(420, 960))),
    ("fi", "haettava ennen puolta neljää", dict(pickup_hours=(420, 930))),
    ("fi", "valmis to puoli kaksi", dict(ready_at=at(THU, 13, 30))),
    ("fi", "noudettavissa pe kymmenestä alkaen", dict(ready_at=at(FRI, 10))),
    ("fi", "Maksu tulee perjantaina klo 10, auton saa sen jälkeen", dict(after_payment=True, ready_at=at(FRI, 10))),
    ("en", "Financing confirmed tomorrow 11:00, pick up only after that", dict(after_payment=True,
                                                                               ready_at=at(WED, 11))),
    ("en", "Customer collects it Friday 15:00, has to be there by then", dict(deadline=at(FRI, 15))),
    ("fi", "perillä viim. to klo 14. Korjaus: pe.", dict(deadline=at(FRI, 14))),
    ("en", "recieving weekdays 9-15 only", dict(delivery_hours=(540, 900))),
    ("en", "No one here after 17:00", dict(pickup_hours=(420, 1020))),
    ("en", "Winter tyres missing", dict(summer_tyres=True)),
    ("fi", "Talvirenkaat puuttuu vielä", dict(summer_tyres=True)),
    ("en", "deliver the day after tomorrow by 2pm", dict(deadline=at(THU, 14))),
    ("sv", "Ingen brådska", dict()),
]


def trade_in() -> list[str]:
    """Two legs: new car dealer a -> customer b, old car b -> dealer a. Every fact belongs to the new car
    (leg 0), as the reveal of other weeks shows; its delivery is private, so receiving hours drop out."""
    a = at(TUE, 10)
    req = request("Valmis klo 14. Vastaanotto klo 16 asti. Liike kiinni klo 18. Manuaali. "
                  "Perillä huomenna klo 12 mennessä", "fi")
    dealer, home = req["legs"][0]["pickup"], {"placeId": "b", "privateAddress": True,
                                              "window": {"from": at(WED, 9), "to": at(WED, 10)}, "hours": None}
    req["legs"] = [{"pickup": dealer, "delivery": home}, {"pickup": home, "delivery": dealer}]
    want = [LegNote(ready_at=a + 240, pickup_hours=(420, 1080), deadline=at(WED, 12), manual=True),
            LegNote()]
    got = read_note(req)
    return [f"trade-in leg {i}: ours {g} want {w}" for i, (g, w) in enumerate(zip(got, want)) if g != w]


def check() -> tuple[int, list[str]]:
    """(number of cases, list of misses)."""
    misses = []
    for case in CASES:
        lang, text, want = case[:3]
        got = read_note(request(text, lang, **(case[3] if len(case) > 3 else {})))[0]
        exp = LegNote(**want, uncertain=got.uncertain)  # 'uncertain' is advisory, not scored here
        if got != exp:
            diff = {k: (v, getattr(exp, k)) for k, v in vars(got).items() if v != getattr(exp, k)}
            misses.append(f"{text!r}: ours/want {diff}")
    return len(CASES) + 1, misses + trade_in()
