"""Preserve native math layout and visual regions without inventing transcription."""
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET


def layout_text(spans):
    """Recover only adjacent, small raised integer runs; preserve raw spans separately.

    This is a layout heuristic, not equation recognition. Fractions, radicals,
    scripts and diagram meaning still require inspection of the image.
    """
    lines = []
    for span in sorted(spans, key=lambda s: (s['top'], s['left'])):
        line = next((line for line in lines if abs((line[0]['top'] + line[0]['height']/2) - (span['top'] + span['height']/2)) <= 3), None)
        if line is None:
            lines.append([span])
        else:
            line.append(span)
    output, recovered = [], []
    for line in lines:
        pieces = []
        previous = None
        for span in sorted(line, key=lambda s: s['left']):
            text = span['text']
            if (previous and re.fullmatch(r'[0-9]+', text)
                    and re.search(r'[A-Za-z0-9)]$', previous['text'])
                    and span['font_size'] <= previous['font_size'] * .75
                    and span['top'] + span['height'] < previous['top'] + previous['height'] - 1
                    and -2 <= span['left'] - (previous['left'] + previous['width']) <= 3):
                pieces.append('^(' + text + ')')
                recovered.append(dict(text=text, left=span['left'], top=span['top']))
            else:
                if previous and span['left'] - (previous['left'] + previous['width']) > 3:
                    pieces.append(' ')
                pieces.append(text)
            previous = span
        output.append(''.join(pieces))
    return '\n'.join(output), recovered


def recover_fractions(spans, image, bbox):
    """Recognize simple stacked tokens only when the crop contains a fraction bar."""
    pixels = image.convert('RGB')
    used, candidates, replacement = set(), [], []
    for i, numerator in enumerate(spans):
        if i in used or not re.fullmatch(r'[A-Za-z0-9]+', numerator['text']):
            continue
        for j, denominator in enumerate(spans):
            if j == i or j in used or not re.fullmatch(r'[A-Za-z0-9]+', denominator['text']):
                continue
            gap = denominator['top'] - (numerator['top'] + numerator['height'])
            nc = numerator['left'] + numerator['width']/2
            dc = denominator['left'] + denominator['width']/2
            if not (1 <= gap <= numerator['height'] and abs(nc-dc) <= 2):
                continue
            width = max(numerator['width'], denominator['width'])
            left = max(0, math.floor((min(numerator['left'], denominator['left'])-bbox[0])*2))
            right = min(pixels.width, left + math.ceil(width*2))
            top = max(0, math.ceil((numerator['top']+numerator['height']-bbox[1])*2))
            bottom = min(pixels.height, math.floor((denominator['top']-bbox[1])*2))
            # Require a continuous printed bar, not mere vertical token alignment.
            bar = any(all(min(pixels.getpixel((x, y))) < 180 for x in range(left, right))
                      for y in range(top, bottom)) if right > left else False
            if not bar:
                continue
            value = f"({numerator['text']})/({denominator['text']})"
            candidates.append(dict(numerator=numerator['text'], denominator=denominator['text'], text=value))
            replacement.append({**numerator, 'text': value,
                'top': (numerator['top']+denominator['top'])/2, 'width': width})
            used.update((i, j))
            break
    return [s for i, s in enumerate(spans) if i not in used] + replacement, candidates


def extract_pdf_region(pdf_path, page_number, bbox, output_dir):
    """Crop an explicitly selected region in PDF points (top-left origin).

    No automatic question boundary detection: the caller must exclude solutions.
    Native span boxes must be wholly inside the region; clipped text is flagged.
    A new output directory is required, preventing overwrite of previous evidence.
    """
    pdf_path = Path(pdf_path).resolve(strict=True)
    if type(page_number) is not int or page_number < 1:
        raise ValueError('Page must be a positive integer')
    if (len(bbox) != 4 or any(type(v) not in (int, float) or not math.isfinite(v) for v in bbox)):
        raise ValueError('Bounding box requires four finite PDF-point coordinates')
    x1, y1, x2, y2 = bbox
    if not (0 <= x1 < x2 and 0 <= y1 < y2):
        raise ValueError('Invalid region bounds')
    result = subprocess.run(['pdftohtml', '-xml', '-i', '-zoom', '1', '-stdout',
        '-f', str(page_number), '-l', str(page_number), str(pdf_path)],
        capture_output=True, check=True, timeout=60)
    page = ET.fromstring(result.stdout).find('page')
    if page is None or int(page.attrib['number']) != page_number:
        raise ValueError('Requested PDF page unavailable')
    if x2 > float(page.attrib['width']) or y2 > float(page.attrib['height']):
        raise ValueError('Region extends outside page')
    fonts = {f.attrib['id']: float(f.attrib['size']) for f in page.findall('fontspec')}
    spans, clipped = [], []
    for node in page.findall('text'):
        s = {k: float(node.attrib[k]) for k in ('left', 'top', 'width', 'height')}
        s.update(text=''.join(node.itertext()), font_size=fonts[node.attrib['font']])
        left, top, right, bottom = s['left'], s['top'], s['left']+s['width'], s['top']+s['height']
        if left < x2 and right > x1 and top < y2 and bottom > y1:
            (spans if x1 <= left and right <= x2 and y1 <= top and bottom <= y2 else clipped).append(s)
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=False)
    # Render only the selected region; no whole-page solution image enters the packet.
    px, py = math.floor(x1*2), math.floor(y1*2)
    subprocess.run(['pdftoppm', '-f', str(page_number), '-l', str(page_number),
        '-singlefile', '-r', '144', '-x', str(px), '-y', str(py),
        '-W', str(math.ceil(x2*2)-px), '-H', str(math.ceil(y2*2)-py),
        '-png', str(pdf_path), str(out/'region')], capture_output=True, check=True, timeout=60)
    image = out/'region.png'
    from PIL import Image
    with Image.open(image) as crop:
        readable_spans, fractions = recover_fractions(spans, crop, bbox)
    text, superscripts = layout_text(readable_spans)
    packet = dict(source_pdf=str(pdf_path), pdf_sha256=hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
        pdf_page=page_number, bbox_pdf_points=list(bbox), image_path=str(image),
        image_sha256=hashlib.sha256(image.read_bytes()).hexdigest(), native_spans=spans,
        clipped_span_count=len(clipped), layout_text=text, recovered_superscripts=superscripts, recovered_fractions=fractions,
        status='INPUT_REVIEW_REQUIRED', solver_ready=False,
        limitations=['Superscripts are geometry-based candidates, not verified mathematics.',
                    'Only simple stacked tokens with a visible bar are fraction candidates; radicals and diagram semantics require visual review.',
                    'Caller-selected crop boundaries must exclude worked solutions.'])
    (out/'region.json').write_text(json.dumps(packet, indent=2, ensure_ascii=False)+'\n')
    return packet
