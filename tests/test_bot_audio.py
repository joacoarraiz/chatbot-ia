"""
tests/test_bot_audio.py
Bot completo con audio: transcribe + router + agente especializado.

Uso:
    python tests/test_bot_audio.py <ruta-al-audio>

Ejemplo:
    python tests/test_bot_audio.py audios/prueba.ogg

Si no le pasas archivo, te pregunta por consola.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from functions.audio_tools import transcribir_audio
from agents.router.router import clasificar
from agents.producto.producto import responder as responder_producto
from agents.faq.faq import responder as responder_faq
from agents.cotizacion.cotizacion import responder as responder_cotizacion
from agents.pedido.pedido import responder as responder_pedido
from agents.derivacion.derivacion import responder as responder_derivacion


AGENTES = {
    "producto": responder_producto,
    "faq": responder_faq,
    "cotizacion": responder_cotizacion,
    "pedido": responder_pedido,
    "derivacion": responder_derivacion,
}


def main():
    print("=" * 70)
    print("  TONI - Bot completo CON AUDIO end-to-end")
    print("  Flujo: audio -> transcripcion -> router -> agente -> respuesta")
    print("=" * 70)
    print()

    # Obtener el archivo de audio
    if len(sys.argv) > 1:
        archivo = sys.argv[1]
    else:
        archivo = input("Ruta al audio: ").strip().strip('"').strip("'")

    archivo_path = Path(archivo)
    if not archivo_path.exists():
        print(f"  ERROR: no existe el archivo {archivo_path.resolve()}")
        return 1

    print(f"  Archivo: {archivo_path.resolve()}")
    print(f"  Tamanio: {archivo_path.stat().st_size / 1024:.1f} KB")
    print()

    # ============ PASO 1: TRANSCRIPCION ============
    print("-" * 70)
    print("  PASO 1/3: Transcribiendo audio con OpenAI...")
    print("-" * 70)
    t_transcripcion_start = time.time()
    transcripcion = transcribir_audio(archivo_path)
    t_transcripcion = time.time() - t_transcripcion_start

    if not transcripcion["exito"]:
        print(f"  ERROR transcribiendo: {transcripcion.get('error')}")
        # Fallback: simular respuesta del bot ante audio que no se puede escuchar
        print()
        print("=" * 70)
        print("  Toni responde (mensaje de fallback):")
        print()
        print("     No pude escuchar bien el audio. ¿Me lo escribis como mensaje?")
        print("=" * 70)
        return 1

    mensaje_texto = transcripcion["texto_transcrito"]
    print(f"  Tiempo: {t_transcripcion:.2f}s  |  Modelo: {transcripcion['modelo_usado']}")
    print(f"  Texto transcrito:")
    print(f"     \"{mensaje_texto}\"")
    print()

    # ============ PASO 2: ROUTER ============
    print("-" * 70)
    print("  PASO 2/3: Router clasificando...")
    print("-" * 70)
    t_router_start = time.time()
    clasificacion = clasificar(mensaje_texto, contexto={"origen": "audio"})
    t_router = time.time() - t_router_start

    agente_elegido = clasificacion["agente"]
    intencion = clasificacion["intencion"]
    confianza = clasificacion["confianza"]
    datos_extraidos = clasificacion.get("datos", {})

    print(f"  Tiempo: {t_router:.2f}s")
    print(f"  Agente:    {agente_elegido}")
    print(f"  Intencion: {intencion} (confianza {confianza:.0%})")
    if datos_extraidos:
        print(f"  Datos:     {json.dumps(datos_extraidos, ensure_ascii=False)}")
    print()

    # ============ PASO 3: AGENTE ============
    respuesta_texto = None
    tokens_especialista = 0

    if agente_elegido == "ninguno":
        respuesta_texto = "Hola! En que te puedo ayudar?"
        print("-" * 70)
        print("  PASO 3/3: Sin agente especialista - respuesta directa")
        print("-" * 70)
    elif agente_elegido in AGENTES:
        print("-" * 70)
        print(f"  PASO 3/3: Invocando agente {agente_elegido}...")
        print("-" * 70)
        try:
            t_agente_start = time.time()
            resultado = AGENTES[agente_elegido](
                mensaje_cliente=mensaje_texto,
                contexto={
                    "origen": "audio",
                    "intencion_router": intencion,
                    "datos_router": datos_extraidos,
                },
                verbose=True,
            )
            t_agente = time.time() - t_agente_start
            respuesta_texto = resultado["respuesta_texto"]
            tokens_especialista = resultado["tokens_usados"]
            print(f"  Tiempo agente: {t_agente:.2f}s")
            print(f"  Iteraciones:   {resultado['iteraciones']}")
            print(f"  Tools usadas:  {len(resultado['tools_usadas'])}")
        except Exception as e:
            print(f"  ERROR en agente {agente_elegido}: {e}")
            import traceback
            traceback.print_exc()
            return 1
    else:
        respuesta_texto = f"Agente desconocido: {agente_elegido}"

    # ============ RESPUESTA FINAL ============
    print()
    print("=" * 70)
    print("  Toni responde:")
    print()
    for linea in (respuesta_texto or "").split("\n"):
        print(f"     {linea}")
    print()
    print("=" * 70)

    # Costo estimado
    # Transcripcion: audios cortos ~$0.003 / min, estimemos audio promedio 10s = $0.0005
    tamanio_kb = archivo_path.stat().st_size / 1024
    minutos_estimados = tamanio_kb / 60  # aprox: 60 KB por minuto en OGG
    costo_transcripcion = minutos_estimados * 0.003
    costo_router = 350 * 1.0 / 1_000_000
    costo_agente = tokens_especialista * 10.0 / 1_000_000
    costo_total = costo_transcripcion + costo_router + costo_agente

    print(f"  Costo: transcripcion ${costo_transcripcion:.4f} + "
          f"router ${costo_router:.4f} + "
          f"agente ${costo_agente:.4f} = ${costo_total:.4f}")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())