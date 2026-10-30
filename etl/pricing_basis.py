"""Versioned, conservative interpretation of explicit packaging, never price conversion."""
import re
import unicodedata

VERSION = 1

def norm(value):
    return ' '.join(unicodedata.normalize('NFKD', value or '').encode('ascii','ignore').decode().lower().split())

SOLIDS = [
    ('tableta','tabletas'),('comprimido','comprimidos'),('capsula','cápsulas'),
    ('ovulo','óvulos'),('supositorio','supositorios'),('parche','parches'),
    ('gragea','grageas'),('pastilla','pastillas'),('implante','implantes'),
]
SINGULAR = {'capsula':'cápsula','ovulo':'óvulo'}
CONTAINERS = [
    (r'frasco(?:s)?(?: gotero)?','frasco','frascos'),
    (r'ampolla(?:s)?(?: bebibles)?','ampolla','ampollas'),
    (r'vial(?:es)?','vial','viales'),
    (r'jeringa(?:s)? (?:prellenada(?:s)?|precargada(?:s)?)','jeringa precargada','jeringas precargadas'),
    (r'tubo','tubo','tubos'),(r'bolsa','bolsa','bolsas'),(r'sobre(?:s)?','sobre','sobres'),
    (r'cartucho(?: prellenado)?','cartucho','cartuchos'),
    (r'envase aerosol','envase aerosol','envases aerosol'),
]

def basis(status, unit, presentation, rule, reason):
    return dict(version=VERSION,status=status,unitLabel=unit,presentationLabel=presentation,rule=rule,reason=reason)

def _drug_basis(drug):
    raw = drug.get('presentation')
    text, form = norm(raw), norm(drug.get('form'))
    count = str(drug.get('fractions') or '')
    declared = 'Presentación: ' + (raw or 'no informada')
    declared += ' · fracciones declaradas: ' + (count or 'no informadas')
    def unknown(reason):
        return basis('unresolved',None,declared,'unresolved',reason)
    if not text or not re.fullmatch(r'[1-9][0-9]*',count):
        return unknown('La presentación o las fracciones no permiten identificar la unidad del precio.')
    # Kits, solventes, different strengths and nested boxes need individual source confirmation.
    stripped = re.sub(r'\+\s*(?:accesorios|vaso dosificador|cuchara dosificadora|dosificador|gotero)\b','',text)
    if '+' in stripped or re.search(r'solvente|disolvente|dispensadora|\bcajas\b|\bcon caja\b|\d+\s*mg.*\d+\s*mg',text):
        return unknown('Presentación compuesta o múltiple: confirmar en la fuente qué unidad se valoró.')
    for stem, plural in SOLIDS:
        if re.match(rf'^{stem}s?\b',form) and re.search(rf'\b{stem}s?\b',text):
            if re.search(r'\b(?:frasco|frascos|sobre|sobres|tubo)\b|\d', text):
                return unknown('Sólidos dentro de otro envase o agrupación: las fracciones no bastan para confirmar si se valoró cada sólido o el recipiente.')
            singular = SINGULAR.get(stem,stem)
            # Only simple blister/folio boxes can be safely shortened to a box count.
            if re.fullmatch(r'caja (?:envase )?(?:blister|folio|tira|tiras) .+',text) and not re.search(r'\d',text):
                declared = f'Presentación: caja de {count} {singular if count=="1" else plural}'
            return basis('resolved','por '+singular,declared,'solid-'+stem,'Unidad sólida explícita en la presentación y concordante con la forma; MTC ya está expresado por unidad.')
    # A bare container must not be mistaken for a bottle holding tablets/capsules, or an inhaler dose.
    if any(re.search(rf'\b{stem}s?\b',text) for stem,_ in SOLIDS) or re.search(r'dosis|monodosis|unitoma|sistema|aplicador|inyector|pluma|inhalador',text):
        return unknown('No se puede distinguir con certeza el recipiente, el dispositivo y su contenido como unidad de precio.')
    found=[(pattern,singular,plural) for pattern,singular,plural in CONTAINERS if re.search(rf'\b(?:{pattern})\b',text)]
    if len(found)!=1:
        return unknown('El tipo de unidad comercial no está precisado de forma inequívoca.')
    pattern,singular,plural=found[0]
    # Restrict to explicit simple grammar; no unreviewed free-form packaging inference.
    grammar=rf'(?:caja (?:envase |bandeja )?)?(?:{pattern})(?: x ([0-9]+(?:[.,][0-9]+)?) (ml|g|mg))?(?: \+ (?:accesorios|vaso dosificador|cuchara dosificadora|dosificador|gotero))?'
    match=re.fullmatch(grammar,text)
    if not match:
        return unknown('Descripción de envase compleja: confirmar la unidad en la fuente.')
    volume, measure=match.group(1),match.group(2)
    size = f' de {volume} {"mL" if measure=="ml" else measure}' if volume else ''
    unit=singular+size
    if text.startswith('caja '):
        declared=f'Presentación: caja con {count} {singular if count=="1" else plural}{size}'
    elif count=='1':
        declared='Presentación: '+unit
    else:
        return unknown('Envase sin caja y fracciones múltiples: verificar la unidad comercial.')
    if '+' in text:
        declared+=' y accesorios declarados'
    return basis('resolved','por '+unit,declared,'container-'+singular,'Recipiente explícito y fracciones declaradas; referencia por recipiente, nunca por mL, gramo o dosis.')

def _institutional_basis(row):
    # All six pinned PDFs explicitly head this column Precio Unitario/P/UNITARIO.
    # TABLET and OVULO/PAR can identify a concrete unit; SOLUCI or INYECT alone cannot.
    description=norm(row['description'])
    presentation=norm(row.get('presentation'))
    declared='Presentación publicada: '+(row.get('presentation') or row['description'])
    # Some PDFs put the dispensing unit in a separate column after a wrapped description.
    if (presentation == "- par -" and description.startswith("guante quirurgico esteril descartable")
        and not re.search(r"\bx\s*\d+\s*(?:par|pares|uni|unidad)", description)):
        return basis('resolved','por par',declared,'institutional-pair',
                     'La columna de presentación de la fila oficial indica PAR para guantes; el precio está expresado por unidad publicada.')
    # The PDF explicitly names UNIDAD for these individual products. Do not infer
    # unit count where the row says e.g. "X 5 UNI" (a package of five).
    if (re.search(r" - unidad -", description) and presentation in ("", "unidad")
        and not re.search(r"\bx\s*\d+\s*(?:uni|unidad)", description)):
        return basis('resolved','por unidad',declared,'institutional-unit',
                     'La lista oficial indica precio unitario y la fila especifica UNIDAD; no identifica una caja ni una agrupación.')
    for token,unit in [('tablet','tableta'),('ovulo','óvulo'),('par','par')]:
        if re.search(rf'(?:^| - ){token}(?: -|$)',description) and presentation in ('',token,'- par -'):
            return basis('resolved','por '+unit,declared,'institutional-'+token,'Columna de precio unitario y unidad explícita de la fila original; sin enlace supuesto al catálogo DIGEMID.')
    return basis('unresolved',None,declared,'institutional-unresolved','El PDF publica un precio unitario, pero esta fila no precisa de forma inequívoca si la unidad es frasco, ampolla, tubo u otro envase. Consultar la fila original.')


def drug_basis(drug):
    value = _drug_basis(drug)
    value.update(inputForm=drug.get('form'), inputPresentation=drug.get('presentation'), inputFractions=drug.get('fractions'))
    return value

def institutional_basis(row):
    value = _institutional_basis(row)
    value.update(inputDescription=row.get('description'),inputPresentation=row.get('presentation'))
    return value
