# Datos de CuySalud

Feed público para los clientes nativos iOS y Android de CuySalud.

URL base: https://0sw2ld0.github.io/cuysalud-data/

`current.json` señala la versión SHA-256. El dataset se obtiene en `versions/<version>/dataset.json`. Las apps verifican integridad y conservan la última copia válida.

La versión inicial contiene 10 991 productos e indicadores nacionales DIGEMID de agosto 2026, 36 108 establecimientos RENIPRESS de septiembre 2026, 1 196 filas de precios publicados de seis FARMAMINSA y 306 centros de salud mental. Es cobertura limitada; no certifica stock, habilitación actual ni intercambiabilidad terapéutica. Los indicadores nacionales no son precios de una botica.

Cada registro incluye la fuente original, fecha de consulta, corte cuando está informado y hash del original. RENIPRESS declara ODC-By; no se atribuye esa licencia a otras fuentes. Los derechos y condiciones de las fuentes originales se mantienen; este repositorio no les impone una licencia abierta adicional. Las fechas de generación del paquete no reemplazan los cortes de las fuentes.

## Publicación

GitHub Actions valida el archivo contra `data/snapshot.json` y publica el feed en Pages al integrar cambios en main o mediante ejecución manual. Las pull requests validan sin desplegar. `node scripts/build.mjs` reproduce el paquete localmente en `_site/`.

El workflow consulta diariamente a las 14:23 UTC (09:23 en Perú; GitHub puede demorar el inicio) y mediante ejecución manual los enlaces públicos del [indicador DIGEMID](https://www.digemid.minsa.gob.pe/webDigemid/reportes/2026/indicador-de-precios-de-productos-farmaceuticos/) y del [dataset RENIPRESS](https://www.datosabiertos.gob.pe/dataset/registro-nacional-de-entidades-prestadoras-de-servicios-de-salud-renipress). Selecciona la edición más reciente enlazada, descarga ambos originales, conserva evidencia durante 30 días en Actions y compara hashes. No adivina URLs de archivos ni utiliza sesiones, credenciales o tokens CAPTCHA.

Si cambian los bytes, valida período, esquema, códigos únicos, categorías, composición y precios decimales. Conserva presentación y fracciones originales; los indicadores MTC ya son unitarios: no se dividen nuevamente entre las fracciones. Un precio por tableta no es el precio de su caja. Rechaza retrocesos de fecha y reducciones de más del 50 % del catálogo. Una falla en cualquiera de las dos fuentes impide guardar o publicar el conjunto. Es necesario revisar cambios de formato o de URL del portal si deja de ofrecer enlaces reconocibles. No se incorporan automáticamente nuevas listas FARMAMINSA ni CSMC.

Si no hay cambios, no genera otra versión ni modifica la fecha de corte. Si hay una edición válida, Actions registra la actualización en Git, valida el feed y despliega Pages en el mismo workflow; no depende de que el commit del bot dispare otro workflow. Las apps nativas comprueban `current.json` al abrir y descargan la nueva versión con verificación SHA-256 y caché local. La fecha de generación no modifica el período de los precios ni el corte del padrón.

Pruebas locales: `pip install -r etl/requirements.txt` y `PYTHONPATH=etl pytest -q etl/tests`. Adquisición: `python etl/refresh.py`; empaquetado: `node scripts/build.mjs`.

No se incluyen recetas, imágenes ni datos de pacientes. No hay API de escritura ni servidor de aplicación.

## Unidad del precio y envase

Cada producto incluye `pricingBasis` (versión 1): interpretación conservadora de la presentación y las fracciones originales, unidad concreta cuando se puede identificar, regla utilizada y motivo cuando no se puede. No se calculan precios de cajas, dosis, mL o gramos por multiplicación o división. Las presentaciones compuestas, sólidos dentro de frascos/sobres y unidades insuficientemente descritas quedan como `unresolved`; las apps muestran “unidad de venta no precisada”. Los importes originales se conservan. Cada interpretación incluye sus campos de entrada para descartar etiquetas obsoletas si la presentación cambia.

La auditoría `python etl/audit_pricing.py` revisa todos los productos y filas de FARMAMINSA antes de publicar. Su informe por registro se conserva en la evidencia de Actions. La obtención automática aplica las mismas reglas a nuevas ediciones DIGEMID. Las listas FARMAMINSA se mantienen con su corte declarado.
