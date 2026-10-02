from triagekit.adapters.bitext import load_bitext


def test_bitext_adapter(tmp_path):
    p = tmp_path / "b.csv"
    p.write_text("flags,instruction,category,intent,response\nB,I want a refund,REFUND,get_refund,ok\nB,where is my order,ORDER,track_order,ok\nB,where is my order,ORDER,track_order,ok\n")
    rows = load_bitext(p)
    assert [(r.label, r.category) for r in rows] == [(1, "get_refund"), (0, "track_order")]
    assert len(load_bitext(p, dedupe=False)) == 3
