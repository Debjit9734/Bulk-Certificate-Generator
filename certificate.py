import os
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

CERT_DIR = os.getenv("CERT_DIR", "generated_certificates")


def generate_pdf(name, course_name, issue_date, job_id, cert_id):
    """Makes one certificate pdf using the single fixed template and returns the file path."""
    folder = os.path.join(CERT_DIR, "job_" + str(job_id))
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "certificate_" + str(cert_id) + ".pdf")

    width, height = landscape(A4)
    c = canvas.Canvas(path, pagesize=landscape(A4))

    # border
    c.setLineWidth(4)
    c.rect(30, 30, width - 60, height - 60)
    c.setLineWidth(1)
    c.rect(40, 40, width - 80, height - 80)

    c.setFont("Helvetica-Bold", 36)
    c.drawCentredString(width / 2, height - 130, "Certificate of Completion")

    c.setFont("Helvetica", 16)
    c.drawCentredString(width / 2, height - 200, "This is to certify that")

    c.setFont("Helvetica-Bold", 30)
    c.drawCentredString(width / 2, height - 260, name)

    c.setFont("Helvetica", 16)
    c.drawCentredString(width / 2, height - 320, "has successfully completed")

    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(width / 2, height - 360, course_name)

    c.setFont("Helvetica", 14)
    c.drawString(80, 80, "Date: " + issue_date)
    c.drawRightString(width - 80, 80, "Certificate ID: " + str(cert_id))

    c.save()
    return path
