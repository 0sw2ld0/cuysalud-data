import pytest
from pricing_basis import drug_basis, institutional_basis

@pytest.mark.parametrize('form,presentation,count,unit', [
 ('TABLETA','CAJA ENVASE BLISTER TABLETAS','100','por tableta'),
 ('TABLETA RECUBIERTA','CAJA ENVASE BLISTER TABLETAS RECUBIERTAS','30','por tableta'),
 ('CÁPSULA BLANDA','CAJA ENVASE BLISTER CAPSULAS BLANDAS','50','por cápsula'),
 ('COMPRIMIDO RECUBIERTO','CAJA ENVASE BLISTER COMPRIMIDOS RECUBIERTOS','20','por comprimido'),
 ('SOLUCIÓN ORAL','FRASCO X 15 ML','1','por frasco de 15 mL'),
 ('SUSPENSIÓN ORAL','CAJA FRASCO X 60 ML + ACCESORIOS','1','por frasco de 60 mL'),
 ('SOLUCIÓN INYECTABLE','CAJA AMPOLLAS X 2 ML','10','por ampolla de 2 mL'),
 ('POLVO PARA SOLUCIÓN INYECTABLE','CAJA VIAL','10','por vial'),
 ('CREMA','CAJA TUBO X 30 G','1','por tubo de 30 g'),
 ('POLVO PARA SOLUCIÓN ORAL','CAJA SOBRE X 1 G','30','por sobre de 1 g'),
 ('SOLUCIÓN PARA PERFUSIÓN','CAJA BOLSA X 100 ML','10','por bolsa de 100 mL'),
 ('SOLUCIÓN INYECTABLE','CAJA JERINGA PRELLENADAS X 1 ML','2','por jeringa precargada de 1 mL'),
])
def test_explicit_units(form,presentation,count,unit):
 d=dict(form=form,presentation=presentation,fractions=count)
 result=drug_basis(d)
 assert result['status']=='resolved' and result['unitLabel']==unit
 assert result['inputForm']==form and result['inputFractions']==count
 assert 'precio' not in result['presentationLabel'].lower()

@pytest.mark.parametrize('form,presentation,count', [
 ('TABLETA','CAJA FRASCO X 30 TABLETAS','1'),
 ('TABLETA','CAJA SOBRE X 8 TABLETAS','4'),
 ('TABLETA','CAJA DISPENSADORA X 10 CAJAS ENVASE BLISTER X 10 TABLETAS','100'),
 ('CÁPSULA','CAJA ENVASE BLISTER CAPSULAS (14 CAPSULAS DE 10 MG Y 14 CAPSULAS DE 20 MG)','28'),
 ('SOLUCIÓN INYECTABLE','CAJA VIAL + AMPOLLAS X 2 ML','1'),
 ('SOLUCIÓN INYECTABLE','CAJA VIAL X 10 ML / 20 ML','1'),
 ('SOLUCIÓN ORAL','FRASCO X 15 ML','2'),
 ('TABLETA','CAJA ENVASE BLISTER TABLETAS','0'),
 ('TABLETA','CAJA ENVASE BLISTER CAPSULAS','30'),
 ('AEROSOL PARA INHALACIÓN','CAJA ENVASE AEROSOL X 200 DOSIS','1'),
 ('JARABE','JARABE','1'),
])
def test_ambiguous_units_are_not_inferred(form,presentation,count):
 result=drug_basis(dict(form=form,presentation=presentation,fractions=count))
 assert result['status']=='unresolved' and result['unitLabel'] is None
 assert presentation in result['presentationLabel']
 assert result['reason']


def test_pdf_form_does_not_invent_container():
 row=dict(description='PARACETAMOL - 100 mg/mL - SOLUCI - 10 mL',presentation='SOLUCI')
 assert institutional_basis(row)['unitLabel'] is None
 row=dict(description='PARACETAMOL - 500 mg - TABLET -',presentation=None)
 assert institutional_basis(row)['unitLabel']=='por tableta'
 row['presentation']='INYECT'
 assert institutional_basis(row)['unitLabel'] is None


def test_pdf_explicit_unit_requires_no_multiple_pack():
    assert institutional_basis(dict(description="RESPIRADOR QUIRURGICO TIPO N-95 - - - UNIDAD - -",presentation="UNIDAD"))["unitLabel"] == "por unidad"
    assert institutional_basis(dict(description="SONDA VESICAL - 2 VIAS DESCARTABLE - UNIDAD - N° 14",presentation=None))["unitLabel"] == "por unidad"
    assert institutional_basis(dict(description="GASA - - UNIDAD - X 5 UNI",presentation="UNIDAD"))["status"] == "unresolved"


def test_pdf_pair_from_separate_presentation_column():
    row = dict(description="GUANTE QUIRURGICO ESTERIL DESCARTABLE Nº 7 -", presentation="- PAR -")
    assert institutional_basis(row)["unitLabel"] == "por par"
    row["description"] += " X 5 PARES"
    assert institutional_basis(row)["status"] == "unresolved"


def test_pdf_explicit_unit_column_without_assuming_package():
    for presentation in ("- UNIDAD -", "- UNIDAD -UNIDAD", "- UNIDAD - 25 g"):
        row = dict(description="ALGODON HIDROFILO -", presentation=presentation)
        assert institutional_basis(row)["unitLabel"] == "por unidad del artículo descrito"
    row = dict(description="GASA - X 5 UNIDADES", presentation="- UNIDAD -")
    assert institutional_basis(row)["status"] == "unresolved"
    row = dict(description="ARTICULO -", presentation="- UNIDAD - X 5 UNI")
    assert institutional_basis(row)["status"] == "unresolved"
