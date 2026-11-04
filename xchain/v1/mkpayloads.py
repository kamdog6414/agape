import sys, json, base64
# args: N R V P T
N,R,V,P,T = sys.argv[1:6]
heads = {"NIKOLAI":N,"ROACH":R,"SOV":V,"SOAP":P,"TV":T}
def payload(self_dev):
    peers = {k:v for k,v in heads.items() if k!=self_dev}
    d = {"self": heads[self_dev], "peers": peers}
    return base64.b64encode(json.dumps(d,separators=(",",":")).encode()).decode()
for dev in ["NIKOLAI","ROACH","SOV","SOAP","TV"]:
    print(dev+" "+payload(dev))
