"""Audit every published record; reject stale interpretations and unlabelled prices."""
from collections import Counter
from decimal import Decimal
import json
from pathlib import Path
from pricing_basis import drug_basis, institutional_basis

ROOT=Path(__file__).resolve().parents[1]

def audit(dataset):
    rows=[]
    prices={p['drugId']:p for p in dataset['nationalPrices']}
    assert len(prices)==len(dataset['nationalPrices'])==len(dataset['drugs'])
    for kind,resolve in [('drugs',drug_basis),('institutionalPrices',institutional_basis)]:
        for record in dataset[kind]:
            expected=resolve(record)
            assert record['pricingBasis']==expected, f'Interpretación obsoleta: {record["id"]}'
            if kind=='drugs':
                p=prices[record['id']]
                assert p['unitLabel']==(expected['unitLabel'] or 'unidad de venta no precisada')
                assert Decimal(p['medianSoles']).is_finite() and Decimal(p['medianSoles'])>=0
            assert (expected['status']=='resolved') == (expected['unitLabel'] is not None)
            rows.append(dict(kind=kind,id=record['id'],name=record.get('name',record.get('description')),form=record.get('form'),presentation=record.get('presentation'),fractions=record.get('fractions'),status=expected['status'],unitLabel=expected['unitLabel'],rule=expected['rule'],reason=expected['reason']))
    return dict(generatedAt=dataset['manifest']['generatedAt'],counts={kind:dict(Counter(r['status'] for r in rows if r['kind']==kind)) for kind in ['drugs','institutionalPrices']},rules=dict(Counter(r['rule'] for r in rows)),records=rows)

if __name__=='__main__':
    result=audit(json.loads((ROOT/'data/dataset.json').read_text()))
    (ROOT/'evidence').mkdir(exist_ok=True)
    (ROOT/'evidence/pricing-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result['counts'],ensure_ascii=False))
