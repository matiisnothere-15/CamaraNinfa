import unittest

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


if __name__ == "__main__":
    unittest.main()
