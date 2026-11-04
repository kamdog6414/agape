import sys, json, base64
heads = {}
for line in open(sys.argv[1]):
    line = line.rstrip("\n")
    if not line.strip():
        continue
    dev, h = line.split(" ", 1)
    heads[dev] = h
for dev in heads:
    peers = {k: v for k, v in heads.items() if k != dev}
    d = {"self": heads[dev], "peers": peers}
    print(dev + " " + base64.b64encode(json.dumps(d, separators=(",", ":")).encode()).decode())
