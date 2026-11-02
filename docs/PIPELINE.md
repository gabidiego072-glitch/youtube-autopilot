# Pipeline de contenido «¿Qué pasaría si…?»

Todo el sistema está orientado a una única línea editorial, definida en `app/content/profile.py`:
curiosidades, ciencia, situaciones hipotéticas y experimentos mentales. Ese módulo contiene el concepto del
canal, ejemplos de premisas, categorías, tono, **reglas de honestidad científica**, estilo visual hiperrealista
y la lista de términos que sacan al sistema del tema (videojuegos, gaming…). Todos los prompts se construyen a
partir de él.

## 1. Ideas y selección de temas

`app/services/ideas/generator.py` · `POST /channels/{id}/ideas/generate`

- Claude propone premisas con: gancho, ángulo (qué consecuencias seguir), base científica y cuatro notas de 0 a 10.
- Puntuación = 0,35·curiosidad + 0,25·potencial visual + 0,25·base científica + 0,15·perennidad, multiplicada
  por el **peso de su categoría** aprendido de las estadísticas (0,8–1,25).
- Se descartan: premisas que no sean pregunta, duplicados de ideas o proyectos anteriores (comparación
  sin tildes ni «¿Qué pasaría si…»), y cualquier idea que mencione videojuegos.
- El prompt incluye las premisas que mejor han funcionado y el rendimiento por categoría.
- `POST /ideas/{id}/select` crea el proyecto (Short o largo) con su categoría.

Categorías: cuerpo humano, escala y tamaño, velocidad y movimiento, Tierra y clima, espacio, leyes físicas,
tiempo y longevidad, naturaleza y animales, sociedad y tecnología.

## 2. Investigación

`app/services/research/` · `POST /projects/{id}/research`

1. Claude identifica los conceptos científicos reales de la premisa (p. ej. rotación terrestre, fuerza
   centrífuga, ley cuadrado-cubo).
2. Se buscan en **Wikipedia** (API pública y gratuita; exige un `WIKIPEDIA_USER_AGENT` con contacto).
3. Claude extrae los hechos clave **solo de esos textos**, cada uno con su URL; los hechos sin URL válida se descartan.

Estado: `complete`, `partial` o `no_sources` (por ejemplo, si Wikipedia limita las peticiones). Sin fuentes, el
guion se escribe solo con ciencia consolidada y debe etiquetar todo lo demás como estimación o especulación.

## 3. Guion

`app/services/scripts/` · `POST /projects/{id}/scripts/generate`

Estructura obligatoria, validada en código (si no se cumple, el guion se rechaza):

| Tramo | Regla |
| --- | --- |
| `hook` | primera escena, máximo 8 palabras (~2 s), sin saludos |
| `setup` | qué significa la premisa en concreto |
| `escalation` | consecuencias cada vez mayores (≥ 3 en Shorts, ≥ 6 en vídeos largos) |
| `climax` | la consecuencia más extrema |
| `ending` | última escena: conclusión sorprendente o pregunta (termina en «?») para los comentarios |

Cada escena trae sus **afirmaciones** etiquetadas (`established`, `estimate`, `speculation`) con la fuente si
existe, y una descripción de plano realista. La **biblia visual** (estilo, sujetos recurrentes con descripción
física, paleta y lenguaje de cámara) mantiene la coherencia entre escenas. Shorts: 30–60 s. Largos: según
duración objetivo, con *open loops*.

## 4. Verificación científica

`app/services/factcheck/checker.py` · `POST /projects/{id}/scripts/{sid}/fact-check`

Claude revisa cada afirmación frente a las notas de investigación: `correct`, `correct_but_imprecise`,
`mislabeled` (una especulación presentada como hecho), `incorrect` o `unverifiable`. El guion necesita
revisión si hay alguna incorrecta o mal etiquetada, o si una afirmación marcada como «establecida» no se
puede verificar. **La aprobación del vídeo exige que la verificación pase.** Es una ayuda, no sustituye una
revisión humana de las fuentes.

## 5. Imágenes y vídeo hiperrealistas

`app/services/visuals/` · `POST /projects/{id}/visuals/generate`

Prompt de cada plano = descripción de la escena + descripción de los sujetos recurrentes que aparecen + estilo
del guion + estilo del canal («fotorrealista, como grabado con cámara real, documental»). Prompt negativo contra
dibujo, CGI, videojuego, texto o marcas de agua. **Misma semilla en todo el proyecto.** Tamaños: 768×1344 (9:16)
y 1344×768 (16:9).

Proveedores, por orden de preferencia (ninguno se usa si no está configurado):

| Opción | Configuración | Coste |
| --- | --- | --- |
| ComfyUI propio con modelos abiertos (FLUX.1-schnell, Apache-2.0; SDXL…) | `COMFYUI_URL`, `COMFYUI_IMAGE_WORKFLOW` | gratis con tu GPU (o Colab/Kaggle) |
| Hugging Face Inference | `HF_TOKEN`, `HF_IMAGE_MODEL` | créditos mensuales gratuitos limitados |
| Vídeo: ComfyUI image-to-video (Wan 2.x, LTX-Video) | `COMFYUI_VIDEO_WORKFLOW` | gratis con GPU |
| Sin vídeo IA | — | las imágenes se animan con movimiento de cámara en FFmpeg |

Los flujos de ComfyUI se exportan en «API format» y usan marcadores `{{prompt}}`, `{{negative_prompt}}`,
`{{seed}}`, `{{width}}`, `{{height}}` (imagen) e `{{image}}`, `{{prompt}}`, `{{seconds}}`, `{{seed}}` (vídeo).

Generar vídeo hiperrealista con IA necesita una GPU. Sin GPU propia, la opción gratuita realista es la capa
gratuita de Hugging Face para imágenes más animación con FFmpeg; para escenas de escala o crecimiento,
también la visualización 3D con Blender.

## 6. Voz

`app/services/voice/piper.py` · `POST /projects/{id}/voice/generate`

Piper (open source, CPU, sin conexión). `scripts/install_voice.sh` descarga `es_ES-davefx-medium` (conjunto de
datos CC0). Un archivo por escena para que el montaje siga el ritmo real de la voz. `PIPER_LENGTH_SCALE=0.92`
da una narración algo más rápida y dinámica. Antes de monetizar, revisa la licencia de cada voz en su
MODEL_CARD: algunas están ajustadas a partir de otros conjuntos de datos.

## 7. Montaje

`app/services/editing/assembler.py` · `POST /projects/{id}/assemble`

Solo FFmpeg. Cada escena dura lo que su voz más 0,25 s. Las imágenes fijas llevan acercamiento o alejamiento
lento alternado; los clips se recortan a esa duración. Subtítulos grandes por bloques de 4 palabras en Shorts
(9 en vídeos largos), sincronizados con la voz. Música opcional que baja sola cuando habla el narrador.
`EDIT_RESOLUTION_SCALE` permite previsualizar más rápido.

## 8. Metadatos

Título en forma de pregunta (≤ 70 caracteres si es posible), descripción con un apartado de qué es ciencia y
qué es hipótesis y las fuentes, etiquetas científicas más generales, hashtags (#Shorts en Shorts), categoría
de YouTube 28 (Ciencia y tecnología) y un **comentario fijado** con una pregunta. Se validan los límites de
YouTube.

## 9. Estadísticas y mejora automática

Las métricas usan los nombres de la YouTube Analytics API. El análisis compara formatos, **categorías** y
**tipos de final** (comentarios por cada 1.000 vistas: ¿funciona mejor terminar con pregunta?) y detecta caídas
de retención. Con suficientes datos (≥ 3 vídeos por grupo), las categorías que superan la mediana pesan más al
generar y ordenar nuevas ideas, y las mejores premisas se usan como referencia.
