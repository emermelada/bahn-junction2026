"""Append every won order with a note (request + truth) from finished-world dumps to data/notes_corpus.jsonl."""
import json, sys
out = open('data/notes_corpus.jsonl', 'a', encoding='utf-8')
n = 0
for path in sys.argv[1:]:
    d = json.load(open(path))
    truth = {o['orderId']: o['legs'] for o in d['reveal']['orders']}
    won = {e['order']['id']: e['order'] for e in d['events'] if e['kind'] == 'order_won'}
    for r in d['reveal']['requests']:
        q = r['request']
        if not q['note'] or q['id'] not in truth: continue
        out.write(json.dumps({'source': path, 'request': q, 'option': r['option'], 'order': won.get(q['id']), 'truth': truth[q['id']]}, ensure_ascii=False) + '\n'); n += 1
print(n, 'notes')
