import json, sys, collections, math, statistics as st
d = json.load(open(sys.argv[1])); m = json.load(open('data/map.json'))
pl = {p['id']: p for p in m['places']}; road = {(r['from'], r['to']): r for r in m['roads']}
def km(a, b):
    A, B = pl[a], pl[b]; x = math.radians(B['lon']-A['lon'])*math.cos(math.radians((A['lat']+B['lat'])/2)); y = math.radians(B['lat']-A['lat'])
    return 6371*math.hypot(x, y)
ro = {r['id']: r for r in d['roster']}
home = collections.Counter(r['homePlaceId'] for r in d['roster'])
reqs = {r['request']['id']: r['request'] for r in d['reveal']['requests']}
ev = d['events']
# requests per pickup town and drivers per town
pick = collections.Counter(q['legs'][0]['pickup']['placeId'] for q in reqs.values())
print('town  drivers  requests(pickup)  drivers within30km')
for p in sorted(pl, key=lambda p: -pick[p]):
    near = sum(c for h, c in home.items() if km(h, p) <= 30)
    print(f"{pl[p]['name'][:12]:12s} {home[p]:4d} {pick[p]:4d} {near:4d}")
gig_order = {e['gigId']: (e['orderId'], e['leg']) for e in ev if e['kind'] == 'picked_up'}
started = {e['gigId'] for e in ev if e['kind'] == 'gig_started'}
rows = []
for e in ev:
    if e['kind'] == 'gig_booked' and e['gigId'] in gig_order and e['gigId'] in started:
        oid, leg = gig_order[e['gigId']]; q = reqs[oid]; L = q['legs'][leg]
        h = ro[e['driverId']]['homePlaceId']; p, dl = L['pickup']['placeId'], L['delivery']['placeId']
        rows.append((e['feeCents']/q['referenceFeeCents'], km(h, p), km(dl, h), road[(p, dl)]['minutes'], q['referenceFeeCents']))
print(len(rows), 'booked+started gigs')
for lo, hi in [(0, 10), (10, 40), (40, 100), (100, 250), (250, 2000)]:
    sub = [r for r in rows if lo <= r[1] < hi]
    if sub: print(f'home->pickup {lo}-{hi}km n={len(sub)} median fee/ref {st.median(r[0] for r in sub):.2f}')
for lo, hi in [(0, 10), (10, 40), (40, 100), (100, 250), (250, 2000)]:
    sub = [r for r in rows if lo <= r[2] < hi]
    if sub: print(f'delivery->home {lo}-{hi}km n={len(sub)} median fee/ref {st.median(r[0] for r in sub):.2f}')
