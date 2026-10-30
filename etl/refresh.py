"""Discover only explicitly linked public editions; publish neither denials nor partial runs."""
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit, unquote
import httpx
from bs4 import BeautifulSoup
from official_adapters import mtc_rows, renipress_rows

DIGEMID = 'https://www.digemid.minsa.gob.pe/webDigemid/reportes/2026/indicador-de-precios-de-productos-farmaceuticos/'
RENIPRESS = 'https://www.datosabiertos.gob.pe/dataset/registro-nacional-de-entidades-prestadoras-de-servicios-de-salud-renipress'
COLLECTIONS = ('drugs','prices','clinics','centers','nationalPrices','institutionalPrices')
ROOT = Path(__file__).resolve().parents[1]

def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))+'\n').encode()

def allowed(url):
    p = urlsplit(url)
    if p.scheme != 'https' or p.hostname not in {'www.digemid.minsa.gob.pe','www.datosabiertos.gob.pe'} or p.username or p.password or p.port not in (None,443):
        raise ValueError('URL fuera de los orígenes oficiales permitidos')
    return url

def download(client, url, limit):
    allowed(url)
    with client.stream('GET', url) as response:
        response.raise_for_status()  # no redirects, cookies, CAPTCHA or credential fallback
        if response.status_code != 200:
            raise ValueError('Respuesta distinta de 200')
        result = bytearray()
        for part in response.iter_bytes():
            result.extend(part)
            if len(result) > limit:
                raise ValueError('Descarga demasiado grande')
    return bytes(result)

def discover(html, base, kind):
    editions = []
    for a in BeautifulSoup(html, 'html.parser').select('a[href]'):
        url = urljoin(base, a['href'])
        path = unquote(urlsplit(url).path)
        pattern = r'/FT_(\d{4})(\d{2})(?:-\d+)?\.zip$' if kind == 'digemid' else r'/RENIPRESS_(\d{2})-(\d{2})-(\d{4})\.csv$'
        m = re.search(pattern, path, re.I)
        if not m:
            continue
        allowed(url)
        if kind == 'digemid':
            year, month = map(int, m.groups())
            cutoff = date(year, month, 1)
            edition = cutoff.strftime('%Y-%m')
        else:
            day, month, year = map(int, m.groups())
            cutoff = date(year, month, day)
            edition = cutoff.isoformat()
        if cutoff > datetime.now(timezone.utc).date():
            raise ValueError('Edición futura')
        editions.append((edition, url))
    if not editions:
        raise ValueError('No se encontraron ediciones enlazadas; revisar el portal')
    latest = max(e for e, _ in editions)
    urls = {u for e, u in editions if e == latest}
    if len(urls) != 1:
        raise ValueError('Edición ambigua')
    return latest, urls.pop()

def source(kind, edition, url, raw, timestamp):
    return dict(id=f'{kind}-{edition}', name=f'{"DIGEMID · MTC" if kind == "digemid" else "SUSALUD · RENIPRESS"} {edition}', url=url,
                cutoff=None if kind == 'digemid' else edition, retrievedAt=timestamp,
                sha256=sha256(raw).hexdigest(), license='No verificada' if kind == 'digemid' else 'Open Data Commons Attribution License (ODC-By), declarada por el dataset SUSALUD', coverage='sample')

def refresh(dataset, client, evidence):
    # All candidates are fetched and validated before mutating the copy or disk.
    candidates = []
    timestamp = datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
    for kind, landing, collection in [('digemid',DIGEMID,'drugs'),('renipress',RENIPRESS,'clinics')]:
        page = download(client, landing, 4_000_000)
        edition, url = discover(page, landing, kind)
        raw = download(client, url, 40_000_000)
        src = source(kind, edition, url, raw, timestamp)
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / f'{kind}-{edition}.raw').write_bytes(raw)
        (evidence / f'{kind}-landing.html').write_bytes(page)
        old = dataset[collection][0]['source']
        old_edition = dataset['nationalPrices'][0]['period'] if kind == 'digemid' else old['cutoff']
        if not old_edition or edition < old_edition:
            raise ValueError(f'{kind}: la edición retrocede')
        if old['sha256'] == src['sha256']:
            candidates.append(None)
            continue
        if kind == 'digemid':
            rows, prices, audit = mtc_rows(raw, src, limit=100_000, period=edition)
        else:
            rows, audit = renipress_rows(raw, src, limit=100_000)
            prices = None
        if not rows or len(rows) < len(dataset[collection]) * .5:
            raise ValueError(f'{kind}: reducción anómala; requiere revisión')
        candidates.append((collection, rows, prices, audit, src))
    if not any(candidates):
        return None
    result = json.loads(json.dumps(dataset))
    audits = []
    for candidate in candidates:
        if candidate is None:
            continue
        collection, rows, prices, audit, src = candidate
        result[collection] = rows
        if prices is not None:
            result['nationalPrices'] = prices
            # Never retain quotations linked to an obsolete product catalogue.
            ids = {r['id'] for r in rows}
            result['prices'] = [p for p in result['prices'] if p['drugId'] in ids]
        audits.append(dict(source=src, audit=audit))
    # Invalidate old indexes: only these six full collections are published in this feed.
    result['manifest']['artifacts'] = {f'{k}.json': dict(sha256=sha256(encode(result[k])).hexdigest(), bytes=len(encode(result[k]))) for k in COLLECTIONS}
    used = {json.dumps(r['source'], sort_keys=True):r['source'] for k in COLLECTIONS for r in result[k]}
    for d in result['drugs']:
        if d.get('essentialSource'):
            used[json.dumps(d['essentialSource'],sort_keys=True)] = d['essentialSource']
    result['manifest']['sources'] = list(used.values())
    result['manifest']['generatedAt'] = timestamp
    return result, dict(checkedAt=timestamp, updates=audits)

def main():
    dataset = json.loads((ROOT/'data/dataset.json').read_bytes())
    with httpx.Client(timeout=60, follow_redirects=False) as client:
        updated = refresh(dataset, client, ROOT/'evidence')
    if updated is None:
        print('Sin nuevas ediciones o correcciones oficiales: snapshot sin cambios.')
        return
    result, audit = updated
    raw = encode(result)
    # Files are staged only after both sources validate; workflow commits only after build validation.
    (ROOT/'data/dataset.json').write_bytes(raw)
    (ROOT/'data/snapshot.json').write_bytes(encode(dict(version=sha256(raw).hexdigest(),bytes=len(raw),generatedAt=result['manifest']['generatedAt'])))
    (ROOT/'data/acquisition.json').write_bytes(encode(audit))
    print(json.dumps(audit,ensure_ascii=False))

if __name__ == '__main__':
    main()
