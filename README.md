# YouTube-Autopilot

Plataforma en la nube para automatizar un canal de YouTube de **curiosidades, ciencia, situaciones hipotéticas
y experimentos mentales**, centrado en vídeos del estilo **«¿Qué pasaría si…?»**, tanto **Shorts** (9:16)
como **vídeos largos** (16:9). Prioriza herramientas gratuitas y de código abierto.

> El canal **no** trata videojuegos ni contenido gaming. Los generadores de ideas, guiones y metadatos lo
> prohíben en sus prompts y además filtran cualquier resultado que lo mencione (`app/content/profile.py`).

> **Estado (v0.2):** el pipeline de producción funciona de principio a fin a través de la API, con proveedores
> reales que se activan al configurarlos. **No se publica nada en YouTube**: la publicación está desactivada
> por defecto y la subida aún no está implementada. Ver [docs/ROADMAP.md](docs/ROADMAP.md).

## Pipeline

```
ideas ─► selección ─► investigación ─► guion ─► verificación ─► imágenes IA ─► voz ─► montaje ─► metadatos ─► aprobación ─► (publicación)
  ▲                                                                                                                         │
  └──────────────────────────────── estadísticas ─► análisis ─► pesos por categoría / mejores premisas ◄──────────────────┘
```

| Etapa | Qué hace | Herramienta | Coste | Estado |
| --- | --- | --- | --- | --- |
| Ideas | Premisas «¿Qué pasaría si…?» puntuadas (curiosidad, potencial visual, base científica, perennidad), sin duplicados ni gaming, ponderadas por el rendimiento pasado | Claude | API de pago por uso | ✅ |
| Investigación | Conceptos científicos de la premisa + resúmenes de Wikipedia + hechos clave con su URL | Claude + Wikipedia | Wikipedia gratis | ✅ |
| Guion | Gancho ≤ 8 palabras (~2 s), consecuencias que escalan, clímax, final sorprendente o pregunta; cada afirmación etiquetada como *establecida / estimación / especulación*; «biblia visual» para coherencia | Claude | — | ✅ |
| Verificación | Revisión científica de cada afirmación; la aprobación exige que pase | Claude | — | ✅ |
| Imágenes | Una imagen hiperrealista por escena, con los mismos sujetos descritos y la misma semilla | ComfyUI propio (FLUX, SDXL…) o Hugging Face | Gratis (GPU propia) o capa gratuita | ✅ al configurarlo |
| Vídeo IA | Imagen → clip con movimiento real | ComfyUI (Wan 2.x, LTX-Video…) | Gratis con GPU propia | ✅ al configurarlo; si no, movimiento de cámara con FFmpeg |
| Voz | Narración por escena en español, offline | Piper (open source) | Gratis | ✅ |
| Montaje | Planos al ritmo de la voz, subtítulos sincronizados, música con *ducking* | FFmpeg | Gratis | ✅ |
| Visualización 3D | Escenas 3D procedurales (escala, crecimiento…) sin IA ni GPU | Blender (Cycles CPU) | Gratis | ✅ |
| Metadatos | Título-pregunta, descripción con «ciencia vs. hipótesis» y fuentes, etiquetas, comentario fijado | Claude | — | ✅ |
| Publicación | Subida a YouTube | YouTube Data API | Gratis (cuota) | ⏳ Fase 5 (bloqueada por seguridad) |
| Estadísticas | Entrada manual hoy; recolector automático después | YouTube Analytics API | Gratis | ✅ manual / ⏳ automático |
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
Requiere FFmpeg. Para la visualización 3D, `scripts/install_blender.sh` (ver [docs/3D_ENGINES.md](docs/3D_ENGINES.md)).

## Flujo por la API

```
POST /api/v1/channels                                    canal (idioma por defecto: es)
POST /api/v1/channels/{id}/ideas/generate                ideas puntuadas
POST /api/v1/ideas/{id}/select  {"format": "short"}      la idea se convierte en proyecto
POST /api/v1/projects/{id}/research                      fuentes y hechos clave
POST /api/v1/projects/{id}/scripts/generate              guion «¿Qué pasaría si…?»
POST /api/v1/projects/{id}/scripts/{sid}/fact-check      verificación científica
POST /api/v1/projects/{id}/visuals/generate              imágenes (y clips) por escena
POST /api/v1/projects/{id}/voice/generate                narración por escena
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
Los tests nunca llaman a Claude, YouTube, Hugging Face ni ComfyUI: usan dobles de prueba en `tests/`.

## Despliegue

`Dockerfile` (API + FFmpeg). `alembic upgrade head` como paso de release. En producción la app exige
PostgreSQL y `API_KEY`. CI: `.github/workflows/ci.yml` (lint + tests contra PostgreSQL 16 + Blender).

## Estructura

Ver [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
