"""
tests/test_bot.py
Bot completo end-to-end (sin WhatsApp, en consola).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

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


def calcular_costo(tokens_router, tokens_especialista):
    return (tokens_router * 1.0 / 1_000_000 +
            tokens_especialista * 10.0 / 1_000_000)


def main():
    print("=" * 70)
    print("  TONI - Bot completo end-to-end (modo consola)")
    print("  Probá cualquier mensaje. El router decide que agente lo atiende.")
    print("  (Ctrl+C para salir)")
    print("=" * 70)
    print()
    print("Ideas para probar:")
    print("  [Producto]   'necesito pastillas para mi gol 2010'")
    print("  [FAQ]        'a que hora abren?'")
    print("  [Cotizacion] 'me llevo 2 pastillas BOSCH'")
    print("  [Derivacion] 'quiero hablar con un vendedor'")
    print("  [Saludo]     'hola'")
    print()

    costo_acumulado = 0.0
    consultas_facturables = 0
    consultas_totales = 0

    while True:
        try:
            mensaje = input("Vos: ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            print()
            print("-" * 70)
            print("  Resumen de la sesion:")
            print("     Consultas totales:      " + str(consultas_totales))
            print("     Consultas facturables:  " + str(consultas_facturables))
            print("     Costo IA acumulado:     $" + format(costo_acumulado, ".4f") + " USD")
            print("-" * 70)
            print("  Hasta luego!")
            break

        if not mensaje:
            continue

        if mensaje.lower() in ("salir", "exit", "quit"):
            continue

        consultas_totales += 1
        t0 = time.time()

        try:
            print()
            print("  [Router clasificando...]")
            t_router_start = time.time()
            clasificacion = clasificar(mensaje)
            t_router = time.time() - t_router_start

            agente_elegido = clasificacion["agente"]
            intencion = clasificacion["intencion"]
            confianza = clasificacion["confianza"]
            datos_extraidos = clasificacion.get("datos", {})
            cuenta_consulta = clasificacion.get("cuenta_como_consulta", True)

            print("     -> Agente:    " + agente_elegido)
            print("     -> Intencion: " + intencion + " (confianza " + format(confianza, ".0%") + ")")
            if datos_extraidos:
                print("     -> Datos:     " + json.dumps(datos_extraidos, ensure_ascii=False))
            print("     -> Tiempo:    " + format(t_router, ".2f") + "s")

            if cuenta_consulta:
                consultas_facturables += 1

        except Exception as e:
            print("\nERROR en el router: " + str(e) + "\n")
            continue

        tokens_router_estimados = 350
        respuesta_texto = None
        tokens_especialista = 0

        if agente_elegido == "ninguno":
            respuesta_texto = "Hola! En que te puedo ayudar?"
            print()
            print("  [Sin agente especialista - respuesta directa]")

        elif agente_elegido in AGENTES:
            print()
            print("  [Invocando agente " + agente_elegido + "...]")
            try:
                t_agente_start = time.time()
                resultado = AGENTES[agente_elegido](
                    mensaje_cliente=mensaje,
                    contexto={
                        "intencion_router": intencion,
                        "datos_router": datos_extraidos,
                    },
                    verbose=True,
                )
                t_agente = time.time() - t_agente_start
                respuesta_texto = resultado["respuesta_texto"]
                tokens_especialista = resultado["tokens_usados"]
                print("     -> Tiempo agente: " + format(t_agente, ".2f") + "s")
                print("     -> Iteraciones:   " + str(resultado["iteraciones"]))
                print("     -> Tools usadas:  " + str(len(resultado["tools_usadas"])))
            except Exception as e:
                print("\nERROR en el agente " + agente_elegido + ": " + str(e) + "\n")
                import traceback
                traceback.print_exc()
                continue
        else:
            respuesta_texto = "Agente desconocido: " + agente_elegido

        costo_consulta = calcular_costo(tokens_router_estimados, tokens_especialista)
        costo_acumulado += costo_consulta
        t_total = time.time() - t0

        print()
        print("=" * 70)
        print("  Toni responde:")
        print()
        for linea in (respuesta_texto or "").split("\n"):
            print("     " + linea)
        print()
        print("-" * 70)
        print("  Tiempo total: " + format(t_total, ".2f") + "s  |  " +
              "Costo: $" + format(costo_consulta, ".4f") + "  |  " +
              "Sesion: " + str(consultas_totales) + " consultas, $" +
              format(costo_acumulado, ".4f"))
        print("=" * 70)
        print()


if __name__ == "__main__":
    main()