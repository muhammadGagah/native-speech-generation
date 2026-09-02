# Native Speech Generation para NVDA

**Autor:** Muhammad Gagah [muha.aku@gmail.com](mailto:muha.aku@gmail.com)

Native Speech Generation es un complemento para NVDA que integra **Google Gemini AI** para generar voz natural y de alta calidad directamente desde NVDA.
Ofrece una interfaz limpia y totalmente accesible para convertir texto en audio, con soporte tanto para **narración de un solo hablante** como para **diálogos dinámicos con varios hablantes**.

Este complemento está pensado para ofrecer un flujo de trabajo fluido, una interacción centrada en la accesibilidad y un control flexible de la voz, ideal para narración, diálogos y producción de contenido de audio.

---

## Características

### Generación de voz de alta calidad

* Elige entre:
  * **Gemini Flash**: calidad estándar, generación rápida y baja latencia.
  * **Gemini Pro**: calidad premium y voces más realistas (modelo de pago).

### Modos de hablante único y múltiple

* **Narración de un solo hablante** para conversión de texto a voz estándar.
* **Modo multihablante (2 hablantes)** para diálogos con voces diferenciadas.

### Control de voz avanzado

* **Nombres de los hablantes**
  Asigna nombres personalizados (por ejemplo, *Juan* o *María*) en el modo multihablante.
  La IA asigna las voces automáticamente según los nombres usados en el guion.
* **Instrucciones de estilo**
  Puedes dar indicaciones como *"Habla con un tono alegre"* o *"Narra con calma"* para orientar la interpretación.
* **Control de temperatura**
  Ajusta la variación y la creatividad del resultado:
  * Valores más bajos -> voz más estable y predecible.
  * Valores más altos -> voz más expresiva y variada.

### Interfaz accesible y clara

* Totalmente accesible con lectores de pantalla.
* Las opciones avanzadas están dentro de un panel desplegable para que el diálogo principal se mantenga simple y enfocado.

### Flujo de trabajo fluido

* El audio se reproduce automáticamente después de la generación.
* El audio generado puede reproducirse de nuevo o guardarse como archivo `.wav` de alta calidad.
* Está diseñado para reducir al mínimo la fricción durante la generación y la reproducción repetidas.

### Carga inteligente de voces y caché

* Las voces disponibles se obtienen dinámicamente desde la API de Gemini.
* Los datos de voz se almacenan en caché durante **24 horas** para reducir llamadas a la API y acelerar el inicio.

### Quick Speak

* Pulsa **NVDA+Alt+E** para leer inmediatamente el texto seleccionado.
* Pulsa **NVDA+Alt+Mayús+E** para leer texto sin formato del portapapeles.
* El audio se reproduce internamente mediante el dispositivo de salida configurado en NVDA, por lo que el foco permanece en la aplicación actual.
* Quick Speak tiene ajustes independientes de modelo, voz, volumen e instrucciones de pronunciación/estilo.
* El volumen de Quick Speak va de 0 (silencio) a 100 (volumen máximo) y se conserva al reiniciar NVDA.
* El texto seleccionado o del portapapeles se envía a Google Gemini para generar el audio.
* Gemini 3.1 Flash Live Preview es la opción recomendada para baja latencia. Siguen aplicándose las cuotas de API y los límites de sesión Live. El servicio no es ilimitado.
* Los modelos disponibles para Quick Speak son Gemini 3.1 Flash Live Preview, Gemini 2.5 Flash Native Audio, Gemini 3.1 Flash TTS Preview, Gemini 2.5 Flash TTS Preview y Gemini 2.5 Pro TTS Preview. El modelo Pro requiere una API de pago.
* Pulsa de nuevo cualquiera de los comandos de Quick Speak para detener la solicitud o reproducción activa.

### Hablar con IA (conversación en vivo)

* **Chat de voz en tiempo real**: mantén una conversación hablada natural y de baja latencia con Gemini.
* **Grounding con Google Search**: permite que la IA acceda a información en tiempo real desde la web durante la conversación.
* **Interrumpible**: puedes interrumpir a la IA en cualquier momento hablando o pulsando "Detener conversación".
* **Personalizable**: usa la voz y las instrucciones de estilo que hayas seleccionado.
* **Control del nivel de razonamiento**: elige entre `Sin razonamiento`, `Bajo`, `Medio` o `Alto` según la profundidad de razonamiento que necesites.
* **Continuidad tras la reconexión**: el contexto reciente de la conversación se restaura automáticamente después de reconectar, sin necesidad de un interruptor de memoria independiente.
* **Streaming más estable**: reconexión mejorada (backoff + retry) y búfer de audio adaptativo para mayor resistencia en redes inestables.

---

## Requisitos

* NVDA 2024.1 o posterior. Probado hasta NVDA 2026.2.
* Conexión activa a Internet.
* Una **clave de API de Google Gemini** válida.

---

## Instalación

1. Descarga el paquete más reciente del complemento desde la
   **página de versiones:**
   [https://github.com/MuhammadGagah/native-speech-generation/releases](https://github.com/MuhammadGagah/native-speech-generation/releases)
2. Instálalo como cualquier complemento estándar de NVDA.
3. Reinicia NVDA cuando se te solicite.

---

## Configuración de la clave de API (obligatoria)

1. Crea una clave de API en **Google AI Studio**:
   [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Abre NVDA y ve a:
   **Menú de NVDA -> Herramientas -> Native Speech Generation**
3. Haz clic en **"Configuración de la clave API"**.
4. Esto abre la configuración de NVDA directamente en la categoría *Native Speech Generation*.
5. Pega tu **clave de API de Gemini** en el campo *GEMINI API Key*.
6. Haz clic en **Aceptar** para guardar.

Las claves guardadas se almacenan de forma segura mediante **Windows DPAPI**, por lo que el valor cifrado no puede descifrarse en otro equipo con Windows ni en otra cuenta de usuario.

Para entornos avanzados o gestionados, también puedes proporcionar la clave mediante la variable de entorno **`GEMINI_API_KEY`**. El complemento la usará automáticamente cuando no haya una clave guardada disponible.

---

## Cómo usar

Abre el diálogo usando:

* **NVDA+Control+Shift+G**, o
* **Menú de NVDA -> Herramientas -> Native Speech Generation**

### Elementos principales de la interfaz

* **Texto a convertir**
  Escribe o pega el texto que quieras convertir en voz.
* **Instrucciones de estilo (opcional)**
  Añade indicaciones sobre tono, emoción o forma de hablar.
* **Seleccionar modelo**
  * Flash (calidad estándar)
  * Pro (alta calidad)
* **Modo de hablante**
  * Un solo hablante
  * Multihablante (2)

---

## Generación de voz

### Quick Speak para texto seleccionado o del portapapeles

1. Abre **Configuración de NVDA -> Native Speech Generation** y elige el modelo, la voz, el volumen y las instrucciones opcionales de pronunciación/estilo.
2. Selecciona texto y pulsa **NVDA+Alt+E**, o copia texto y pulsa **NVDA+Alt+Mayús+E**.
3. La voz se reproduce sin abrir un diálogo ni cambiar el foco de aplicación.
4. Pulsa de nuevo cualquiera de los comandos para detener Quick Speak.

Los estados rutinarios de inicio, finalización y reproducción permanecen en silencio. Solo se anuncian los errores que requieren una acción.

### Modo de hablante único

1. Selecciona **Un solo hablante**.
2. Elige una voz en la lista *Seleccionar voz*.
3. Introduce tu texto.
4. Añade instrucciones de estilo si lo deseas.
5. Haz clic en **Generar voz**.
6. El audio se reproducirá automáticamente cuando termine la generación.

---

### Modo multihablante

1. Selecciona **Multihablante (2)**.
2. Para cada hablante:
   * Introduce un **nombre de hablante** único.
   * Elige una **voz** distinta.
3. Da formato al texto para que cada línea comience con el nombre del hablante seguido de dos puntos.

**Ejemplo:**

```
Alicia: Hola, Bob. ¿Cómo estás hoy?
Bob: ¡Muy bien, Alicia! Hace un tiempo fantástico.
```

4. Haz clic en **Generar voz**.
   Las voces se asignarán automáticamente según los nombres de los hablantes.

---

## Hablar con IA (modo en vivo)

Disfruta de una conversación de voz bidireccional y natural con Gemini.

1. Configura la **Voz** y las **Instrucciones de estilo** que quieras en el diálogo principal.
   *(Nota: Hablar con IA actualmente solo admite el modo de un solo hablante).*
2. Haz clic en **Hablar con IA**.
3. En la nueva ventana:
   * **Iniciar conversación**: inicia la sesión. Habla por tu micrófono.
   * **Detener conversación**: finaliza la sesión.
   * **Grounding con Google Search**: marca esta casilla para permitir que Gemini busque respuestas en la web (por ejemplo, noticias o el clima actual).
     * *Nota: esta casilla se oculta mientras la conversación está activa. Detén la conversación para cambiarla.*
   * **Nivel de razonamiento**: elige entre `Sin razonamiento`, `Bajo`, `Medio` o `Alto`.
   * **Micrófono**: silencia o activa tu micrófono.
   * **Volumen**: ajusta el volumen de reproducción de la IA. El volumen y los dispositivos de entrada y salida seleccionados se guardan al cerrar el diálogo.

---

## Configuración avanzada

* Activa **Configuración avanzada (temperatura)** para mostrar el control deslizante.
* **Rango de temperatura**:
  * `0.0` -> resultado más determinista y estable.
  * `1.0` -> equilibrio predeterminado.
  * `2.0` -> resultado más creativo y variado.

---

## Resumen de botones

* **Generar voz** - Inicia la generación de voz.
* **Reproducir** - Vuelve a reproducir el último audio generado.
* **Hablar con IA** - Abre la interfaz de conversación de voz en tiempo real.
* **Guardar audio** - Guarda el último audio como archivo `.wav`.
* **Configuración de la clave API** - Abre la configuración del complemento en los ajustes de NVDA.
* **Ver voces en AI Studio** - Abre Google AI Studio en el navegador.
* **Cerrar** - Cierra el diálogo (o pulsa `Escape`).

---

## Gestos de entrada

Personalizable desde:
**Menú de NVDA -> Preferencias -> Gestos de entrada -> Native Speech Generation**

Gesto predeterminado:

* **NVDA+Control+Shift+G** - Abrir el diálogo de Native Speech Generation.
* **NVDA+Alt+E** - Leer texto seleccionado con Quick Speak o detener Quick Speak.
* **NVDA+Alt+Mayús+E** - Leer texto del portapapeles con Quick Speak o detener Quick Speak.

Todos los comandos pueden cambiarse o eliminarse en Gestos de entrada de NVDA.

---

## Guía de desarrollo y contribución

Si quieres desarrollar o modificar este complemento, sigue los pasos siguientes.

### Configuración del entorno

* **Python correspondiente al runtime de NVDA objetivo**
  * Usa **Python 3.13 de 64 bits** para NVDA 2026.1 y versiones posteriores.
  * Usa **Python 3.11 de 32 bits** solo para empaquetar dependencias de versiones anteriores de NVDA compatibles.
* **uv** para la cadena de herramientas de compilación y lint fijada.

  ```
  uv sync
  uv run pre-commit run --all-files
  uv run scons
  uv run scons pot
  ```

  SCons 4.10.1, Markdown 3.10, Ruff 0.14.10, Pyright 1.1.407 y las demás herramientas de compilación se instalan desde `uv.lock`.
* **Herramientas GNU Gettext** (opcional, recomendado para localización)
  * Normalmente vienen preinstaladas en Linux/Cygwin.
  * Windows: [https://gnuwin32.sourceforge.net/downlinks/gettext.php](https://gnuwin32.sourceforge.net/downlinks/gettext.php)
### Dependencias adicionales

Solo para desarrollo local, instala las dependencias de audio de Talk With AI directamente en la ruta de bibliotecas del complemento usando la versión y arquitectura de Python que coincidan con el runtime de NVDA que estás probando:

```
python.exe -m pip install pyaudio --target "D:/myAdd-on/Native-Speech-Generation/addon/globalPlugins/NativeSpeechGeneration/lib"
```

Ajusta la ruta según tu directorio local del código fuente del complemento.

La función de compartir pantalla usa la captura de Windows/wx ya disponible en NVDA, por lo que no necesitas `opencv-python`, `pillow` ni `mss`.

Para los paquetes de lanzamiento, el complemento descarga únicamente la rueda fijada de PyAudio 0.2.14 que coincide con la ABI y la arquitectura de Python integradas en NVDA (`cp311` a `cp313`, `win32` o `win_amd64`). El SHA-256 está fijado en el complemento, se compara con los metadatos de PyPI y se verifica de nuevo después de la descarga. No se instala el SDK Google GenAI ni sus dependencias transitivas. La rueda se extrae en `addon/globalPlugins/NativeSpeechGeneration/lib`.

---

## Contribuir

Las contribuciones, sugerencias y reportes de errores son muy bienvenidos.

* Abre un **Issue** para reportar errores o solicitar funciones.
* Envía un **Pull Request** para contribuir con código.

**Contacto**

* Email: `muha.aku@gmail.com`
* GitHub: [https://github.com/MuhammadGagah](https://github.com/MuhammadGagah)
