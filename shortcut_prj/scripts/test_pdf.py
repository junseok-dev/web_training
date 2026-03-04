import traceback
import os
from pathlib import Path

out_dir = Path(__file__).resolve().parent / "tmp"
out_dir.mkdir(parents=True, exist_ok=True)

# Test ReportLab
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    rl_path = out_dir / "reportlab_test.pdf"
    c = canvas.Canvas(str(rl_path), pagesize=A4)
    c.setFont("Helvetica", 12)
    c.drawString(100, 800, "ReportLab PDF Test")
    c.drawString(100, 780, "If you see this, ReportLab generation succeeded.")
    c.save()
    print("REPORTLAB: OK", rl_path.stat().st_size)
except Exception as e:
    print("REPORTLAB: ERROR")
    traceback.print_exc()

# Test xhtml2pdf (pisa)
try:
    from xhtml2pdf import pisa

    html = """
    <html><body>
    <h1>pisa/xhtml2pdf Test</h1>
    <p>This is a test of xhtml2pdf conversion.</p>
    </body></html>
    """
    pisa_path = out_dir / "pisa_test.pdf"
    with open(pisa_path, "wb") as f:
        res = pisa.CreatePDF(html, dest=f)
    # pisa returns error code via res.err
    print(
        "PISA: OK" if not res.err else "PISA: ERR",
        (
            getattr(pisa_path, "stat", lambda: None)() and pisa_path.stat().st_size
            if pisa_path.exists()
            else "no-file"
        ),
    )
except Exception as e:
    print("PISA: ERROR")
    traceback.print_exc()

print("FILES:", list(out_dir.glob("*")))
