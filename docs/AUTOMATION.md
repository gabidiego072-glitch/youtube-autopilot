# Automatización completa: plan técnico

Objetivo: que el sistema produzca y publique vídeos «¿Qué pasaría si…?» por sí solo, en la nube, con coste
cercano a 0 €, sin publicar nada sin autorización previa.

## 1. Estado actual (análisis)

| Pieza | Estado | Dónde |
| --- | --- | --- |
| API, base de datos PostgreSQL/Supabase, migraciones | ✅ funciona, con tests | `app/`, `alembic/` |
| Ideas puntuadas (curiosidad, **impacto humano**, potencial visual, base científica, perennidad), sin duplicados, ponderadas por el rendimiento pasado | ✅ | `app/services/ideas/` |
| Investigación con Wikipedia y verificación científica obligatoria | ✅ (Wikipedia limita las peticiones desde algunas IP) | `app/services/research/`, `factcheck/` |
| Guion con gancho, escalada, final, afirmaciones etiquetadas y **regla de impacto humano** (≥70 % del tiempo a escala humana) | ✅ | `app/services/scripts/`, `app/content/profile.py` |
| Escenas 3D por código: ciudad, costa, interior de vivienda, prado, espacio; física (inercia, cristales, mar), personas con acciones | ✅ base; vocabulario ampliable | `render_engines/` |
| Voz Piper (español de España), montaje FFmpeg con transiciones, música y efectos por código, subtítulos, −14 LUFS | ✅ | `app/services/voice/`, `editing/`, `audio/` |
| Control de calidad automático del vídeo y miniaturas desde el propio render | ✅ | `app/services/qa/`, `thumbnails/` |
| **Orquestador autónomo** (12 pasos, reanudable, registro de tokens, aprobación humana) | ✅ probado con servicios simulados | `app/services/autopilot/`, `scripts/autopilot.py` |
| Ejecución diaria en la nube | ⚙️ flujo preparado y desactivado (necesita secretos y decidir el cómputo) | `.github/workflows/autopilot.yml` |
| Subida a YouTube (OAuth + subida reanudable + miniatura) | ⏳ fase 5: necesita tus credenciales para probarla de verdad | `app/services/youtube/` |
| Recogida de estadísticas de YouTube Analytics | ⏳ fase 6 (credenciales) | `app/services/youtube/analytics_api.py` |
| Investigación de tendencias y competencia | ⏳ fase 6 (clave de la API de YouTube) | — |

## 2. Arquitectura

```
GitHub Actions (cron diario) ──► scripts/autopilot.py run
        │                                 │
        │                                 ├─ PostgreSQL (Supabase): canal, ideas, proyectos, ejecuciones, métricas
        │                                 ├─ Claude API: ideas, investigación, guion, verificación, storyboard, metadatos
        │                                 ├─ Wikipedia: fuentes
        │                                 ├─ Piper: voz · Blender: escenas 3D · FFmpeg: montaje, QA, miniaturas
        │                                 └─ YouTube Data API: subida (tras aprobación)
        │
        └─ artefactos de la ejecución: MP4, miniaturas, hoja de capturas e informe (14 días) → tú revisas
           y apruebas con «Run workflow → approve <run_id>» (o por la API)
```

Cada ejecución (`PipelineRun`) recorre los pasos `topic → research → script → fact_check → voice → storyboard →
render → qa → metadata → thumbnail → approval → publish`. Cada paso guarda estado, intentos, errores y tokens;
si algo falla (cuota, red, guion rechazado), `resume` continúa desde ese paso sin repetir los anteriores.
**Nunca se publica sin aprobación**, salvo que la ejecución se lance con `--auto-publish` *y* la variable
`YOUTUBE_PUBLISHING_ENABLED=true` esté activada.

## 3. Herramientas y costes

| Necesidad | Herramienta | Coste | Límites a tener en cuenta |
| --- | --- | --- | --- |
| Cómputo programado | GitHub Actions | **0 €** | Repo **público**: minutos ilimitados en ejecutores de 4 vCPU/16 GB. Repo **privado** (el tuyo ahora): 2.000 min/mes en ejecutores de 2 vCPU; un Short a calidad final no cabe (≈7 h > límite de 6 h por trabajo). |
| Base de datos | Supabase Free | **0 €** | 500 MB; el proyecto se pausa tras 7 días sin uso (la ejecución diaria lo mantiene activo). |
| IA de texto | Claude API | **único coste variable** | Sin capa gratuita. Estimación por Short: ~30 k tokens de entrada y ~35 k de salida (con razonamiento). Opus 5.5 ≈ 0,80 $/Short (~24 $/mes a 1 diario); Sonnet 5.5 ≈ 0,40 $ (~12 $/mes); Haiku 5.5 ≈ 0,02 $ (calidad menor). El coste real queda registrado en cada ejecución (`usage`). El modelo se elige con `CLAUDE_MODEL`. |
| Voz | Piper | 0 € | Revisa la licencia de cada voz antes de monetizar. |
| 3D y montaje | Blender, FFmpeg | 0 € | CPU: ~2–3 s/fotograma en draft, ~6–11 s en final (4 núcleos). |
| Fuentes | Wikipedia API | 0 € | Requiere un User-Agent con contacto; limita peticiones excesivas. |
| Publicación y estadísticas | YouTube Data API v3 + YouTube Analytics API | 0 € | 10.000 unidades/día por proyecto; una subida consume ~1.600 (comprueba el valor actual en la documentación de cuota) → unas 6 subidas/día. |

### Decisión pendiente: dónde renderizar

1. **Hacer público el repositorio** (recomendado): GitHub Actions gratis e ilimitado con 4 vCPU, y se pueden
   renderizar las escenas **en paralelo** (un trabajo por escena) para producir un Short final en ~30–45 min.
   Los secretos no son visibles aunque el código sea público.
2. Mantenerlo privado y publicar en calidad `draft` (540×960), que cabe en los 2.000 minutos.
3. Máquina virtual gratuita de Oracle Cloud (ARM): Blender no publica binarios oficiales para Linux ARM; habría
   que compilarlo o usar el paquete del sistema y probarlo antes de confiar en ella.

## 4. Credenciales: cómo conseguirlas

Todas se guardan como **secretos de GitHub** (Settings → Secrets and variables → Actions) o en `.env` en local.
Nunca en el código.

| Secreto / variable | Cómo obtenerlo |
| --- | --- |
| `ANTHROPIC_API_KEY` | console.anthropic.com → API Keys → Create key. Añade un límite de gasto mensual en Billing. |
| `DATABASE_URL` | supabase.com → New project → Project Settings → Database → Connection string (cámbialo a `postgresql+psycopg://…`). |
| `WIKIPEDIA_USER_AGENT` (variable) | Texto libre con nombre del proyecto y un contacto, p. ej. `YouTubeAutopilot/1.0 (tu-correo)`. |
| `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET` | console.cloud.google.com → nuevo proyecto → habilita *YouTube Data API v3* y *YouTube Analytics API* → Pantalla de consentimiento OAuth (externa) → Credenciales → ID de cliente OAuth (tipo «Aplicación de escritorio»). |
| `YOUTUBE_REFRESH_TOKEN` | Se obtiene una vez con un script de autorización local (fase 5) que abre el navegador y te pide permiso para tu canal. |
| `AUTOPILOT_ENABLED`, `YOUTUBE_PUBLISHING_ENABLED`, `CHANNEL_NAME`, `CLAUDE_MODEL` (variables) | Interruptores; empiezan desactivados. |

Dos avisos importantes de YouTube:

- **Auditoría de la API**: los vídeos subidos por la API desde proyectos de Google Cloud no verificados quedan
  **bloqueados como privados** hasta que el proyecto pasa la auditoría de cumplimiento de YouTube (formulario
  gratuito; tarda días o semanas). Conviene solicitarla en cuanto exista el proyecto.
- **Tokens que caducan**: si la pantalla de consentimiento está en modo «Prueba», el token de actualización
  caduca a los 7 días. Para una ejecución autónoma hay que pasarla a «En producción».

## 5. Fases

| Fase | Contenido | Estado |
| --- | --- | --- |
| 1 | Análisis del proyecto | ✅ |
| 2 | Arquitectura, herramientas y costes (este documento) | ✅ |
| 3 | Generación automática: orquestador reanudable, regla de impacto humano, entornos urbanos con física | ✅ probado con servicios simulados; falta una ejecución real con `ANTHROPIC_API_KEY` |
| 4 | Narración, montaje, audio, subtítulos, miniaturas y QA dentro del orquestador | ✅ |
| 5 | YouTube: autorización OAuth, subida reanudable, miniatura, comentario fijado, programación | ⏳ necesita credenciales de Google |
| 6 | Estadísticas (YouTube Analytics) y tendencias/competencia (YouTube Data API, Wikipedia Pageviews) → aprendizaje | ⏳ necesita credenciales |
| 7 | Prueba de principio a fin: una ejecución real hasta «esperando aprobación», revisión, y una subida de prueba en privado autorizada por ti | ⏳ |

Extras previstos para la escala diaria: render en paralelo por escenas, límite de gasto por ejecución,
notificación cuando un vídeo espera aprobación, y ampliación del vocabulario 3D (incendios, derrumbes,
vehículos en marcha, más tipos de edificios).

## 6. Uso

```bash
python scripts/autopilot.py preflight                                   # ¿falta algo?
python scripts/autopilot.py run --channel "Qué Pasaría Si" --mode draft  # produce hasta «esperando aprobación»
python scripts/autopilot.py status
python scripts/autopilot.py approve <run_id>                            # tras revisar el vídeo
python scripts/autopilot.py resume <run_id>                             # reintenta desde el paso que falló
```

API: `GET /api/v1/autopilot/preflight`, `POST /api/v1/autopilot/runs`, `GET /api/v1/autopilot/runs/{id}`,
`POST /api/v1/autopilot/runs/{id}/resume`.
