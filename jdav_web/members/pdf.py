import glob
import logging
import os
import subprocess
import time
from datetime import datetime
from io import BytesIO

from contrib.media import ensure_media_dir
from contrib.media import find_template
from contrib.media import media_dir
from contrib.media import media_path
from contrib.media import serve_media
from django.template.loader import get_template
from PIL import Image
from pypdf import PageObject
from pypdf import PdfReader
from pypdf import PdfWriter
from utils import normalize_filename

logger = logging.getLogger(__name__)


def serve_pdf(filename_pdf):
    return serve_media(filename_pdf, "application/pdf")


def generate_tex(name, template_path, context, date=None):
    filename = normalize_filename(name, date=date)
    filename_tex = filename + ".tex"

    tmpl = get_template(template_path)
    res = tmpl.render(dict(context, creation_date=datetime.today().strftime("%d.%m.%Y")))

    ensure_media_dir()

    with open(media_path(filename_tex), "w", encoding="utf-8") as f:
        f.write(res)
    return filename


def render_docx(name, template_path, context, date=None, save_only=False):
    filename = generate_tex(name, template_path, context, date=date)
    filename_tex = filename + ".tex"
    filename_docx = filename + ".docx"
    oldwd = os.getcwd()
    os.chdir(media_dir())
    result = subprocess.run(
        ["pandoc", filename_tex, "-o", filename_docx],
        capture_output=True,
        text=True,
    )
    if result.stdout:
        logger.debug(f"Pandoc stdout: {result.stdout}")
    if result.stderr:
        logger.debug(f"Pandoc stderr: {result.stderr}")
    time.sleep(1)
    os.chdir(oldwd)
    if save_only:
        return filename_docx
    return serve_media(filename_docx, "application/docx")


def render_tex_with_attachments(name, template_path, context, attachments, save_only=False):
    rendered_pdf = render_tex(name, template_path, context, save_only=True)

    reader = PdfReader(media_path(rendered_pdf))
    writer = PdfWriter()
    writer.append(reader)

    pdf_add_attachments(writer, attachments)

    with open(media_path(rendered_pdf), "wb") as output_stream:
        writer.write(output_stream)

    if save_only:
        return rendered_pdf
    return serve_pdf(rendered_pdf)


def render_tex(name, template_path, context, date=None, save_only=False):
    filename = generate_tex(name, template_path, context, date=date)
    filename_tex = filename + ".tex"
    filename_pdf = filename + ".pdf"
    # compile using pdflatex
    oldwd = os.getcwd()
    os.chdir(media_dir())
    result = subprocess.run(
        ["pdflatex", "-halt-on-error", filename_tex],
        capture_output=True,
        text=True,
    )
    if result.stdout:
        logger.debug(f"pdflatex stdout: {result.stdout}")
    if result.stderr:
        logger.debug(f"pdflatex stderr: {result.stderr}")
    time.sleep(1)

    # do some cleanup
    for f in glob.glob("*.log"):
        os.remove(f)
    for f in glob.glob("*.aux"):
        os.remove(f)
    # os.remove(filename_tex)
    # os.remove(filename_table)

    os.chdir(oldwd)

    if save_only:
        return filename_pdf
    return serve_pdf(filename_pdf)


def pdf_add_attachments(pdf_writer, attachments):
    for fp in attachments:
        try:
            if fp.endswith(".pdf"):
                # append pdf directly
                img_pdf = PdfReader(fp)
            else:
                # convert ensures that png files with an alpha channel can be appended
                img = Image.open(fp).convert("RGB")
                img_io = BytesIO()
                img.save(img_io, "pdf")
                img_io.seek(0)
                img_pdf = PdfReader(img_io)
            img_pdf_scaled = scale_pdf_to_a4(img_pdf)
            pdf_writer.append(img_pdf_scaled)

        except Exception as e:
            logger.warning(f"Could not add image under filepath {fp}: {e}.")


def scale_pdf_page_to_a4(page):
    A4_WIDTH, A4_HEIGHT = 595, 842

    page_width = page.mediabox.width
    page_height = page.mediabox.height
    scale_x = A4_WIDTH / page_width
    scale_y = A4_HEIGHT / page_height
    scale_factor = min(scale_x, scale_y)

    new_page = PageObject.create_blank_page(width=A4_WIDTH, height=A4_HEIGHT)
    page.scale_by(scale_factor)
    x_offset = (A4_WIDTH - page.mediabox.width) / 2
    y_offset = (A4_HEIGHT - page.mediabox.height) / 2
    new_page.merge_translated_page(page, x_offset, y_offset)

    return new_page


def scale_pdf_to_a4(pdf):
    scaled_pdf = PdfWriter()
    for page in pdf.pages:
        scaled_pdf.add_page(scale_pdf_page_to_a4(page))

    return scaled_pdf


def fill_pdf_form(name, template_path, fields, attachments=[], date=None, save_only=False):
    filename = normalize_filename(name, date=date)
    filename_pdf = filename + ".pdf"

    path = find_template(template_path)

    ensure_media_dir()

    reader = PdfReader(path)
    writer = PdfWriter()

    writer.append(reader)

    writer.update_page_form_field_values(None, fields, auto_regenerate=False)

    pdf_add_attachments(writer, attachments)

    with open(media_path(filename_pdf), "wb") as output_stream:
        writer.write(output_stream)

    if save_only:
        return filename_pdf
    return serve_pdf(filename_pdf)


def merge_pdfs(name, filenames, date=None, save_only=False):
    merger = PdfWriter()

    for pdf in filenames:
        merger.append(media_path(pdf))

    filename = normalize_filename(name, date=date)
    filename_pdf = filename + ".pdf"
    merger.write(media_path(filename_pdf))
    merger.close()

    if save_only:
        return filename_pdf
    return serve_pdf(filename_pdf)
