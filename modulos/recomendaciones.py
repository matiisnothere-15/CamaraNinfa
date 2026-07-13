"""Motor de recomendaciones basado en reglas.

Genera consejos segun el estado de las aves. Mas adelante esto puede
reemplazarse o complementarse con un LLM que redacte resumenes diarios.
"""


def generar_recomendaciones(mood, move_status, horas_sin_comer, horas_sin_beber, audio_status):
    """Retorna una lista de recomendaciones (strings) segun las reglas de salud.

    Si todo esta bien, retorna un unico mensaje positivo.
    """
    recs = []

    # --- Alimentacion e hidratacion ---
    if horas_sin_comer >= 8 or horas_sin_beber >= 6:
        recs.append("URGENTE: demasiado tiempo sin comer/beber. Consulta al veterinario.")
    else:
        if horas_sin_comer >= 4:
            recs.append("Varias horas sin comer. Revisa el comedero y observala de cerca.")
        if horas_sin_beber >= 4:
            recs.append("Varias horas sin beber. Revisa que el bebedero tenga agua limpia.")

    # --- Estado de animo ---
    if mood == "Desesperado":
        recs.append("Signos de angustia (gritos + alertas). Revisala pronto; si persiste, veterinario.")
    elif mood == "Estresado":
        recs.append("Se nota estresada (gritos y mucha actividad). Busca la causa: ruidos, visitas, cambios.")

    # --- Letargo: quieta y sin apetito puede indicar enfermedad ---
    if move_status == "Tranquilo" and horas_sin_comer >= 6:
        recs.append("Muy quieta y sin comer: el letargo con falta de apetito puede indicar enfermedad.")

    # --- Todo bien ---
    if not recs:
        recs.append("Todo se ve bien: come, bebe y esta tranquila. Sigue asi!")

    return recs
