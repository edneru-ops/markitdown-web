"""
Versión pública de la app MarkItDown, pensada para desplegarse en Render / PythonAnywhere.

- Pide una contraseña compartida antes de dejar usar la app (variable de entorno APP_PASSWORD).
- Permite convertir hasta 10 archivos a la vez.
- Los archivos convertidos se descargan automáticamente como .md, sin mostrar
  el texto en pantalla (más ágil para documentos largos).
- Límite de 50 MB en total por lote, pensado para un servidor gratuito compartido.
"""

import os
import secrets
import tempfile
from functools import wraps

from flask import Flask, jsonify, redirect, request, session, url_for
from markitdown import MarkItDown

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(16))
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB máximo por lote

CONTRASENA = os.environ.get("APP_PASSWORD", "")
MAX_ARCHIVOS_POR_LOTE = 10

conversor = MarkItDown()


def requiere_login(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        if CONTRASENA and not session.get("autenticado"):
            return redirect(url_for("login"))
        return vista(*args, **kwargs)
    return envoltura


@app.errorhandler(413)
def archivo_demasiado_grande(e):
    return jsonify({
        "error": f"El lote supera el límite de {app.config['MAX_CONTENT_LENGTH'] // (1024*1024)} MB en total. "
                  "Prueba con menos archivos o archivos más pequeños."
    }), 413


LOGIN_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MarkItDown - Acceso</title>
<style>
  body {{
    margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center;
    font-family: -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
    background: #f4f5f7; color: #23262b;
  }}
  .tarjeta {{
    background: white; border: 1px solid #d8dbe0; border-radius: 12px;
    padding: 32px; width: 100%; max-width: 340px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);
  }}
  h1 {{ font-size: 1.2rem; margin: 0 0 18px 0; }}
  input {{
    width: 100%; padding: 10px 12px; border-radius: 7px; border: 1px solid #d8dbe0;
    font-size: 0.95rem; box-sizing: border-box; margin-bottom: 12px;
  }}
  button {{
    width: 100%; padding: 10px; border-radius: 7px; border: none;
    background: #2f6f4f; color: white; font-size: 0.95rem; cursor: pointer;
  }}
  button:hover {{ background: #245a3f; }}
  .error {{ color: #b3261e; font-size: 0.85rem; margin: -6px 0 12px 0; }}
</style>
</head>
<body>
  <div class="tarjeta">
    <h1>Acceso a MarkItDown</h1>
    <form method="POST">
      {mensaje_error}
      <input type="password" name="password" placeholder="Contraseña" autofocus>
      <button type="submit">Entrar</button>
    </form>
  </div>
</body>
</html>
"""


@app.route("/login", methods=["GET", "POST"])
def login():
    mensaje_error = ""
    if request.method == "POST":
        if request.form.get("password") == CONTRASENA:
            session["autenticado"] = True
            return redirect(url_for("index"))
        mensaje_error = '<div class="error">Contraseña incorrecta.</div>'
    return LOGIN_HTML.format(mensaje_error=mensaje_error)


PAGINA_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MarkItDown - Convertidor a Markdown</title>
<style>
  :root {
    --bg: #f4f5f7; --card: #ffffff; --border: #d8dbe0;
    --accent: #2f6f4f; --text: #23262b; --muted: #6b7280;
    --error: #b3261e; --error-bg: #fdecea;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; font-family: -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
    background: var(--bg); color: var(--text);
    display: flex; justify-content: center; padding: 48px 16px;
  }
  .contenedor { width: 100%; max-width: 720px; }
  h1 { font-size: 1.5rem; margin: 0 0 4px 0; }
  p.subtitulo { color: var(--muted); margin: 0 0 28px 0; }
  .tarjeta {
    background: var(--card); border: 1px solid var(--border); border-radius: 12px;
    padding: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);
  }
  #zona-arrastre {
    border: 2px dashed var(--border); border-radius: 10px;
    padding: 48px 24px; text-align: center; cursor: pointer;
    transition: border-color 0.15s ease, background 0.15s ease;
  }
  #zona-arrastre.sobre-zona { border-color: var(--accent); background: #eef6f1; }
  #zona-arrastre svg { margin-bottom: 12px; opacity: 0.6; }
  #zona-arrastre p.principal { font-size: 1.05rem; margin: 0 0 4px 0; }
  #zona-arrastre p.secundario { font-size: 0.85rem; color: var(--muted); margin: 0; }
  #entrada-archivo { display: none; }
  #estado { margin-top: 18px; display: none; align-items: center; }
  #estado.visible { display: flex; }
  .spinner {
    width: 20px; height: 20px; border: 3px solid #d8dbe0; border-top-color: var(--accent);
    border-radius: 50%; display: inline-block; margin-right: 10px;
    animation: girar 0.8s linear infinite; flex-shrink: 0;
  }
  @keyframes girar { to { transform: rotate(360deg); } }
  #error-general {
    margin-top: 18px; padding: 12px 16px; background: var(--error-bg); color: var(--error);
    border-radius: 8px; font-size: 0.9rem; display: none;
  }
  #error-general.visible { display: block; }
  #resultados { margin-top: 20px; display: none; }
  #resultados.visible { display: block; }
  .resultado-item { border: 1px solid var(--border); border-radius: 8px; margin-bottom: 8px; padding: 10px 14px; }
  .resultado-fila { display: flex; justify-content: space-between; align-items: center; font-size: 0.9rem; }
  .resultado-fila .nombre { font-weight: 600; }
  .resultado-fila .estado-ok { color: var(--accent); font-size: 0.8rem; }
  .resultado-fila .estado-error { color: var(--error); font-size: 0.8rem; }
  .mensaje-error { color: var(--error); font-size: 0.82rem; margin-top: 6px; }
  .acciones { margin-top: 14px; display: flex; gap: 10px; flex-wrap: wrap; }
  button {
    font-family: inherit; font-size: 0.85rem; padding: 8px 14px; border-radius: 7px;
    border: 1px solid var(--border); background: white; cursor: pointer;
  }
  button:hover { background: #f0f0f0; }
  .aviso-tamano { font-size: 0.78rem; color: var(--muted); margin-top: 10px; text-align: center; }
  .aviso-descarga { font-size: 0.78rem; color: var(--muted); margin-top: 10px; }
</style>
</head>
<body>
<div class="contenedor">
  <h1>MarkItDown</h1>
  <p class="subtitulo">Convierte hasta 10 archivos a Markdown arrastrándolos aquí. Todo ocurre en tu propio computador.</p>

  <div class="tarjeta">
    <div id="zona-arrastre">
      <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#6b7280" stroke-width="1.5">
        <path d="M12 15V3m0 12-4-4m4 4 4-4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      <p class="principal">Arrastra tus archivos aquí, o haz clic para elegirlos</p>
      <p class="secundario">PDF, Word, Excel, PowerPoint, imágenes, HTML y más</p>
    </div>
    <input type="file" id="entrada-archivo" multiple>
    <p class="aviso-tamano">Hasta 10 archivos por lote · 200 MB en total · se descargan como .md automáticamente</p>

    <div id="estado"><span class="spinner"></span>Convirtiendo, un momento...</div>
    <div id="error-general"></div>

    <div id="resultados"></div>
    <div class="acciones" id="acciones-lote" style="display:none;">
      <button id="otro-lote">Convertir otro lote</button>
    </div>
  </div>
</div>

<script>
const zona = document.getElementById('zona-arrastre');
const entrada = document.getElementById('entrada-archivo');
const estado = document.getElementById('estado');
const errorGeneral = document.getElementById('error-general');
const resultados = document.getElementById('resultados');
const accionesLote = document.getElementById('acciones-lote');
const MAX_ARCHIVOS = 10;

zona.addEventListener('click', () => entrada.click());
zona.addEventListener('dragover', (e) => { e.preventDefault(); zona.classList.add('sobre-zona'); });
zona.addEventListener('dragleave', () => zona.classList.remove('sobre-zona'));
zona.addEventListener('drop', (e) => {
  e.preventDefault();
  zona.classList.remove('sobre-zona');
  if (e.dataTransfer.files.length > 0) convertirLote(e.dataTransfer.files);
});
entrada.addEventListener('change', () => {
  if (entrada.files.length > 0) convertirLote(entrada.files);
});
document.getElementById('otro-lote').addEventListener('click', () => {
  resultados.classList.remove('visible');
  resultados.innerHTML = '';
  accionesLote.style.display = 'none';
  errorGeneral.classList.remove('visible');
  entrada.value = '';
});

async function convertirLote(listaArchivos) {
  errorGeneral.classList.remove('visible');
  resultados.classList.remove('visible');
  resultados.innerHTML = '';
  accionesLote.style.display = 'none';

  if (listaArchivos.length > MAX_ARCHIVOS) {
    errorGeneral.textContent = `Elegiste ${listaArchivos.length} archivos. El máximo por lote es ${MAX_ARCHIVOS}.`;
    errorGeneral.classList.add('visible');
    return;
  }

  estado.classList.add('visible');
  const datos = new FormData();
  for (const archivo of listaArchivos) {
    datos.append('archivo', archivo);
  }

  try {
    const respuesta = await fetch('/convertir', { method: 'POST', body: datos });
    if (respuesta.status === 401) { window.location.href = '/login'; return; }
    const cuerpo = await respuesta.json();
    if (!respuesta.ok) throw new Error(cuerpo.error || 'Ocurrió un error al convertir los archivos.');
    mostrarResultados(cuerpo.resultados);
  } catch (err) {
    errorGeneral.textContent = err.message;
    errorGeneral.classList.add('visible');
  } finally {
    estado.classList.remove('visible');
  }
}

function mostrarResultados(listaResultados) {
  resultados.innerHTML = '';
  let huboDescargas = false;

  listaResultados.forEach((r) => {
    const item = document.createElement('div');
    item.className = 'resultado-item';

    const fila = document.createElement('div');
    fila.className = 'resultado-fila';
    fila.innerHTML = `<span class="nombre">${r.nombre_original}</span>` +
      (r.error ? `<span class="estado-error">Error</span>` : `<span class="estado-ok">Descargado ✓</span>`);
    item.appendChild(fila);

    if (r.error) {
      const msg = document.createElement('div');
      msg.className = 'mensaje-error';
      msg.textContent = r.error;
      item.appendChild(msg);
    } else {
      const blob = new Blob([r.markdown], { type: 'text/markdown;charset=utf-8' });
      const enlace = document.createElement('a');
      enlace.href = URL.createObjectURL(blob);
      enlace.download = r.nombre_archivo;
      document.body.appendChild(enlace);
      enlace.click();
      document.body.removeChild(enlace);
      URL.revokeObjectURL(enlace.href);
      huboDescargas = true;
    }

    resultados.appendChild(item);
  });

  if (huboDescargas) {
    const aviso = document.createElement('p');
    aviso.className = 'aviso-descarga';
    aviso.textContent = 'Si tu navegador bloqueó alguna descarga, permite descargas múltiples para este sitio.';
    resultados.appendChild(aviso);
  }

  resultados.classList.add('visible');
  accionesLote.style.display = 'flex';
}
</script>
</body>
</html>
"""


@app.route("/")
@requiere_login
def index():
    return PAGINA_HTML


@app.route("/convertir", methods=["POST"])
def convertir():
    if CONTRASENA and not session.get("autenticado"):
        return jsonify({"error": "Sesión no válida."}), 401

    archivos = request.files.getlist("archivo")
    if not archivos or archivos[0].filename == "":
        return jsonify({"error": "No se recibió ningún archivo."}), 400

    if len(archivos) > MAX_ARCHIVOS_POR_LOTE:
        return jsonify({"error": f"Máximo {MAX_ARCHIVOS_POR_LOTE} archivos por lote."}), 400

    resultados = []
    for archivo in archivos:
        nombre_original = archivo.filename
        _, extension = os.path.splitext(nombre_original)
        ruta_temporal = None
        try:
            with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as tmp:
                ruta_temporal = tmp.name
                archivo.save(ruta_temporal)

            resultado = conversor.convert(ruta_temporal)
            nombre_md = os.path.splitext(nombre_original)[0] + ".md"
            resultados.append({
                "nombre_original": nombre_original,
                "nombre_archivo": nombre_md,
                "markdown": resultado.text_content,
                "error": None,
            })
        except Exception as e:
            resultados.append({
                "nombre_original": nombre_original,
                "nombre_archivo": None,
                "markdown": None,
                "error": f"No se pudo convertir: {e}",
            })
        finally:
            if ruta_temporal and os.path.exists(ruta_temporal):
                os.remove(ruta_temporal)

    return jsonify({"resultados": resultados})


if __name__ == "__main__":
    puerto = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=puerto, debug=False)
