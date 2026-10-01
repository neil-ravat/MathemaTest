"""Preserve native math layout and visual regions without inventing transcription."""
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

from src.verification.formula_dimensions import check_region_dimensions
from src.ingestion.source_quality import quantity_symbol_mentions


def layout_text(spans):
    """Recover only adjacent, small raised signed integer runs; preserve raw spans separately.

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
            if (previous and re.fullmatch(r'[+−–-]?[0-9]+', text.strip())
                    and re.search(r'[A-Za-z0-9)]$', previous['text'].rstrip())
                    and span['font_size'] <= previous['font_size'] * .75
                    and span['top'] + span['height'] < previous['top'] + previous['height'] - 1
                    and -2 <= span['left'] - (previous['left'] + previous['width']) <= 3):
                exponent = text.strip().replace('−', '-').replace('–', '-')
                pieces.append('^(' + exponent + ')' + text[len(text.rstrip()):])
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


def read_pdf_page(pdf_path, page_number):
    """Read original span geometry once without inferring mathematical meaning."""
    result = subprocess.run(['pdftohtml', '-xml', '-i', '-zoom', '1', '-stdout',
        '-f', str(page_number), '-l', str(page_number), str(pdf_path)],
        capture_output=True, check=True, timeout=60)
    page = ET.fromstring(result.stdout).find('page')
    if page is None or int(page.attrib['number']) != page_number:
        raise ValueError('Requested PDF page unavailable')
    fonts = {f.attrib['id']: float(f.attrib['size']) for f in page.findall('fontspec')}
    spans = []
    for node in page.findall('text'):
        span = {k: float(node.attrib[k]) for k in ('left', 'top', 'width', 'height')}
        span.update(text=''.join(node.itertext()), font_size=fonts[node.attrib['font']])
        spans.append(span)
    return page, spans


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
    page, native_spans = read_pdf_page(pdf_path, page_number)
    if x2 > float(page.attrib['width']) or y2 > float(page.attrib['height']):
        raise ValueError('Region extends outside page')
    spans, clipped = [], []
    for s in native_spans:
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


def math_region_boxes(spans, page_width, page_height):
    """Find compact equation neighborhoods; no guessed formula or manual crop.

    ponytail: native single-letter algebra only. Long expressions, radicals,
    multi-column layouts and equations without equals need a richer detector.
    """
    def math_span(span):
        text = span['text'].strip()
        return (bool(text) and len(text) <= 80
                and not re.search(r'[A-Za-z]{4}', text)
                and re.fullmatch(r'[A-Za-z0-9µμΩΩπθρσΔ=+−–*/().^_ ×÷-]+', text) is not None)
    regions = []
    for anchor in spans:
        inline = re.search(r'\b\d+\s+[A-Za-z]\s*=\s*\d+\s+[A-Za-z]\s*/\s*\d+\s+[A-Za-z]\b', anchor['text'])
        if '=' not in anchor['text'] or not (math_span(anchor) or inline):
            continue
        ax, ay = anchor['left'], anchor['top']
        ar, ab = ax + anchor['width'], ay + anchor['height']
        nearby = [s for s in spans if (math_span(s) or s is anchor)
                  and s['left'] <= ar + 28 and s['left'] + s['width'] >= ax - 28
                  and s['top'] <= ab + 9 and s['top'] + s['height'] >= ay - 9]
        box = (max(0, min(s['left'] for s in nearby)-1),
               max(0, min(s['top'] for s in nearby)-1),
               min(page_width, max(s['left']+s['width'] for s in nearby)+1),
               min(page_height, max(s['top']+s['height'] for s in nearby)+1))
        # Include full spans intersecting the row instead of clipping off units.
        # Do not expand vertically into neighboring prose or another column's row.
        while True:
            row = [s for s in spans if box[1] <= s['top'] and s['top']+s['height'] <= box[3]
                   and s['left'] <= box[2]+3 and s['left']+s['width'] >= box[0]-3]
            expanded = (min([box[0]]+[s['left'] for s in row]), box[1],
                        max([box[2]]+[s['left']+s['width'] for s in row]), box[3])
            if expanded == box:
                break
            box = expanded
        signature = {(s['left'],s['top'],s['text']) for s in spans
                     if box[0] <= s['left'] and s['left']+s['width'] <= box[2]
                     and box[1] <= s['top'] and s['top']+s['height'] <= box[3]}
        if not any(signature == {(s['left'],s['top'],s['text']) for s in spans
                    if b[0] <= s['left'] and s['left']+s['width'] <= b[2]
                    and b[1] <= s['top'] and s['top']+s['height'] <= b[3]} for b in regions):
            regions.append(box)
    return regions


def extract_pdf_math_candidates(pdf_path, page_number, output_dir):
    """Automatically propose equation crops; never certify them or rewrite offsets.

    Scan the whole requested page, including examples; source role and page boxes
    are explicit so callers must apply their target boundary before any retrieval.
    """
    pdf_path = Path(pdf_path).resolve(strict=True)
    if type(page_number) is not int or page_number < 1:
        raise ValueError('Page must be a positive integer')
    page, spans = read_pdf_page(pdf_path, page_number)
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=False)
    boxes = math_region_boxes(spans, float(page.attrib['width']), float(page.attrib['height']))
    # Conservative page-local separation; unmarked continuations remain unknown.
    example_tops = [s['top'] for s in spans
                    if re.match(r'\s*(?:Example\s+\d|Solution\b)', s['text'], re.I)]
    packets = []
    for index, bbox in enumerate(boxes):
        packet = extract_pdf_region(pdf_path, page_number, bbox, out/f'candidate_{index:03d}')
        packet['source_role'] = ('example_or_later' if example_tops and bbox[3] >= min(example_tops)
                                 else 'unclassified_source')
        packet['symbols'] = sorted(set(re.findall(r'(?<![A-Za-z])[A-Za-z](?![A-Za-z])', packet['layout_text'])))
        preceding = [s for s in spans if bbox[1]-45 <= s['top']
                     and s['top']+s['height'] <= bbox[1]
                     and s['left'] < bbox[2]+250 and s['left']+s['width'] > bbox[0]-30]
        # Complete adjacent spans on selected rows, retaining split parenthesized
        # labels without widening the window into a separate column.
        while True:
            adjacent = [s for s in spans if s not in preceding and any(
                abs(s['top']-p['top']) <= 3 and
                -3 <= s['left']-(p['left']+p['width']) <= 3
                for p in preceding) and s['top']+s['height'] <= bbox[1]]
            if not adjacent:
                break
            preceding.extend(adjacent)
        nearby_text, _ = layout_text(preceding)
        packet['preceding_native_spans'] = preceding
        packet['preceding_layout_text'] = nearby_text
        mentions = quantity_symbol_mentions([dict(content=nearby_text, evidence_id=0,
            start_offset=0, end_offset=len(nearby_text))])
        packet['symbol_mentions'] = [dict(symbol=m['symbol'], label=m['name'],
            source_phrase=m['source_phrase'], context_start=m['start_offset'],
            context_end=m['end_offset']) for m in mentions if m['symbol'] in packet['symbols']]
        packet['symbol_meanings_verified'] = False
        packet['dimension_check'] = check_region_dimensions(packet)
        if packet['clipped_span_count']:
            packet['rejection_reason'] = 'Crop intersects incomplete native text spans'
        (Path(packet['image_path']).with_suffix('.json')).write_text(
            json.dumps(packet,indent=2,ensure_ascii=False)+'\n')
        packets.append(packet)
    result = dict(source_pdf=str(pdf_path), pdf_page=page_number,
        pdf_sha256=hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
        detection='compact_native_equality_regions_v1', candidates=packets,
        status='INPUT_REVIEW_REQUIRED', solver_ready=False,
        limitations=['Symbols are lexical candidates, not quantities or verified meanings.',
                    'Page-local example markers do not establish target-blind source scope.',
                    'Unsupported formulas and implicit visual dependencies may be missed.'])
    (out/'candidates.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    return result
