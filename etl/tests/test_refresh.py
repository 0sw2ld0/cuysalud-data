from copy import deepcopy
from hashlib import sha256
import io
import json
import zipfile
import httpx
import polars as pl
import pytest
import refresh as sync
from official_adapters import mtc_rows


def test_only_linked_newest_editions():
    html='<a href="/Archivos/Indicadores/TendenciaCentral/FT_202608.zip">Agosto</a><a href="/Archivos/Indicadores/TendenciaCentral/FT_202609.zip">Setiembre</a>'
    assert sync.discover(html,sync.DIGEMID,'digemid')[0]=='2026-09'
    html='<a href="/sites/default/files/RENIPRESS_30-09-2026.csv">CSV</a>'
    assert sync.discover(html,sync.RENIPRESS,'renipress')[0]=='2026-09-30'
    with pytest.raises(ValueError):
        sync.discover('<a href="https://evil.test/FT_202609.zip">x</a>',sync.DIGEMID,'digemid')
    with pytest.raises(ValueError):
        sync.discover('<html>captcha</html>',sync.RENIPRESS,'renipress')
    with pytest.raises(ValueError):
        sync.discover('<a href="/FT_202613.zip">x</a>',sync.DIGEMID,'digemid')


def test_download_denials_redirects_limits():
    for status in (302,403,418):
        client=httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(status,headers={'location':'https://evil.test/'})))
        with pytest.raises((ValueError,httpx.HTTPStatusError)):
            sync.download(client,sync.DIGEMID,10)
    client=httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=b'12345678901')))
    with pytest.raises(ValueError):sync.download(client,sync.DIGEMID,10)


def fixture_dataset():
    src={'sha256':sha256(b'zip').hexdigest(),'cutoff':'2026-09-30'}
    return {'drugs':[{'source':src}], 'clinics':[{'source':dict(src,sha256=sha256(b'csv').hexdigest())}], 'nationalPrices':[{'period':'2026-08'}]}


def transport(request):
    if str(request.url)==sync.DIGEMID:return httpx.Response(200,text='<a href="/FT_202608.zip">x</a>')
    if str(request.url)==sync.RENIPRESS:return httpx.Response(200,text='<a href="/RENIPRESS_30-09-2026.csv">x</a>')
    return httpx.Response(200,content=b'zip' if request.url.path.endswith('.zip') else b'csv')


def test_unchanged_bytes_no_new_snapshot(tmp_path):
    d=fixture_dataset();before=deepcopy(d)
    with httpx.Client(transport=httpx.MockTransport(transport)) as c:
        assert sync.refresh(d,c,tmp_path) is None
    assert d==before


def test_failure_leaves_original_untouched(tmp_path):
    d=fixture_dataset();d['drugs'][0]['source']['sha256']='0'*64;before=deepcopy(d)
    with httpx.Client(transport=httpx.MockTransport(transport)) as c:
        with pytest.raises(zipfile.BadZipFile):sync.refresh(d,c,tmp_path)
    assert d==before


def test_dynamic_period_and_preserved_presentation(monkeypatch):
    headers=['N°','Código de Producto','Nombre Comercial','Concentración','Forma Farmacéutica','Presentación','Fracciones','Clasificación','Registro Sanitario','Titular de Registro Sanitario','Fabricante','País','Grupo producto','IFA','Cantidad IFAS','Cantidad de establecimientos reportantes por producto','media','mediana','moda']
    row=['1','36917','PARACETAMOL','500 MG','TABLETA','CAJA ENVASE BLISTER TABLETAS','100','GENERICO','RS','T','F','PE','G','PARACETAMOL','1','20','0.11','0.1','0.1']
    frame=pl.DataFrame([['title']+[None]*18,['Periodo septiembre 2026']+[None]*18,headers,row],orient='row')
    monkeypatch.setattr(pl,'read_excel',lambda *a,**kw:frame)
    data=io.BytesIO()
    with zipfile.ZipFile(data,'w') as z:z.writestr('MTC.xlsx',b'x')
    drugs,prices,_=mtc_rows(data.getvalue(),{},period='2026-09')
    assert drugs[0]['fractions']=='100'
    assert drugs[0]['presentation']=='CAJA ENVASE BLISTER TABLETAS'
    assert prices[0]['medianSoles']=='0.1'  # never divide an already unit-normalized price by 100
    assert prices[0]['unitLabel']=='por tableta'
    with pytest.raises(ValueError):mtc_rows(data.getvalue(),{},period='2026-08')


def test_both_sources_validate_before_publication_and_no_partial_update(tmp_path,monkeypatch):
    d=fixture_dataset()
    d.update(prices=[],centers=[],institutionalPrices=[],manifest={'sources':[],'generatedAt':'2026-01-01T00:00:00Z','artifacts':{}})
    d['drugs'][0]['source']['sha256']='0'*64
    d['clinics'][0]['source']['sha256']='1'*64
    original=deepcopy(d)
    monkeypatch.setattr(sync,'mtc_rows',lambda raw,src,**kw:([dict(id='new',source=src)],[dict(drugId='new',source=src,period=kw['period'])],{}))
    def fail(*args,**kwargs):raise ValueError('schema changed')
    monkeypatch.setattr(sync,'renipress_rows',fail)
    with httpx.Client(transport=httpx.MockTransport(transport)) as c:
        with pytest.raises(ValueError):sync.refresh(d,c,tmp_path)
    assert d==original
    monkeypatch.setattr(sync,'renipress_rows',lambda raw,src,**kw:([dict(code='00000001',source=src)],{}))
    with httpx.Client(transport=httpx.MockTransport(transport)) as c:
        result,audit=sync.refresh(d,c,tmp_path)
    assert d==original
    assert result['drugs'][0]['id']=='new'
    assert len(audit['updates'])==2
    assert len(result['manifest']['artifacts'])==6
    with httpx.Client(transport=httpx.MockTransport(transport)) as c:
        assert sync.refresh(result,c,tmp_path) is None


def test_regression_rejected(tmp_path):
    d=fixture_dataset();d['nationalPrices'][0]['period']='2026-09'
    with httpx.Client(transport=httpx.MockTransport(transport)) as c:
        with pytest.raises(ValueError,match='retrocede'):sync.refresh(d,c,tmp_path)
