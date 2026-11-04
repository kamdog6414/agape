import importlib.util,sys
sp=importlib.util.spec_from_file_location("x","/workspace/xchain-v1/xchain.py");x=importlib.util.module_from_spec(sp);sp.loader.exec_module(x)
oc=x.order_consistent; P=["A","B","C","D"]
assert oc(["A","B","B","C"],P)==(True,"ok (repeat 1)")
assert oc(["A","B","C"],P)==(True,"ok")
assert oc(["A","B","A"],P)[0] is False
assert oc(["C","B"],P)[0] is False
assert oc(["A","C","C","B"],P)[0] is False
assert oc(["A","X"],P)==(False,"missing X")
print("tests OK")
assert oc(["A","A"],["A","A","B"])==(True,"ok")
print("tests OK2")
