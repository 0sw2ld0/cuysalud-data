# Datos de CuySalud

Feed público para los clientes nativos iOS y Android de CuySalud.

URL base: https://0sw2ld0.github.io/cuysalud-data/

`current.json` señala la versión SHA-256. El dataset se obtiene en `versions/<version>/dataset.json`. Las apps verifican integridad y conservan la última copia válida.

La versión inicial contiene 10 991 productos e indicadores nacionales DIGEMID de agosto 2026, 36 108 establecimientos RENIPRESS de septiembre 2026, 1 196 filas de precios publicados de seis FARMAMINSA y 306 centros de salud mental. Es cobertura limitada; no certifica stock, habilitación actual ni intercambiabilidad terapéutica. Los indicadores nacionales no son precios de una botica.

Cada registro incluye la fuente original, fecha de consulta, corte cuando está informado y hash del original. RENIPRESS declara ODC-By; no se atribuye esa licencia a otras fuentes. Los derechos y condiciones de las fuentes originales se mantienen; este repositorio no les impone una licencia abierta adicional. Las fechas de generación del paquete no reemplazan los cortes de las fuentes.

## Publicación

GitHub Actions valida el archivo contra `data/snapshot.json` y publica el feed en Pages al integrar cambios en main o mediante ejecución manual. Las pull requests validan sin desplegar. `node scripts/build.mjs` reproduce el paquete localmente en `_site/`.

Para actualizar, incorporar un dataset generado y revisado por el ETL de CuySalud y regenerar su descriptor SHA-256. Conservar fuentes y cortes reales. El workflow distribuye las versiones incorporadas; no descubre nuevas ediciones oficiales automáticamente.

No se incluyen recetas, imágenes ni datos de pacientes. No hay API de escritura ni servidor de aplicación.
