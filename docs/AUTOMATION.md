# Automatización completa: guía de puesta en marcha

Objetivo: que el sistema produzca y publique vídeos «¿Qué pasaría si…?» por sí solo, en la nube, con el
repositorio **privado** y el menor coste posible, sin publicar nada en público sin tu autorización.

Índice: [1. Estado](#1-estado) · [2. Dónde renderizar](#2-dónde-renderizar) · [3. Coste mensual](#3-coste-mensual)
· [4. Credenciales paso a paso](#4-credenciales-paso-a-paso) · [5. YouTube: auditoría, pruebas y autenticación
permanente](#5-youtube-auditoría-pruebas-privadas-y-autenticación-permanente) · [6. Interruptores de
seguridad](#6-interruptores-de-seguridad) · [7. Comandos](#7-comandos)

## 1. Estado

| Pieza | Estado | Dónde |
| --- | --- | --- |
| API, PostgreSQL/Supabase, migraciones | ✅ con tests (SQLite y PostgreSQL) | `app/`, `alembic/` |
| IA de texto gratis (Gemini) con Claude opcional | ✅ probada contra la API simulada; falta tu clave | `app/services/ai/` |
| Ideas puntuadas, sin duplicados, guiadas por el rendimiento real y por **tendencias** (Wikipedia gratis + búsqueda de YouTube opcional) | ✅ (tendencias probadas en vivo con Wikipedia) | `app/services/ideas/`, `trends/` |
| Investigación (Wikipedia) y verificación científica obligatoria | ✅ | `research/`, `factcheck/` |
| Guion con regla de **impacto humano** | ✅ | `scripts/`, `app/content/profile.py` |
| Escenas 3D por código (Blender): ciudad, costa, vivienda, prado, espacio, con física | ✅ | `render_engines/` |
| Voz Piper, montaje FFmpeg, música y efectos por código, subtítulos, −14 LUFS, QA, miniaturas | ✅ | `voice/`, `editing/`, `audio/`, `qa/`, `thumbnails/` |
| Orquestador autónomo reanudable con aprobación humana | ✅ | `app/services/autopilot/` |
| **Render en paralelo** (escenas repartidas entre varias máquinas; las ya hechas se reutilizan) | ✅ probado en local; el flujo de GitHub está sin ejecutar | `production/short.py`, `.github/workflows/autopilot.yml` |
| **Subida a YouTube**: OAuth, subida reanudable con reintentos, miniatura, comentario opcional, estado de procesado | ✅ probado contra un Google simulado; **falta una prueba real con tus credenciales** | `app/services/youtube/` |
| **YouTube Analytics** → aprendizaje | ✅ probado contra un Google simulado; falta probarlo con tu canal | `youtube/analytics_api.py`, `analytics/sync.py` |

## 2. Dónde renderizar

Velocidad medida en una escena urbana real de este proyecto (Blender 4.5, Cycles CPU, 9:16):

| Calidad | Resolución | Muestras | 2 núcleos | 4 núcleos |
| --- | --- | --- | --- | --- |
| `hd` (nuevo) | 720×1280 → reescalado a 1080×1920 | 4 | ~11 s/fotograma | ~5,8 s |
| `hd` con 8 muestras | 720×1280 | 8 | ~21 s | ~10,5 s |
| `final` | 1080×1920 | 8 | ~47 s | ~23,5 s |

El tiempo es casi todo trazado de rayos, proporcional a píxeles × muestras. Con 4 muestras el fotograma es
prácticamente igual que con 8 (el eliminador de ruido OIDN lo compensa), así que `hd` es el modo recomendado
para publicar. Un Short de ~50 s son ~1.250 fotogramas.

### Comparativa de opciones gratuitas

| Opción | CPU / RAM | Límite gratis | Privado | Blender sin pantalla | Paralelo | ¿Sirve? |
| --- | --- | --- | --- | --- | --- | --- |
| **GitHub Actions, repo privado** (lo actual) | 2 vCPU / 8 GB | 2.000 min/mes (plan Free); trabajos de máx. 6 h | ✅ | ✅ | ✅ hasta 20 trabajos a la vez | Sí, pero solo para **~7 Shorts/mes** en `hd` |
| GitHub Actions, repo público | 4 vCPU / 16 GB | **Ilimitado** | ❌ | ✅ | ✅ 20 a la vez | Todo gratis, pero expone el proyecto (ver abajo) |
| **Ejecutor propio (tu ordenador) conectado a GitHub** | La de tu PC | **Ilimitado**: GitHub no cobra los ejecutores propios | ✅ | ✅ | ✅ (varios PCs) | **La mejor opción a 0 € y privada** si tienes un PC que pueda quedarse encendido |
| Oracle Cloud Always Free (ARM Ampere) | ~2 OCPU / 12 GB (cupo de 1.500 OCPU·h/mes en 2026) | 24/7 dentro del cupo; pide tarjeta para verificar la cuenta (no cobra) | ✅ | ⚠️ Blender no publica binarios ARM oficiales; habría que usar el paquete del sistema (otra versión) o compilarlo. **No probado** | Limitado | Posible a 0 €, pero requiere trabajo de instalación y no está probado |
| CircleCI Free | 2 vCPU (medium) | 30.000 créditos ≈ 3.000 min/mes | ✅ | ✅ | ✅ | Complemento: otra plataforma más que configurar |
| GitLab.com Free | 2 vCPU | 400 min/mes | ✅ | ✅ | ✅ | Demasiado poco |
| Kaggle Notebooks | 4 CPU + GPU T4 30 h/semana | Sesiones de 9–12 h | ✅ | ✅ | ❌ | **No recomendado**: está pensado para ciencia de datos y sus condiciones de uso no contemplan un servicio de producción |

Conclusiones:

- **Con el repositorio privado y GitHub como única máquina**, 0 € solo alcanza para unos 7 Shorts al mes en
  `hd`. Sin método de pago, GitHub no cobra nunca: los trabajos se detienen al agotar los minutos.
- **Para 30 Shorts + 4 largos a 0 € y en privado, la vía realista es un ejecutor propio**: tu ordenador hace de
  máquina de render de GitHub (instrucciones en la sección 4.8). El flujo ya lo admite con la variable
  `RUNS_ON`. Un PC de sobremesa de 8 núcleos rinde unas 3–4 veces más que un ejecutor de GitHub de 2 núcleos.
- El render **en paralelo** (variable `RENDER_SHARDS`, 4 por defecto) no ahorra minutos: reparte las escenas en
  varios trabajos para que un vídeo largo no supere las 6 h por trabajo y para tener el resultado antes.

### Si algún día hicieras público el repositorio (no lo he cambiado)

Quedaría visible para cualquiera:

- todo el código, los prompts y la estrategia del canal, y el historial completo de commits;
- los **registros de las ejecuciones de Actions**: temas, guiones y errores. Los secretos aparecen como `***`;
- los **artefactos de las ejecuciones**: vídeos antes de aprobarlos, voces y miniaturas, descargables por
  cualquiera. Habría que dejar de subirlos como artefactos o cifrarlos;
- los issues y las PR.

No quedaría visible: los valores de los secretos (`ANTHROPIC_API_KEY`, `DATABASE_URL`, tokens de YouTube) ni
tu base de datos. Las ejecuciones lanzadas desde forks no reciben los secretos.

Ventaja: minutos ilimitados en máquinas el doble de rápidas (todo el plan mensual gratis). Inconveniente:
cualquiera puede copiar el sistema y ver los vídeos y guiones antes de que se publiquen.

## 3. Coste mensual

Suposiciones: 30 Shorts de ~50 s y 4 vídeos largos de ~8 min, en escenas urbanas (las más pesadas), calidad
`hd`. Son ~83.600 fotogramas al mes.

| Concepto | Repo privado, ejecutores de GitHub | Ejecutor propio (tu PC) | Repo público |
| --- | --- | --- | --- |
| Render (`hd`, 4 muestras) | ~16.500 min; 2.000 gratis → **~87 $/mes** (0,006 $/min) | **0 €** (luz del PC) | 0 € |
| Render en `final` | ~66.000 min → ~380 $/mes | 0 € (más horas de PC) | 0 € |
| Solo los 30 Shorts en `hd` | ~7.800 min → ~35 $/mes | 0 € | 0 € |
| Base de datos (Supabase Free) | 0 € | 0 € | 0 € |
| Voz, 3D, montaje, Wikipedia, YouTube API | 0 € | 0 € | 0 € |
| **IA de texto: Gemini (capa gratuita)** | **0 €** (límites diarios de peticiones) | 0 € | 0 € |
| IA de texto opcional: Claude | ~30–35 $/mes con Opus 5.5 (solo si decides pagar) | igual | igual |

Con Gemini gratis y el render en un ejecutor propio (tu PC), **el sistema completo cuesta 0 €**. Los tokens de
cada ejecución quedan registrados (`usage`) y el tiempo de render en cada informe.

## 4. Credenciales paso a paso

Regla general: **ninguna clave va en el código ni en el repositorio**. En la nube van como *secretos* de GitHub
(Settings → Secrets and variables → Actions → *New repository secret*), y en tu ordenador en un archivo `.env`
(ya ignorado por git; copia `.env.example`). Los interruptores no secretos van como *variables* de GitHub (misma
pantalla, pestaña *Variables*).

### 4.1 IA de texto (gratis): `GEMINI_API_KEY`

- **Dónde**: [aistudio.google.com](https://aistudio.google.com) → **Get API key → Create API key**. Necesita una
  cuenta de Google de una persona **mayor de edad** (si eres menor, la crea tu madre, padre o tutor).
- **Coste**: 0 €. Usa la capa gratuita de Google AI Studio; si no añades facturación, nunca cobra.
- **Límites**: peticiones por minuto y por día según el modelo (los ves en AI Studio; Google los cambia a veces).
  Un Short usa ~8–10 peticiones. Las esperas por minuto se gestionan solas; si se acaba el cupo del día, la
  ejecución se para con un mensaje claro y `resume` la continúa al día siguiente.
- **Privacidad**: en la capa gratuita Google puede usar lo enviado para mejorar sus productos. Solo se envían
  ideas, guiones y verificaciones (nada personal).
- **Dónde ponerla**: secreto `GEMINI_API_KEY` en GitHub (o en `.env`).
- **Verificar**: `python scripts/autopilot.py ai-check` lista los modelos que tu clave puede usar y hace una
  llamada mínima. Si `gemini-3.8-flash` no aparece, crea la variable `GEMINI_MODEL` con uno de la lista.

Opcional, de pago: Claude (`AI_PROVIDER=claude` + `ANTHROPIC_API_KEY` de console.anthropic.com) escribe
guiones de más calidad, pero cuesta ~0,40–0,80 $ por Short. No hace falta.

### 4.2 Base de datos (Supabase): `DATABASE_URL`, gratis

- **Dónde**: [supabase.com](https://supabase.com) → Start your project (cuenta de GitHub o correo). Plan Free.
- **Límites Free**: 500 MB de base de datos y 2 proyectos. **Se pausa tras 7 días sin actividad**; la ejecución
  diaria lo mantiene activo y, si se pausa, se reactiva desde el panel.
- **Pasos**: New project, región Europa (Frankfurt o París) y una contraseña fuerte. Después pulsa
  **Connect → Session pooler** y copia la cadena. Usa el *pooler*: la conexión directa es solo IPv6 y los
  ejecutores de GitHub no tienen IPv6.
- **Formato**: cambia `postgresql://` por `postgresql+psycopg://`:
  `postgresql+psycopg://postgres.<ref>:<contraseña>@aws-0-<región>.pooler.supabase.com:5432/postgres`.
- **Dónde ponerla**: el secreto `DATABASE_URL`.
- **Verificar**: con la variable puesta en `.env`, ejecuta `alembic upgrade head` (crea las tablas) y luego
  `python scripts/autopilot.py status`, que debe devolver `[]`.

### 4.3 Proyecto de Google Cloud (para YouTube), gratis

- **Dónde**: [console.cloud.google.com](https://console.cloud.google.com), con la **misma cuenta de Google que es
  dueña del canal** (o una que lo gestione).
- **Coste**: crear el proyecto y usar las APIs de YouTube es gratis. **No actives la facturación**, no hace
  falta.
- **Pasos**:
  1. Crea un proyecto llamado `youtube-autopilot`.
  2. En APIs & Services → Library, habilita **YouTube Data API v3** y **YouTube Analytics API**.
- **Cuota**: 10.000 unidades al día por proyecto. Una subida (`videos.insert`) cuenta 1 unidad, con un límite
  propio de unas 100 subidas al día. La miniatura cuenta 50, un comentario 50 y la lectura de estado 1. Para
  1–2 vídeos al día sobra.

### 4.4 Pantalla de consentimiento OAuth, gratis

APIs & Services → **OAuth consent screen** (en la consola nueva: Google Auth Platform):

1. **User type: External**. Rellena el nombre de la app, tu correo de soporte y tu correo de desarrollador.
2. **Scopes**: añade `youtube.upload`, `youtube.readonly` y `yt-analytics.readonly`. Si quieres comentarios
   automáticos, añade también `youtube.force-ssl`.
3. **Test users**: añade la cuenta de Google del canal.
4. Cuando el token funcione (paso 4.6), pulsa **Publish app → In production**. Esto es imprescindible: en modo
   *Testing* el token caduca **a los 7 días** y la automatización se para. Detalles en la sección 5.

### 4.5 Cliente OAuth: `YOUTUBE_CLIENT_ID` y `YOUTUBE_CLIENT_SECRET`, gratis

- APIs & Services → Credentials → Create credentials → **OAuth client ID**, con tipo **Desktop app**.
- Copia el *Client ID* y el *Client secret*.
- Guárdalos como los secretos `YOUTUBE_CLIENT_ID` y `YOUTUBE_CLIENT_SECRET`, y en tu `.env` para el paso
  siguiente.

### 4.6 Token permanente: `YOUTUBE_REFRESH_TOKEN`, una sola vez y en tu ordenador

Hace falta un navegador, así que este paso se hace en tu ordenador, no en la nube:

```bash
pip install -r requirements.txt
python scripts/youtube_auth.py            # añade --with-comments para permitir comentarios
```

1. Pega el Client ID y el Client secret (el secreto no se ve al escribirlo).
2. Se abre Google: elige la cuenta del canal y marca **todas** las casillas de permisos.
3. Si sale «Google no ha verificado esta aplicación»: es tu propia app. Pulsa Configuración avanzada → Ir a…
4. El token se guarda en `~/.youtube-autopilot/refresh_token` y no se muestra en pantalla.
5. Súbelo como secreto, con la [CLI de GitHub](https://cli.github.com):
   `gh secret set YOUTUBE_REFRESH_TOKEN < ~/.youtube-autopilot/refresh_token`. También puedes pegarlo a mano
   en la web, o usar `--set-github-secret`.
6. **Verifica**: `python scripts/autopilot.py youtube-check` muestra el nombre del canal y no sube nada.

### 4.7 Clave de API de YouTube (opcional): `YOUTUBE_API_KEY`, gratis

Sirve para investigar la competencia (los vídeos recientes más vistos del nicho).

- **Pasos**: Credentials → Create credentials → **API key**. Después pulsa *Edit* → API restrictions → solo
  *YouTube Data API v3*.
- **Cuota**: sale de las mismas 10.000 unidades diarias. Las búsquedas tienen un límite propio de unas 100 al
  día; el sistema hace 3 por idea nueva.
- **Dónde ponerla**: el secreto `YOUTUBE_API_KEY`.
- **Verificar**: `python scripts/autopilot.py trends`. Sin clave, solo usa Wikipedia, que es gratis y no
  necesita clave.

### 4.8 Ejecutor propio en tu PC (opcional, para render gratis e ilimitado)

1. En el repositorio: Settings → Actions → Runners → **New self-hosted runner** → Linux x64. Sigue los comandos
   que muestra: descargar, `./config.sh` con el token y `./svc.sh install`, que lo deja como servicio.
   - En Windows, usa WSL2 con Ubuntu.
   - En Mac no sirve: el flujo instala Blender para Linux.
2. Instala en esa máquina `ffmpeg` y `fonts-inter`.
3. En GitHub crea la variable `RUNS_ON` con el valor `["self-hosted","linux","x64"]`.
4. Mientras el PC esté encendido y el servicio en marcha, los vídeos se renderizan ahí sin gastar minutos.

Ojo: un ejecutor propio en un repo **privado** es seguro, porque solo ejecuta tu código. No lo uses con repos
públicos.

### 4.9 Resto de variables de GitHub (no secretas)

| Variable | Valor recomendado | Para qué |
| --- | --- | --- |
| `AUTOPILOT_ENABLED` | `true` cuando quieras la ejecución diaria | Activa el horario 05:17 UTC |
| `RENDER_MODE` | `hd` | `draft` (barato, 540p), `hd` (publicable), `final` (1080p nativo, 2,2× más caro) |
| `RENDER_SHARDS` | `4` | Trabajos de render en paralelo (1–8) |
| `RUNS_ON` | vacío, o `["self-hosted","linux","x64"]` | Dónde se ejecuta |
| `AI_PROVIDER` | `gemini` | IA de texto (`gemini` gratis, `claude` de pago) |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Modelo de Gemini (ver `ai-check`) |
| `WIKIPEDIA_USER_AGENT` | `YouTubeAutopilot/1.0 (tu-correo)` | Wikimedia pide un contacto |
| `CHANNEL_NAME` | el nombre de tu canal | |
| `YOUTUBE_PUBLISHING_ENABLED` | `false` hasta la primera prueba | Interruptor de subida |
| `YOUTUBE_ALLOW_PUBLIC` | `false` hasta que lo autorices | Interruptor de vídeos públicos o programados |
| `YOUTUBE_DEFAULT_PRIVACY` | `private` | Privacidad de cada subida |

## 5. YouTube: auditoría, pruebas privadas y autenticación permanente

**Pruebas privadas desde ya.** Cualquier proyecto no verificado puede subir vídeos por la API, pero YouTube los
**bloquea como privados** (proyectos creados después del 28‑07‑2020) hasta que el proyecto pasa la auditoría de
cumplimiento. Eso basta para la prueba autorizada:

1. Pon `YOUTUBE_PUBLISHING_ENABLED=true` en tu `.env` (no en GitHub todavía).
2. Ejecuta `python scripts/autopilot.py upload-test media/…/video.mp4`. **Siempre sube en privado**, diga lo que
   diga la configuración.
3. Revisa el vídeo en YouTube Studio y bórralo si quieres.

**Auditoría (para poder publicar en público por la API).** Es gratis, pero tarda de días a semanas.

- **Dónde**: el formulario *YouTube API Services – Audit and Quota Extension*, enlazado en la página de cuota de
  la documentación de YouTube.
- **Qué piden**: cumplir los [Términos de los servicios de la API de YouTube](https://developers.google.com/youtube/terms/api-services-terms-of-service)
  y sus políticas para desarrolladores. Hay que describir el cliente (uso interno: sube los vídeos de tu propio
  canal), qué datos lee y guarda, y aportar pruebas de su funcionamiento.
- **Prepara antes**:
  - Una descripción breve del flujo: guion → render → revisión humana → subida privada → publicación.
  - Capturas o un vídeo de pantalla del proceso: `upload-test` y el vídeo en Studio.
  - Una página de privacidad sencilla: qué datos se guardan (métricas de tus vídeos) y cómo revocar el acceso.
  - El número de proyecto de Google Cloud.
- Mientras tanto, los vídeos se pueden publicar a mano desde Studio después de revisarlos.

**Evitar la caducidad de 7 días.** En *Testing*, Google caduca el refresh token a los 7 días. Pasa la app a
**In production** (botón *Publish app*).

- **Sin verificar la app**, para tu propio uso: solo verás la pantalla de «app no verificada» al autorizar.
  Hay un máximo de 100 usuarios en toda la vida de la app; a ti te basta con 1.
- **Verificarla** solo hace falta para quitar ese aviso o para tener más usuarios. Pide una página de inicio,
  una política de privacidad en un dominio verificado, la justificación de cada permiso sensible y un vídeo de
  demostración.

**El token puede dejar de valer** si revocas el acceso, cambias la contraseña de Google, pasan 6 meses sin
usarlo o hay más de 100 tokens para el mismo cliente. El sistema lo detecta (`invalid_grant`) y el error explica
qué hacer: vuelve a ejecutar `scripts/youtube_auth.py` y actualiza el secreto.

**Autenticación permanente.** El refresh token se guarda como secreto. En cada ejecución el sistema pide un
token de acceso de 1 hora (sin navegador ni intervención) y lo renueva solo si caduca a mitad de la subida. La
subida es **reanudable**: si se corta, pregunta a YouTube cuántos bytes tiene y sigue desde ahí (hasta 6
reintentos con espera creciente).

**Requisitos del canal.**

- Las **miniaturas personalizadas** exigen un canal verificado por teléfono
  ([youtube.com/verify](https://www.youtube.com/verify)). Sin eso, el vídeo se sube igual y queda un aviso.
- **Fijar comentarios** no es posible por la API: el sistema puede publicar el comentario sugerido
  (`YOUTUBE_POST_COMMENT=true`), pero fijarlo se hace a mano en Studio.
- Las **impresiones y el CTR** no están en YouTube Analytics API (están en los informes masivos de la Reporting
  API). Se pueden anotar a mano: `POST /projects/{id}/analytics`.

## 6. Interruptores de seguridad

1. `YOUTUBE_PUBLISHING_ENABLED=false` (por defecto): no se sube nada.
2. Con la publicación activada, cada vídeo necesita **tu aprobación**, salvo que lances la ejecución con
   `--auto-publish`.
3. `YOUTUBE_ALLOW_PUBLIC=false` (por defecto): aunque se suba, el vídeo es **privado**. Los vídeos públicos o
   programados se rechazan **antes** de enviar nada a YouTube.
4. Mientras no se haya superado la auditoría, YouTube deja privado todo lo subido por la API.

## 7. Comandos

```bash
python scripts/autopilot.py preflight            # ¿falta algo para una ejecución desatendida?
python scripts/autopilot.py ai-check             # verifica la clave de la IA (llamada mínima)
python scripts/autopilot.py youtube-check        # verifica el OAuth de YouTube (no sube nada)
python scripts/autopilot.py trends               # tendencias que verá el generador de ideas
python scripts/autopilot.py run --channel "Qué Pasaría Si" --mode hd   # hasta «esperando aprobación»
python scripts/autopilot.py status
python scripts/autopilot.py approve <run_id>     # tras revisar el vídeo
python scripts/autopilot.py resume <run_id>      # reintenta desde el paso que falló
python scripts/autopilot.py upload-test video.mp4  # subida de prueba, siempre privada
python scripts/autopilot.py sync-analytics       # métricas de YouTube → aprendizaje
python scripts/autopilot.py render-shard <run_id> --shard 0 --shards 4   # lo usa el flujo en paralelo
```

En GitHub: Actions → **Autopilot** → Run workflow, con `command` = `run`, `approve`, `resume`, `status` o
`sync-analytics`. Cada ejecución deja un artefacto `review-<run_id>` (5 días) con el vídeo, las miniaturas, la
hoja de capturas de QA y el informe.

Límite a vigilar: el plan Free incluye **500 MB de almacenamiento de artefactos**. Por eso los intermedios se
borran a los 2 días, la revisión a los 5, y nunca se suben los fotogramas PNG.

API: `GET /api/v1/autopilot/preflight`, `POST /api/v1/autopilot/runs`, `GET /api/v1/autopilot/runs/{id}`,
`POST /api/v1/autopilot/runs/{id}/resume`, `POST /api/v1/projects/{id}/publish?privacy=private`,
`POST /api/v1/analytics/sync`.
