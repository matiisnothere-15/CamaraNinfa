import unittest

import app.recomendaciones as app_recs
import modulos.recomendaciones as mod_recs
from modulos.recomendaciones import generar_recomendaciones


class RecomendacionesTests(unittest.TestCase):
    def test_estado_normal_entrega_mensaje_positivo(self):
        recomendaciones = generar_recomendaciones(
            "Normal", "Actividad Normal", 1.0, 1.0, "Sonidos"
        )
        self.assertEqual(1, len(recomendaciones))
        self.assertIn("Todo se ve bien", recomendaciones[0])

    def test_falta_de_agua_prolongada_es_urgente(self):
        recomendaciones = generar_recomendaciones(
            "Normal", "Tranquilo", 1.0, 7.0, "Silencio"
        )
        self.assertTrue(any("URGENTE" in recomendacion for recomendacion in recomendaciones))

    def test_motores_de_recomendaciones_unificados_y_fps_eficiente(self):
        import main

        self.assertIs(app_recs.generar, mod_recs.generar)
        self.assertIs(app_recs.generar_recomendaciones, mod_recs.generar_recomendaciones)
        self.assertEqual(20.0, main.FPS_OBJETIVO)


if __name__ == "__main__":
    unittest.main()
