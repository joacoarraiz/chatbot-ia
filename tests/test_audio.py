"""
tests/test_audio.py
Test interactivo de transcripcion de audios.

Uso:
    python tests/test_audio.py <ruta-al-audio>

Ejemplo:
    python tests/test_audio.py audios/mensaje.ogg
    python tests/test_audio.py "C:/Users/PC/Downloads/audio.m4a"

Si no le pasas un archivo, te pregunta por consola.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from functions.audio_tools import transcribir_audio


def main():
    print("=" * 70)
    print("  TONI - Test de transcripcion de audios")
    print("=" * 70)
    print()

    # Obtener el archivo: de argumento o por input
    if len(sys.argv) > 1:
        archivo = sys.argv[1]
    else:
        print("  Pasame la ruta al archivo de audio.")
        print("  Ejemplos:")
        print("    audios/mi_audio.ogg")
        print("    C:/Users/PC/Downloads/grabacion.m4a")
        print()
        archivo = input("  Ruta: ").strip().strip('"').strip("'")
        print()

    if not archivo:
        print("  ERROR: no se paso archivo.")
        return 1

    archivo_path = Path(archivo)

    if not archivo_path.exists():
        print(f"  ERROR: no existe el archivo {archivo_path.resolve()}")
        return 1

    print(f"  Archivo: {archivo_path.resolve()}")
    print(f"  Tamanio: {archivo_path.stat().st_size / 1024:.1f} KB")
    print()
    print("  Transcribiendo con OpenAI...")
    print()

    t0 = time.time()
    resultado = transcribir_audio(archivo_path)
    duracion = time.time() - t0

    if resultado["exito"]:
        print("=" * 70)
        print("  TRANSCRIPCION:")
        print("=" * 70)
        print()
        # Imprimir el texto identado para legibilidad
        for linea in resultado["texto_transcrito"].split("\n"):
            print(f"     {linea}")
        print()
        print("=" * 70)
        print(f"  Modelo:    {resultado['modelo_usado']}")
        print(f"  Tamanio:   {resultado['tamanio_bytes'] / 1024:.1f} KB")
        print(f"  Duracion:  {duracion:.2f}s")
        print("=" * 70)
        print()
        print("  Listo! Si esta transcripcion se viera bien, podes usar este")
        print("  texto como si fuera un mensaje de texto normal del cliente.")
        return 0
    else:
        print("=" * 70)
        print("  ERROR EN LA TRANSCRIPCION")
        print("=" * 70)
        print(f"  Detalle: {resultado.get('error', 'sin detalle')}")
        return 1


if __name__ == "__main__":
    sys.exit(main())