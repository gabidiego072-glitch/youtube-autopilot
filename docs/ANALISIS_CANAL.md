# Análisis del canal con datos reales

Se genera con el comando `channel-report` (menú del workflow *Autopilot* → `channel-report`). Todos los
números vienen de la YouTube Data API y de la YouTube Analytics API. Si una métrica no llega, se queda
vacía: no se estima.

## Informe del 7 de noviembre de 2026

| Publicado (Madrid) | Duración | Vistas | Se quedan a ver* | % medio visto | Likes | Coment. | Subs | Vídeo |
|---|---|---|---|---|---|---|---|---|
| mié 04-11 14:13 | 44 s | 1.682 | 53 % | 55 % | 27 | 1 | 2 | La Tierra frenara en seco |
| jue 05-11 14:13 | 30 s | 1.131 | 34 % | 50 % | 27 | 0 | 1 | La fricción desapareciera |
| jue 05-11 23:03 | 41 s | 1.201 | 46 % | 54 % | 34 | 0 | 2 | Todos los humanos cayeran dormidos |
| sáb 07-11 11:08 | 42 s | 84** | — | — | — | — | — | Los metales perdieran su conductividad |

\* *engaged views / views*: la parte de las vistas que no deslizó en los primeros segundos.
\*\* Contador público unas 9 horas después de publicarse. YouTube Analytics tarda entre 2 y 3 días, así
que ese vídeo todavía no tiene datos de retención.

### Lo que dicen los datos

1. **Casi todo el tráfico viene del feed de Shorts** (entre el 96 % y el 98 % de las vistas). El
   crecimiento depende de que YouTube siga enseñando los vídeos en el feed, y eso depende de cuánta gente
   se queda a verlos.
2. **Entre la mitad y dos tercios de la gente desliza al principio**: solo se queda a ver entre el 34 % y
   el 53 %. El vídeo con más vistas (el de la Tierra) es también el que más gente retuvo.
3. **La gran caída llega entre el 10 % y el 25 % del vídeo** (más o menos entre los segundos 4 y 10).
   Ahí se pasa de ~1,1 a ~0,65 en la curva de audiencia en los tres vídeos. Es justo la escena de
   "planteamiento", en la que el guion explicaba la premisa antes de enseñar algo.
4. **Frente a Shorts de duración parecida, la retención relativa es baja en la primera mitad** (~0,3; la
   media de YouTube es 0,5) y buena al final (~0,8). Quien llega a la mitad se queda hasta el final.
5. **Casi ningún comentario y ningún compartido**: el final no invita a responder.
6. **El vídeo de hoy** (conductividad de los metales) arranca muy por debajo: 84 vistas en unas 9 horas,
   cuando los anteriores sumaron más de 1.000 el primer día. Es la primera premisa "abstracta": una
   propiedad física que hay que explicar antes de que pase algo visible. **Hipótesis por confirmar**
   cuando lleguen sus datos de retención.
7. **Hora de publicación**: con 4 vídeos no hay datos suficientes para sacar conclusiones (dos a las
   14:13, uno a las 23:03 y otro a las 11:08).

### Cambios aplicados a partir de estos datos

- **Guion (prompt v6)**:
  - arranque en frío con la imagen más fuerte;
  - el "planteamiento" ya no explica nada: enseña lo primero que le pasa a una persona en el segundo 3-5;
  - un evento visible nuevo cada 3-5 segundos;
  - un bucle abierto a mitad del vídeo;
  - un final con pregunta para que la gente comente.
- **Temas (prompt ideas-v2)**: "prueba del primer segundo". El espectador tiene que sentir la premisa en
  su cuerpo o en su casa al instante. Las propiedades abstractas puntúan bajo.
- **Aprendizaje**: la puntuación de cada variante (voz, música, duración, gancho) usa ahora también la
  proporción de gente que se queda a ver, no solo la retención y las vistas.

### Prueba de horarios

Como YouTube deja los vídeos en privado hasta que se pasan a público a mano, la hora real de publicación es
la de ese cambio. Prueba propuesta: rotar las franjas **14:00, 19:00 y 21:30** (hora de Madrid), un vídeo
por franja, y repetir. Con unos 9 vídeos, `channel-report` muestra la mediana de vistas por franja
(`by_publish_slot`).

## Informe del 10 de noviembre de 2026 (datos reales de YouTube Analytics)

Canal en español, vídeos públicos (vistas a 10 nov; "se quedan" = proporción de gente que no desliza):

| Publicado | Vídeo | Vistas | Se quedan | Retención al final |
|---|---|---|---|---|
| 4 nov 14:13 | La Tierra frena en seco | 1.692 | 53 % | 22 % |
| 5 nov 14:13 | La fricción desaparece | 1.147 | 34 % | 22 % |
| 5 nov 23:03 | Todos los humanos se duermen | 1.216 | 46 % | 23 % |
| 7 nov 11:08 | Los metales pierden su conductividad | 108 | 49 % | 25 % |
| 7 nov 23:26 | La gravedad baja un 1 % | 299 | **23 %** | 16 % |
| 8 nov 13:52 | Los árboles dejan de absorber CO₂ | 96 | (aún sin datos) | |
| 9 nov 11:08 | Zombis POV | 121 | (aún sin datos) | |
| 10 nov 09:16 | Ayudar a todas las personas sin hogar (sistema nuevo) | **1.051** en el primer día | (aún sin datos) | |

Canal en inglés: lluvia hacia arriba (sistema nuevo) 1.231 vistas; zombis 65; envejecer 10 años (hoy) 70.
YouTube tarda unos 3 días en dar retención, así que los vídeos del 8-10 nov aún no la tienen.

### Lo que dicen

1. **La hipótesis del 7 nov se confirma: las premisas abstractas o pequeñas no despegan.** Conductividad
   (108), un 1 % menos de gravedad (299) y árboles que dejan de absorber CO₂ (96) se quedan por debajo de
   300 vistas, frente a más de 1.000 de las premisas grandes y que se sienten en el cuerpo (la Tierra
   frena, la fricción desaparece, todos se duermen).
2. **No es solo la retención.** El de los metales retuvo como los buenos (49 % se quedan), pero YouTube
   apenas lo enseñó (96 vistas del feed). El tema y el título deciden cuánta gente lo prueba al principio.
3. **El cambio pequeño es el peor gancho.** "Un 1 %" tiene el peor dato del canal: solo se queda el 23 %.
4. **Los vídeos del sistema nuevo vuelven a superar las 1.000 vistas** (sin hogar en español, lluvia en
   inglés), con temas concretos y humanos. Falta su retención para confirmar que el arranque nuevo
   retiene más.
5. **Zombis rinde poco en los dos canales** (121 y 65). Es un tema muy visto; hipótesis por confirmar
   cuando lleguen sus datos.

### Cambios aplicados

- Ideas: los ejemplos malos incluyen ya "un 1 por ciento" y los porcentajes pequeños; la premisa tiene
  que ser un cambio grande, absoluto y visible.
- Siguiente revisión: cuando lleguen los datos de retención de sin hogar, lluvia, envejecer y dinosaurios
  (TikTok), comparar el sistema nuevo con el anterior.
