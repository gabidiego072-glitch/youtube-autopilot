# YouTube-Autopilot

Plataforma en la nube para automatizar un canal de YouTube de **curiosidades, ciencia, situaciones hipotéticas
y experimentos mentales**, centrado en vídeos del estilo **«¿Qué pasaría si…?»**, tanto **Shorts** (9:16)
como **vídeos largos** (16:9). Prioriza herramientas gratuitas y de código abierto.

**Todo lo visual se genera por código**: cada escena es una animación 3D procedural renderizada con Blender.
No se usan fotos, imágenes de IA ni hiperrealismo.

> El canal **no** trata videojuegos ni contenido gaming. Los generadores de ideas, guiones y metadatos lo
> prohíben en sus prompts y además filtran cualquier resultado que lo mencione (`app/content/profile.py`).

> **Estado (v0.2):** el pipeline de producción funciona de principio a fin a través de la API, con proveedores
> reales que se activan al configurarlos. **No se publica nada en YouTube**: la publicación está desactivada
> por defecto y la subida aún no está implementada. Ver [docs/ROADMAP.md](docs/ROADMAP.md).

## Automatización

`scripts/autopilot.py` ejecuta el proceso completo sin intervención (tema → investigación → guion → verificación →
voz → escenas 3D → render → control de calidad → metadatos → miniatura) y se detiene a esperar tu aprobación antes
de publicar. Plan, herramientas, costes y credenciales: [docs/AUTOMATION.md](docs/AUTOMATION.md).

## Pipeline

```
ideas ─► selección ─► investigación ─► guion ─► verificación ─► voz ─► escenas 3D (plan) ─► render Blender ─► montaje ─► metadatos ─► aprobación ─► (publicación)
  ▲                                                                                                                         │
  └──────────────────────────────── estadísticas ─► análisis ─► pesos por categoría / mejores premisas ◄──────────────────┘
```

| Etapa | Qué hace | Herramienta | Coste | Estado |
| --- | --- | --- | --- | --- |
| Ideas | Premisas «¿Qué pasaría si…?» puntuadas (curiosidad, potencial visual, base científica, perennidad), sin duplicados ni gaming, ponderadas por el rendimiento pasado | Claude | API de pago por uso | ✅ |
| Investigación | Conceptos científicos de la premisa + resúmenes de Wikipedia + hechos clave con su URL | Claude + Wikipedia | Wikipedia gratis | ✅ |
| Guion | Gancho ≤ 8 palabras (~2 s), consecuencias que escalan, clímax, final sorprendente o pregunta; cada afirmación etiquetada como *establecida / estimación / especulación*; las escenas se describen con lo que el motor 3D sabe dibujar | Claude | — | ✅ |
| Verificación | Revisión científica de cada afirmación; la aprobación exige que pase | Claude | — | ✅ |
| Voz | Narración por escena en español, offline; marca la duración de cada escena | Piper (open source) | Gratis | ✅ |
| Escenas 3D | Cada escena del guion se convierte en una escena del motor (entorno, personajes, planetas, acciones, cámara), validada por el propio motor | Claude + catálogo del motor | — | ✅ |
| Render | Cada escena con la duración exacta de su voz; en la nube, repartidas en trabajos paralelos; modo `hd` (720p, 4 muestras, reescalado a 1080p) | Blender (Cycles, CPU) | Gratis | ✅ |
| Montaje | Clips al ritmo de la voz, subtítulos sincronizados, música con *ducking* | FFmpeg | Gratis | ✅ |
| Metadatos | Título-pregunta, descripción con «ciencia vs. hipótesis» y fuentes, etiquetas, comentario fijado | Claude | — | ✅ |
| Publicación | Subida reanudable, miniatura, comentario opcional; privada por defecto, pública solo con `YOUTUBE_ALLOW_PUBLIC` | YouTube Data API | Gratis (cuota) | ✅ probada con Google simulado; falta la prueba real con tus credenciales |
| Estadísticas | Sincronización diaria (vistas, tiempo visto, retención, interacción) + entrada manual para impresiones/CTR | YouTube Analytics API | Gratis | ✅ (falta probar con tu canal) |
| Tendencias | Artículos más leídos de Wikipedia y vídeos populares del nicho | Wikimedia Pageviews + YouTube Data API (clave opcional) | Gratis | ✅ |
| Aprendizaje | Compara categorías, formatos y tipos de final; reajusta el ranking de ideas | — | — | ✅ |

Detalle de cada etapa, prompts y opciones gratuitas: [docs/PIPELINE.md](docs/PIPELINE.md).

## Puesta en marcha

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # DATABASE_URL, ANTHROPIC_API_KEY, etc.
alembic upgrade head
scripts/install_voice.sh        # voz española gratuita de Piper (opcional)
uvicorn app.main:app --reload
```

API interactiva: <http://localhost:8000/docs>. Qué servicios están conectados: `GET /api/v1/system/integrations`.
Requiere FFmpeg y Blender (`scripts/install_blender.sh`, ver [docs/3D_ENGINES.md](docs/3D_ENGINES.md)).

## Producir un Short completo

Una producción (`productions/<id>/production.json`) contiene el guion y una escena 3D por cada escena del guion,
el mismo formato que genera la API. Un solo comando hace voz → render → música, efectos → montaje:

```bash
python scripts/produce_short.py productions/what_if_earth_stops/production.json --mode preview --scenes 0,1
python scripts/produce_short.py productions/what_if_earth_stops/production.json --mode draft
python scripts/produce_short.py productions/what_if_earth_stops/production.json --mode final
python scripts/validate_video.py out/what_if_earth_stops/what_if_earth_stops_final.mp4
```

| Modo | Para qué | Contenido | Resolución | Muestras |
| --- | --- | --- | --- | --- |
| `preview` | revisar escenas, objetos, luz y animación | fragmento de 5–10 s (escenas elegidas) | 360×640 | 6 |
| `draft` | revisar el vídeo entero | todas las escenas, voz, música, efectos y subtítulos | 540×960 | 8 |
| `final` | publicar | todo lo anterior a calidad final, desenfoque de movimiento | 1080×1920, 24 fps | 8 + denoise |

Los renders se pueden interrumpir y reanudar, y las escenas que no cambian no se vuelven a renderizar.
`validate_video.py` revisa el MP4 (negros, congelados, silencios, subtítulos fuera de su voz, volumen) y crea
una hoja de capturas.

Pruebas técnicas sueltas del motor 3D:

```bash
python scripts/render_3d.py examples/scenes/what_if_earth_stops.json --aspect 9:16 --quality draft --ambient
```

## Flujo por la API

```
POST /api/v1/channels                                    canal (idioma por defecto: es)
POST /api/v1/channels/{id}/ideas/generate                ideas puntuadas
POST /api/v1/ideas/{id}/select  {"format": "short"}      la idea se convierte en proyecto
POST /api/v1/projects/{id}/research                      fuentes y hechos clave
POST /api/v1/projects/{id}/scripts/generate              guion «¿Qué pasaría si…?»
POST /api/v1/projects/{id}/scripts/{sid}/fact-check      verificación científica
POST /api/v1/projects/{id}/voice/generate                narración por escena
POST /api/v1/projects/{id}/scenes/plan                   escenas 3D (una por escena del guion)
POST /api/v1/projects/{id}/scenes/render                 render con Blender (trabajo en segundo plano)
GET  /api/v1/renders/{job_id}                            estado del render
POST /api/v1/projects/{id}/assemble                      MP4 final
POST /api/v1/projects/{id}/metadata/generate             título, descripción, etiquetas, comentario fijado
POST /api/v1/projects/{id}/approve                       aprobación humana
POST /api/v1/projects/{id}/analytics                     métricas (manual por ahora)
POST /api/v1/insights/analyze                            aprendizaje
GET  /api/v1/dashboard/summary                           panel
```

## Tests

```bash
pytest                       # SQLite; usa FFmpeg, Blender y Piper reales si están instalados
ruff check . && ruff format --check .
```

Con PostgreSQL: `TEST_DATABASE_URL=... TEST_POSTGRES_URL=... pytest` (se borran esas bases).
Los tests nunca llaman a Claude ni a YouTube: usan dobles de prueba en `tests/`.

## Despliegue

`Dockerfile` (API + FFmpeg). `alembic upgrade head` como paso de release. En producción la app exige
PostgreSQL y `API_KEY`. CI: `.github/workflows/ci.yml` (lint + tests contra PostgreSQL 16 + Blender).

## Estructura

Ver [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
