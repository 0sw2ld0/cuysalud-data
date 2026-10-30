"""Adapters for downloaded official resources; no guesses or authenticated endpoints."""

import io
import json
from pathlib import Path
import re
from decimal import Decimal, InvalidOperation
import unicodedata
import zipfile
import polars as pl
from pricing_basis import drug_basis
import hashlib
ROOT = Path(__file__).parent
CATEGORIES = {"I-1", "I-2", "I-3", "I-4", "II-1", "II-2", "II-E", "III-1", "III-2", "III-E"}

def verify_raw(path, expected):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("Hash de fuente incorrecto")
    return raw


def normalized(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def alternative_source(
    key, name, *, cutoff=None, license="No verificada", coverage="sample"
):
    attempts = json.loads((ROOT / "data/alternatives/attempts.json").read_text())
    row = next(v for v in reversed(attempts) if v["id"] == key)
    if row.get("status") != 200:
        raise ValueError("No hay descarga oficial exitosa")
    raw = verify_raw(ROOT / "data/alternatives" / row["file"], row["sha256"])
    source = {
        "id": key,
        "name": name,
        "url": row["url"],
        "cutoff": cutoff,
        "retrievedAt": row["retrievedAt"].replace("+00:00", "Z"),
        "sha256": row["sha256"],
        "license": license,
        "coverage": coverage,
    }
    return raw, source


def renipress_rows(raw, source, limit=2000):
    frame = pl.read_csv(raw, separator=";", infer_schema=False, encoding="utf8")
    required = {
        "COD_IPRESS",
        "NOMBRE",
        "CATEGORIA",
        "ESTADO",
        "NORTE",
        "ESTE",
        "UBIGEO",
        "DIRECCION",
    }
    if not required.issubset(frame.columns):
        raise ValueError("Cambió esquema RENIPRESS")
    if frame["COD_IPRESS"].n_unique() != frame.height:
        raise ValueError("Códigos RENIPRESS duplicados")
    records = []
    inactive = {
        "BAJA DEFINITIVA",
        "CIERRE TEMPORAL DE OFICIO",
        "BAJA PROVISIONAL DE OFICIO",
        "BAJA PROVISIONAL",
        "BAJA DEFINITIVA DE OFICIO",
        "CIERRE TEMPORAL DE PARTE",
        "INACTIVO",
    }
    excluded_unnamed = 0
    for row in frame.iter_rows(named=True):
        if not (row["NOMBRE"] or "").strip():
            excluded_unnamed += 1
            continue
        code = row["COD_IPRESS"]
        cat = row["CATEGORIA"]
        status = row["ESTADO"]
        if not re.fullmatch(r"\d{8}", code):
            raise ValueError("Código RENIPRESS inválido")
        if cat not in CATEGORIES and cat not in {"0", None, "Sin Categoría"}:
            raise ValueError("Categoría desconocida")
        lat = lng = None
        try:
            a, b = float(row["NORTE"]), float(row["ESTE"])
            if -19 <= a <= 0.5 and -82 <= b <= -68:
                lat, lng = a, b
        except (ValueError, TypeError):
            pass
        records.append(
            {
                "code": code,
                "name": row["NOMBRE"],
                "category": cat if cat in CATEGORIES else None,
                "status": "active"
                if status == "ACTIVO"
                else "inactive"
                if status in inactive
                else "unknown",
                "reportedStatus": status,
                "address": row["DIRECCION"] or "",
                "ubigeo": row["UBIGEO"]
                if re.fullmatch(r"\d{6}", row["UBIGEO"] or "")
                else None,
                "lat": lat,
                "lng": lng,
                "services": None,
                "sanctions": None,
                "source": source,
            }
        )
    # Explicit sample: include Lima and other regions; never silently imply country-wide search coverage.
    groups = {}
    for record in sorted(records, key=lambda r: r["code"]):
        groups.setdefault((record["ubigeo"] or "unknown")[:2], []).append(record)
    records = []
    for offset in range(max(map(len, groups.values()), default=0)):
        for region in sorted(groups):
            if offset < len(groups[region]):
                records.append(groups[region][offset])

    return records[:limit], {
        "sourceRows": frame.height,
        "excludedUnnamed": excluded_unnamed,
        "included": min(limit, len(records)),
        "unknownCategories": frame.filter(pl.col("CATEGORIA") == "0").height,
    }


def mtc_rows(raw, source, limit=2000, period="2026-08"):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = [n for n in archive.namelist() if n.endswith(".xlsx")]
        if len(names) != 1:
            raise ValueError("Archivo MTC ambiguo")
        member = archive.getinfo(names[0])
        if member.file_size > 30_000_000:
            raise ValueError("Workbook demasiado grande")
        f = pl.read_excel(
            io.BytesIO(archive.read(names[0])),
            sheet_name="MTC",
            has_header=False,
            infer_schema_length=None,
        )
    months = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    year, month = period.split("-")
    title = normalized(str(f.row(1)[0])).replace("setiembre", "septiembre")
    if f"periodo {months[int(month)-1]} {year}" not in title:
        raise ValueError("Periodo MTC inesperado")
    headers = f.row(2)
    expected = [
        "N°",
        "Código de Producto",
        "Nombre Comercial",
        "Concentración",
        "Forma Farmacéutica",
        "Presentación",
        "Fracciones",
        "Clasificación",
        "Registro Sanitario",
        "Titular de Registro Sanitario",
        "Fabricante",
        "País",
        "Grupo producto",
        "IFA",
        "Cantidad IFAS",
        "Cantidad de establecimientos reportantes por producto",
        "media",
        "mediana",
        "moda",
    ]
    if list(headers) != expected:
        raise ValueError("Cambió el encabezado DIGEMID MTC")
    frame = f.slice(3)
    frame.columns = expected
    products = []
    prices = {}
    counts = {"sourceRows": 0, "excludedMissingOrAmbiguousComposition": 0}

    def decimal_string(v):
        try:
            d = Decimal(str(v).strip())
            return format(d, "f") if d.is_finite() and d >= 0 else None
        except InvalidOperation:
            return None

    for row in frame.iter_rows(named=True):
        code = str(row["Código de Producto"] or "").strip()
        if not re.fullmatch(r"\d+", code):
            continue
        counts["sourceRows"] += 1
        strength = str(row["Concentración"] or "").strip()
        ifa = str(row["IFA"] or "").strip()
        form = str(row["Forma Farmacéutica"] or "").strip()
        if (
            row["Cantidad IFAS"] != "1"
            or "+" in ifa
            or not ifa
            or not form
            or not re.search(r"\d\s*(?:MG|MCG|G|UI|%)(?:\b|$)", strength)
        ):
            counts["excludedMissingOrAmbiguousComposition"] += 1
            continue
        classification = row["Clasificación"]
        if classification not in {"MARCA", "GENERICO"}:
            continue
        identifier = "digemid-" + code
        product = {
            "id": identifier,
            "name": row["Nombre Comercial"].strip(),
            "ingredients": [{"dci": ifa, "strength": strength}],
            "form": form,
            "presentation": str(row["Presentación"] or "").strip() or None,
            "fractions": str(row["Fracciones"] or "").strip() or None,
            "generic": classification == "GENERICO",
            "registration": str(row["Registro Sanitario"] or "").strip() or None,
            "essential": None,
            "essentialSource": None,
            "source": source,
        }
        product["pricingBasis"] = drug_basis(product)
        median = decimal_string(row["mediana"])
        mean = decimal_string(row["media"])
        mode = decimal_string(row["moda"])
        if mean is None or median is None:
            raise ValueError("Precio MTC inválido")
        products.append(product)
        prices[identifier] = {
            "drugId": identifier,
            "scope": "national-private-retail",
            "period": period,
            "unitLabel": product["pricingBasis"]["unitLabel"] or "unidad de venta no precisada",
            "meanSoles": mean,
            "medianSoles": median,
            "modeSoles": mode,
            "reportingEstablishments": int(
                row["Cantidad de establecimientos reportantes por producto"]
            ),
            "source": source,
        }
    if len({d["id"] for d in products}) != len(products):
        raise ValueError("Productos duplicados")
    products.sort(
        key=lambda d: (
            0
            if any(
                w in normalized(d["ingredients"][0]["dci"])
                for w in ["amoxicil", "atorvastat", "paracetamol"]
            )
            else 1,
            d["id"],
        )
    )
    products = products[:limit]
    counts["included"] = len(products)
    return products, [prices[d["id"]] for d in products], counts


def official_samples(drug_limit=20000, clinic_limit=50000):
    csv, clinic_source = alternative_source(
        "renipress-september.csv",
        "SUSALUD · RENIPRESS setiembre 2026",
        cutoff="2026-09-30",
        license="Open Data Commons Attribution License (ODC-By), declarada por el dataset SUSALUD",
    )
    clinics, clinic_audit = renipress_rows(csv, clinic_source, clinic_limit)
    raw, drug_source = alternative_source(
        "FT_202608.zip", "DIGEMID · MTC agosto 2026 · composición verificable"
    )
    drugs, national_prices, drug_audit = mtc_rows(raw, drug_source, drug_limit)
    return {
        "drugs": drugs,
        "clinics": clinics,
        "nationalPrices": national_prices,
        "sources": [clinic_source, drug_source],
        "audit": {"renipress": clinic_audit, "digemid": drug_audit},
    }
