#!/usr/bin/env python3
# Resident witness v0 — runs ON a muse gadget (Nikolai: Spark, Roach: Wonder).
# Watches the local muse-hub; on a new round it assembles the evidence packet
# (round + chain state + hub status recomputed on this box) and:
#   - key file present: calls the Meta Model API for an independent verdict
#   - key file absent:  files a DRY-RUN post with the exact prompt it would send
# Verdicts are evidence, not authority. Files to the local board + the plane.
import json, os, sys, time, hashlib, subprocess, datetime, urllib.request

HOME = os.path.expanduser('~')
RW = os.path.join(HOME, 'resident-witness')
STATE = os.path.join(RW, 'state.json')
LEDGER = os.path.join(RW, 'spend.csv')
KEY = os.path.join(HOME, '.config', 'meta', 'MODEL_API_KEY')
HUB = os.path.join(HOME, 'muse-hub')
BOARD = os.path.join(HOME, 'fullcircle', 'agape', 'board', 'posts')
PLANE = '/mnt/fullstock/ghostie/live-link-20261102/desk'
BOX = os.environ.get('RW_BOX', 'NIKOLAI')
MODEL = os.environ.get('RW_MODEL', 'muse-spark-1.3')
PRICES = {'muse-spark-1.3': (1.25, 4.25), 'muse-wonder-1.0': (4.00, 20.00)}

def load(p):
    with open(p) as f:
        return json.load(f)

def evidence():
    latest = load(os.path.join(HUB, 'latest.json'))
    chain = load(os.path.join(HUB, 'chain-state.json'))
    try:
        status = subprocess.run(['python3', os.path.join(HUB, 'hub_status.py')],
                                capture_output=True, text=True, timeout=60).stdout.strip()
    except Exception as e:
        status = '(hub_status failed: %s)' % e
    return latest, chain, status

def build_prompt(latest, chain, status):
    return ("You are a resident cloud witness for the FullCircle three-gadget witness hub "
            "(submission name QUICK), called from the gadget " + BOX + " itself. You witness; "
            "you do not govern.\nLATEST ROUND: " + json.dumps(latest) +
            "\nCHAIN STATE: " + json.dumps(chain) +
            "\nHUB STATUS (produced on this box): " + status +
            "\nDo three things, briefly: (1) check consistency: do the round stamps match the "
            "chain heads member for member, and is the baseline's termination at the named "
            "genesis evidenced in what is presented? (2) give one verdict word: WITNESS-PASS, "
            "WITNESS-FINDING, or WITNESS-UNKNOWN, with a one-line basis. (3) name anything "
            "anomalous in the data exactly as presented. End your reply with your model name "
            "on its own final line.")

def call_api(prompt):
    key = open(KEY).read().strip()
    payload = {'model': MODEL,
               'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': prompt}]}],
               'max_tokens': 16384}
    req = urllib.request.Request('https://api.ai.meta.com/v1/chat/completions',
                                 data=json.dumps(payload).encode(), method='POST')
    req.add_header('Content-Type', 'application/json')
    req.add_header('Authorization', 'Bearer ' + key)
    with urllib.request.urlopen(req, timeout=300) as resp:
        result = json.loads(resp.read())
    text = result['choices'][0]['message']['content']
    usage = result.get('usage', {}) or {}
    pin, pout = PRICES.get(MODEL, (0, 0))
    cost = (usage.get('prompt_tokens', 0) * pin + usage.get('completion_tokens', 0) * pout) / 1e6
    return text, usage, cost

def file_post(kind, body):
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    name = '%s-%s-RESIDENT-WITNESS-%s.txt' % (stamp, BOX, kind)
    h = hashlib.sha256(body.encode()).hexdigest()
    for d in (BOARD, PLANE):
        try:
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, name), 'w') as f:
                f.write(body)
            with open(os.path.join(d, name + '.sha256'), 'w') as f:
                f.write(h + '  ' + name + '\n')
        except Exception as e:
            print('file fail %s: %s' % (d, e))
    return name, h

def once():
    os.makedirs(RW, exist_ok=True)
    st = load(STATE) if os.path.exists(STATE) else {}
    latest, chain, status = evidence()
    ts = latest.get('ts')
    if st.get('last_round') == ts:
        print('NO_NEW_ROUND', ts)
        return
    prompt = build_prompt(latest, chain, status)
    if os.path.exists(KEY):
        text, usage, cost = call_api(prompt)
        body = ("RESIDENT WITNESS - %s (model %s)\nRound: %s\nMode: LIVE\nUsage: %s\nCost USD: %.6f\n---\n%s\n"
                % (BOX, MODEL, ts, json.dumps(usage), cost, text))
        kind = 'LIVE'
        with open(LEDGER, 'a') as f:
            f.write('%s,%s,%s,%s,%s,%.6f\n' % (datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    ts, MODEL, usage.get('prompt_tokens', 0), usage.get('completion_tokens', 0), cost))
    else:
        body = ("RESIDENT WITNESS - %s (model %s)\nRound: %s\nMode: DRY-RUN - no key file on this box; nothing was sent.\n"
                "Evidence packet sha256: %s\n---\nPROMPT THAT WILL BE SENT WHEN THE KEY LANDS:\n%s\n"
                % (BOX, MODEL, ts, hashlib.sha256(prompt.encode()).hexdigest(), prompt))
        kind = 'DRYRUN'
    name, h = file_post(kind, body)
    st['last_round'] = ts
    with open(STATE, 'w') as f:
        json.dump(st, f)
    print('FILED', kind, name, h)

if __name__ == '__main__':
    if '--loop' in sys.argv:
        while True:
            try:
                once()
            except Exception as e:
                print('ERR', e)
            time.sleep(20)
    else:
        once()
