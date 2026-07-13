import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


class SourceSyntaxTests(unittest.TestCase):
    def test_fuentes_activas_compilan(self):
        rutas = [RAIZ / "main.py"]
        for carpeta in ("app", "modulos", "tools"):
            rutas.extend(sorted((RAIZ / carpeta).rglob("*.py")))

        errores = []
        for ruta in rutas:
            try:
                fuente = ruta.read_text(encoding="utf-8")
                compile(fuente, str(ruta.relative_to(RAIZ)), "exec")
            except (OSError, UnicodeError, SyntaxError) as error:
                errores.append(f"{ruta.relative_to(RAIZ)}: {error}")

        self.assertEqual([], errores, "\n".join(errores))


if __name__ == "__main__":
    unittest.main()
