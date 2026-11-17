"""Motor unificado de recomendaciones basado en reglas del Monitor de Ninfas.

Analiza los datos recientes (snapshots, comidas, ánimo) para el panel web y
evalúa el estado instantáneo para el HUD de OpenCV con los mismos umbrales:

- "bien"     → todo en orden, mensaje positivo
- "info"     → avisos neutros (ej: el monitor está apagado)
- "atencion" → algo que conviene vigilar
- "urgente"  → señales de problema; se sugiere veterinario
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# Umbrales compartidos (horas / valores)
HORAS_SIN_COMER_ATENCION = 4
HORAS_SIN_COMER_URGENTE = 8
HORAS_SIN_BEBER_ATENCION = 4
HORAS_SIN_BEBER_URGENTE = 6
MINUTOS_MONITOR_APAGADO = 30
ACTIVIDAD_LETARGO = 5.0  # porcentaje de la diagonal/min considerado letargo
FRACCION_ESTRES_DIA = 0.25


def _nombres(aves):
    """'tus ninfas' o 'Mushu y Yukki' según lo registrado."""
    nombres = [a["nombre"] for a in aves]
    if not nombres:
        return "tus ninfas"
    if len(nombres) == 1:
        return nombres[0]
    return ", ".join(nombres[:-1]) + " y " + nombres[-1]


def generar(estado, snapshots, acciones, aves, ahora=None):
    """Retorna la lista de recomendaciones estructuradas para el panel y el agente.

    estado:    dict {metrica: {valor, estado, fecha(datetime utc)}}
    snapshots: lista de {fecha(datetime utc), metrica, valor, estado} (24h)
    acciones:  lista de {fecha, accion, estado} (24h)
    aves:      lista de {nombre, ...}
    """
    ahora = ahora or datetime.now(timezone.utc)
    recs = []
    quien = _nombres(aves)

    # ---- 0. ¿Hay datos? ¿El monitor está encendido? ----
    if not estado:
        return [
            {
                "nivel": "info",
                "titulo": "Sin datos todavía",
                "detalle": (
                    "Ejecuta el monitor (python main.py) para que la IA empiece a "
                    f"observar a {quien} y pueda darte recomendaciones."
                ),
            }
        ]

    ultima_fecha = max(m["fecha"] for m in estado.values())
    monitor_activo = (ahora - ultima_fecha) <= timedelta(
        minutes=MINUTOS_MONITOR_APAGADO
    )
    if not monitor_activo:
        recs.append(
            {
                "nivel": "info",
                "titulo": "Monitor apagado",
                "detalle": (
                    "El último dato es de hace un buen rato. Las recomendaciones se "
                    "basan en lo último observado; enciende el monitor para datos al día."
                ),
            }
        )

    hay_problema = False

    # ---- 1. Comida y agua (solo confiable con el monitor encendido) ----
    if monitor_activo:
        comer = estado.get("SinComer")
        if comer:
            h = comer["valor"]
            if h >= HORAS_SIN_COMER_URGENTE:
                hay_problema = True
                recs.append(
                    {
                        "nivel": "urgente",
                        "titulo": f"{h:.0f} horas sin comer",
                        "detalle": (
                            "Un ave que no come en tanto tiempo puede estar enferma — "
                            "las ninfas ocultan sus síntomas. Revisa que haya comida "
                            "fresca y, si sigue sin comer, consulta al veterinario hoy."
                        ),
                    }
                )
            elif h >= HORAS_SIN_COMER_ATENCION:
                hay_problema = True
                recs.append(
                    {
                        "nivel": "atencion",
                        "titulo": f"{h:.1f} horas sin comer",
                        "detalle": (
                            "Revisa el comedero: ¿tiene comida fresca y accesible? "
                            "Obsérvalas de cerca en la próxima hora."
                        ),
                    }
                )

        beber = estado.get("SinBeber")
        if beber:
            h = beber["valor"]
            if h >= HORAS_SIN_BEBER_URGENTE:
                hay_problema = True
                recs.append(
                    {
                        "nivel": "urgente",
                        "titulo": f"{h:.0f} horas sin beber agua",
                        "detalle": (
                            "La deshidratación es peligrosa y rápida en aves pequeñas. "
                            "Cambia el agua por agua limpia y fresca ahora; si no bebe "
                            "en las próximas horas, consulta al veterinario."
                        ),
                    }
                )
            elif h >= HORAS_SIN_BEBER_ATENCION:
                hay_problema = True
                recs.append(
                    {
                        "nivel": "atencion",
                        "titulo": f"{h:.1f} horas sin beber agua",
                        "detalle": (
                            "Revisa el bebedero: agua limpia, sin suciedad y a su alcance. "
                            "En días calurosos esto es especialmente importante."
                        ),
                    }
                )

    # ---- 2. Estado de ánimo ----
    animo = estado.get("EstadoAnimo")
    if monitor_activo and animo:
        if animo["estado"] == "Desesperado":
            hay_problema = True
            recs.append(
                {
                    "nivel": "urgente",
                    "titulo": "Señales de angustia ahora mismo",
                    "detalle": (
                        "Gritos constantes combinados con alertas de salud. Ve a verlas "
                        "ahora: revisa si algo las asusta (otro animal, ruido, objeto "
                        "nuevo) y si tienen comida y agua."
                    ),
                }
            )
        elif animo["estado"] == "Estresado":
            hay_problema = True
            recs.append(
                {
                    "nivel": "atencion",
                    "titulo": "Estrés en este momento",
                    "detalle": (
                        "Mucho ruido y actividad agitada. Causas comunes: ruidos fuertes, "
                        "cambios en el entorno, visitas u otros animales. Dales un rato "
                        "de calma."
                    ),
                }
            )

    animos_dia = [s for s in snapshots if s["metrica"] == "EstadoAnimo"]
    if len(animos_dia) >= 6:
        estresados = [
            s for s in animos_dia if s["estado"] in ("Estresado", "Desesperado")
        ]
        fraccion = len(estresados) / len(animos_dia)
        if fraccion >= FRACCION_ESTRES_DIA:
            hay_problema = True
            recs.append(
                {
                    "nivel": "atencion",
                    "titulo": "Día más estresante de lo normal",
                    "detalle": (
                        f"El {fraccion * 100:.0f}% del día mostraron señales de estrés. "
                        "Piensa qué cambió hoy en su entorno (ruidos, movimiento, luz) "
                        "e intenta reducirlo."
                    ),
                }
            )

    # ---- 3. Letargo (actividad muy baja sostenida) ----
    if monitor_activo:
        hace_2h = ahora - timedelta(hours=2)
        actividad_2h = [
            s["valor"]
            for s in snapshots
            if s["metrica"] == "Actividad" and s["fecha"] >= hace_2h
        ]
        if len(actividad_2h) >= 3:
            promedio = sum(actividad_2h) / len(actividad_2h)
            if promedio < ACTIVIDAD_LETARGO:
                hay_problema = True
                recs.append(
                    {
                        "nivel": "atencion",
                        "titulo": "Actividad muy baja en las últimas horas",
                        "detalle": (
                            "El letargo sostenido puede ser señal de enfermedad en aves "
                            "(plumas infladas, ojos cerrados, en el fondo de la jaula). "
                            "Si además no come o se ve decaída, consulta al veterinario."
                        ),
                    }
                )

    # ---- 4. Resumen positivo ----
    comidas = [
        a
        for a in acciones
        if a["accion"] == "Alimentacion" and a["estado"] in ("Fin", "Activo")
    ]
    bebidas = [
        a
        for a in acciones
        if a["accion"] == "Hidratacion" and a["estado"] in ("Fin", "Activo")
    ]

    if not hay_problema:
        partes = []
        if comidas:
            partes.append(
                f"comieron {len(comidas)} {'vez' if len(comidas) == 1 else 'veces'}"
            )
        if bebidas:
            partes.append(
                f"bebieron agua {len(bebidas)} {'vez' if len(bebidas) == 1 else 'veces'}"
            )
        resumen = (
            f"En las últimas 24 horas {quien} " + " y ".join(partes) + "."
            if partes
            else ""
        )
        recs.append(
            {
                "nivel": "bien",
                "titulo": "¡Todo se ve bien! 🎉",
                "detalle": (
                    resumen
                    + " Ánimo tranquilo y sin alertas de salud. "
                    "¡Sigue así, lo estás haciendo genial!"
                ).strip(),
            }
        )

    orden = {"urgente": 0, "atencion": 1, "info": 2, "bien": 3}
    recs.sort(key=lambda r: orden[r["nivel"]])
    return recs


def generar_recomendaciones(
    mood, move_status, horas_sin_comer, horas_sin_beber, audio_status
):
    """Retorna recomendaciones concisas (strings) para el HUD usando los mismos umbrales."""
    del audio_status
    recs = []

    if (
        horas_sin_comer >= HORAS_SIN_COMER_URGENTE
        or horas_sin_beber >= HORAS_SIN_BEBER_URGENTE
    ):
        recs.append(
            "URGENTE: demasiado tiempo sin comer/beber. Consulta al veterinario."
        )
    else:
        if horas_sin_comer >= HORAS_SIN_COMER_ATENCION:
            recs.append(
                "Varias horas sin comer. Revisa el comedero y observala de cerca."
            )
        if horas_sin_beber >= HORAS_SIN_BEBER_ATENCION:
            recs.append(
                "Varias horas sin beber. Revisa que el bebedero tenga agua limpia."
            )

    if mood == "Desesperado":
        recs.append(
            "Signos de angustia (gritos + alertas). Revisala pronto; si persiste, veterinario."
        )
    elif mood == "Estresado":
        recs.append(
            "Se nota estresada (gritos y mucha actividad). Busca la causa: ruidos, visitas, cambios."
        )

    if move_status == "Tranquilo" and horas_sin_comer >= 6:
        recs.append(
            "Muy quieta y sin comer: el letargo con falta de apetito puede indicar enfermedad."
        )

    if not recs:
        recs.append("Todo se ve bien: come, bebe y esta tranquila. Sigue asi!")

    return recs
