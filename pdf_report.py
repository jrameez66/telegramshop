"""User stats ka chhota PDF report (pure-Python, koi library nahi)."""
import io
import zlib


def _esc(t):
    return str(t).replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def make_stats_pdf(shop, u, s, period_label, deps_total, ref_cnt):
    lines = [
        (f"{shop} — User Stats Report", 18),
        (f"User: {u['first_name']} (@{u['username'] or '-'})  ID: {u['user_id']}", 11),
        (f"Period: {period_label}", 11),
        ("", 11),
        (f"Orders:            {s['orders']}", 13),
        (f"Items Bought:      {s['items']}", 13),
        (f"Total Spent:       {s['spent']:g} USDT", 13),
        (f"Deposits (period): {s['deposits']:g} USDT", 13),
        (f"Deposits (all):    {deps_total:g} USDT", 13),
        (f"Balance:           {u['balance']:g} USDT", 13),
        (f"Referrals:         {ref_cnt}  (earned {u['ref_earnings']:g} USDT)", 13),
    ]
    content = "BT\n"
    y = 780
    for text, size in lines:
        content += f"/F1 {size} Tf 50 {y} Td ({_esc(text)}) Tj\n"
        content += f"-50 -{int(size * 1.8)} Td\n" if text else ""
        y -= int(size * 1.8)
    content += "ET"
    comp = zlib.compress(content.encode())

    objs = []
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>")
    objs.append(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(comp)
                + comp + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = [0]
    for i, o in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + o + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\n"
              f"startxref\n{xref}\n%%EOF".encode())
    return out.getvalue()
