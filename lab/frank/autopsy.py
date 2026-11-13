"""Starter autopsy on a finished week: economics of list price vs typical fee vs booked fee."""
import json, sys, collections, statistics as st
d = json.load(open(sys.argv[1]))
rev, ev = d['reveal'], d['events']
reqs = {r['request']['id']: r for r in rev['requests']}
kinds = collections.Counter(e['kind'] for e in ev)
print(kinds.most_common())
led = collections.defaultdict(int)
for e in ev:
    if e['kind'] == 'ledger': led[e['line']['kind']] += e['line']['cents']
print({k: round(v/100) for k, v in led.items()}, 'total', round(sum(led.values())/100))
# list vs ref
rat = []
for r in rev['requests']:
    q = r['request']; o = q['options'][0]
    rat.append(o['listPriceCents'] / q['referenceFeeCents'])
rat.sort(); print('list(first opt)/ref quantiles', [round(rat[int(len(rat)*p)],2) for p in (0.05,.25,.5,.75,.95)])
# options mix
print('options', collections.Counter(tuple(o['kind'] for o in r['request']['options']) for r in rev['requests']).most_common(8))
print('legs', collections.Counter(len(r['request']['legs']) for r in rev['requests']))
print('notes', sum(1 for r in rev['requests'] if r['request']['note']))
# gig bookings: fee vs ref
gig_order = {}
posted = {}
for e in ev:
    if e['kind'] == 'gig_booked': pass
book = [e for e in ev if e['kind']=='gig_booked']
fees = [e['feeCents'] for e in book]
print('bookings', len(book), 'median fee', st.median(fees)/100)
# order list prices
won = [r for r in rev['requests'] if r['outcome']=='won']
print('won', len(won), 'median list', st.median(r['request']['options'][0]['listPriceCents'] for r in won)/100, 'median ref', st.median(r['request']['referenceFeeCents'] for r in won)/100)
