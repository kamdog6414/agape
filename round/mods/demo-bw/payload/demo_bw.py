"""demo-bw test fixture. Plain text, offline, black and white."""


def run(request):
    if type(request) is not dict or request.get("schema") != "agape.demo.request.v0":
        raise ValueError("request schema")
    return {"schema": "agape.demo.result.v0", "text": "demo-bw\n"}
