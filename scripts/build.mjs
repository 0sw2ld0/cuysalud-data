import {readFile,mkdir,writeFile,rm} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const bytes=await readFile('data/dataset.json');
const stamp=JSON.parse(await readFile('data/snapshot.json','utf8'));
const version=createHash('sha256').update(bytes).digest('hex');
if(version!==stamp.version || bytes.length!==stamp.bytes || bytes.length>80000000) throw Error('Snapshot alterado');
const d=JSON.parse(bytes);
if(d.manifest.generatedAt!==stamp.generatedAt || !Number.isFinite(Date.parse(stamp.generatedAt))) throw Error('Fecha inválida');
const declared=new Set(d.manifest.sources.map(s=>JSON.stringify(s)));
const ids=new Set();
for(const drug of d.drugs){if(ids.has(drug.id))throw Error('Producto duplicado');ids.add(drug.id);}
const clinics=new Set(d.clinics.map(c=>c.code));
if(clinics.size!==d.clinics.length || !ids.size || !clinics.size)throw Error('Catálogo inválido');
for(const kind of ['drugs','prices','clinics','centers','nationalPrices','institutionalPrices']){
 if(!Array.isArray(d[kind]))throw Error('Colección ausente');
 for(const row of d[kind]){
  if(!declared.has(JSON.stringify(row.source)))throw Error('Fuente no declarada');
  if(row.drugId && !ids.has(row.drugId))throw Error('Precio sin producto');
 }
}
const counts=Object.fromEntries(['drugs','clinics','centers','nationalPrices','institutionalPrices'].map(k=>[k,d[k].length]));
await rm('_site',{recursive:true,force:true});
await mkdir(`_site/versions/${version}`,{recursive:true});
await writeFile(`_site/versions/${version}/dataset.json`,bytes);
await writeFile('_site/current.json',JSON.stringify({version})+'\n');
await writeFile('_site/metadata.json',JSON.stringify({...stamp,counts,sources:d.manifest.sources},null,2)+'\n');
await writeFile('_site/index.html','<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Datos de CuySalud</title><h1>Datos de CuySalud</h1><p>Feed público para las apps nativas.</p><ul><li><a href="current.json">Versión actual</a></li><li><a href="metadata.json">Fuentes, cobertura y fechas</a></li><li><a href="https://github.com/0sw2ld0/cuysalud-data">Repositorio y documentación</a></li></ul><p>Información referencial con fecha de corte; no garantiza stock ni habilitación actual.</p></html>');
await writeFile('_site/.nojekyll','');
console.log(JSON.stringify({version,...counts}));
