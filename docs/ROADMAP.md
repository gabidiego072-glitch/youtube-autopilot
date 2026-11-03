# Hoja de ruta

Línea editorial fija: curiosidades, ciencia, situaciones hipotéticas y experimentos mentales («¿Qué pasaría
si…?»). Sin videojuegos ni gaming. Vídeos 100 % generados por código (animación 3D procedural con Blender),
sin imágenes de IA ni hiperrealismo. Prioridad: automatización en la nube con herramientas gratuitas.
Cada fase termina con código probado; nada se marca como hecho si no funciona contra el servicio real.

## Fase 0 — Base ✅ (v0.1)

- [x] FastAPI, PostgreSQL/Supabase, migraciones Alembic, configuración por variables de entorno, Docker, CI
- [x] Canales, proyectos Short/largo, máquina de estados, proveedor Claude, metadatos, analítica manual, informes, panel
- [x] Interfaces de YouTube con bloqueo de seguridad (sin publicación)

## Fase 0.5 — Visualización 3D ✅ (v0.1)

- [x] Motor 3D procedural en Blender (Cycles, CPU, sin GPU): personajes, entornos, luz, cámara, 9:16 y 16:9
- [x] Ejemplo «¿Qué pasaría si cada paso que das crecieras un centímetro?»
- [x] El motor voxel/estilo videojuego se retiró al fijar la línea editorial (sigue en el historial de git)

## Fase 1 — Pipeline «¿Qué pasaría si…?» ✅ (v0.2, esta versión)

- [x] Perfil editorial único que alimenta todos los prompts; filtro anti-gaming en ideas, guiones y metadatos
- [x] Generación de ideas puntuadas, sin duplicados, ponderadas por el rendimiento por categoría
- [x] Investigación con Wikipedia (gratis) y hechos clave con fuente
- [x] Guiones con gancho ≤ 2 s, escalada de consecuencias, final con pregunta o conclusión, afirmaciones etiquetadas
- [x] Verificación científica obligatoria antes de aprobar
- [x] Voz en español con Piper (gratis, offline)
- [x] Montaje FFmpeg: ritmo de voz, subtítulos sincronizados, música con ducking
- [x] Metadatos con fuentes, «ciencia vs. hipótesis» y comentario fijado
- [x] Aprendizaje por categoría y tipo de final

## Fase 1.5 — Vídeos generados solo por código ✅ (v0.3, esta versión)

- [x] Retirada la generación de imágenes y vídeo por IA (Hugging Face, ComfyUI) y los prompts hiperrealistas
- [x] Catálogo del motor 3D como única fuente para el validador y para los prompts
- [x] Storyboard: cada escena del guion se convierte en una escena del motor, validada antes de guardarse
- [x] Render de cada escena con Blender en segundo plano, ajustada a la duración de su voz
- [x] Motor: entorno espacial con estrellas, planetas procedurales (Tierra con océanos, continentes, nubes y
      atmósfera; Luna; Marte; Sol), acciones `spin` y `scale`
- [x] Ejemplo «¿Qué pasaría si la Tierra dejase de girar?»

## Fase 2 — Calidad de contenido

- [ ] Regeneración automática de un guion cuando la verificación falla, usando las correcciones
- [ ] Más fuentes gratuitas (Wikidata, NASA Open APIs, arXiv) y citas por escena en la descripción
- [ ] Coste y tokens por vídeo; límite de gasto por canal
- [ ] Conjunto de evaluación de guiones (ganchos, precisión) para comparar versiones de prompts
- [ ] Biblioteca de música y efectos libres de derechos

## Fase 3 — Más vocabulario visual para el motor 3D

- [ ] Entornos: ciudad, océano, interior, laboratorio, sistema solar a escala
- [ ] Objetos: edificios, vehículos, animales, cuerpo humano simplificado, flechas y gráficos 3D (escalas, órbitas)
- [ ] Acciones: caer, volar, explosión/onda expansiva, cambio de gravedad, paso del tiempo (día/noche)
- [ ] Texto 3D y medidores dentro de la escena (alturas, velocidades)
- [ ] Miniaturas: fotograma del render + texto compuesto a 1280×720, varias variantes

## Fase 4 — Ejecución en la nube

- [ ] Cola de trabajos y worker para investigación, imágenes, voz y montaje (fuera de la petición HTTP)
- [ ] Almacenamiento de medios en Supabase Storage o S3
- [ ] Workers de CPU para Blender/FFmpeg que reparten las escenas en paralelo (y GPU opcional para Cycles)

## Fase 5 — Publicación en YouTube

- [ ] OAuth por canal (tokens cifrados), subida reanudable, miniatura, programación, comentario fijado
- [ ] Control de cuota; subidas en `private` por defecto; aprobación humana obligatoria

## Fase 6 — Estadísticas automáticas

- [ ] Recolector programado de la YouTube Analytics API (vistas, CTR, retención, comentarios)
- [ ] Curvas de retención por escena (¿en qué consecuencia se va la gente?)

## Fase 7 — Aprendizaje avanzado

- [ ] Retención por tramo del guion para ajustar el ritmo de la escalada
- [ ] Experimentos A/B de gancho, duración y hora de publicación
- [ ] Informes automáticos semanales con resumen escrito

## Fase 8 — Panel y multiusuario

- [ ] Panel web, cuentas (Supabase Auth), permisos y RLS
