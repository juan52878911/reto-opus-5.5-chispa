"""Tests de las fuentes de libre uso y de las PQRS (T1.1c): fixtures inventados, anonimizado con frases inventadas."""
import collections
import tempfile
import unittest
from pathlib import Path

from model.datos import (anonimizar, ciberacoso, clima, goemociones, libres, odio_alia, pqrs_e86p, pqrs_enrutamiento,
                         pqrs_gb9w, pqrs_xtj2, riesgo_suicida, soporte_ti, spam_tanaos, toxicidad_constitucion,
                         toxicidad_protestas, validar)
from model.datos.comun import FuenteAusente

FIX = Path(__file__).resolve().parent.parent / "fixtures"


def por_split(filas):
    return dict(collections.Counter(f["split"] for f in filas))


class Base(unittest.TestCase):
    def convertir(self, mod, fixture=None):
        filas, info = mod.convertir(FIX / (fixture or mod.__name__.rsplit(".", 1)[1]))
        self.assertEqual(validar.errores_conjunto(filas), [])
        self.assertFalse([f for f in filas if not f["uso_comercial"] and f["split"] != "test"])
        return filas, info


class TestFuentesHF(Base):
    def test_odio_alia(self):
        filas, info = self.convertir(odio_alia)
        self.assertEqual(len(filas), 40)  # 41 con un texto repetido
        self.assertEqual(info["duplicados_descartados"], 1)
        humanas = [f for f in filas if f["fuente"].endswith("human-sample")]
        self.assertEqual(len(humanas), 3)
        self.assertEqual({f["split"] for f in humanas}, {"test"})
        # record_4: el LLM dice odio pero los humanos votan 0,0,1 → false, con blanda 1/3
        r4 = next(f for f in humanas if f["texto"].endswith("esos 4, no valen nada."))
        self.assertEqual((r4["etiqueta"], r4["anotadores"]), ("false", 3))
        self.assertAlmostEqual(r4["blanda"]["true"], 1 / 3.0)
        self.assertTrue(all(f["tipo"] == "noul" and f["licencia"] == "cc-by-4.0" for f in filas))
        # etiquetas de LLM con términos propios: pendiente de decisión de Juan → nada comercial, todo a test
        self.assertFalse(any(f["uso_comercial"] for f in filas))
        self.assertEqual({f["split"] for f in filas}, {"test"})

    def test_toxicidad_usa_acuerdo_de_codificadores_y_no_la_columna_consensus(self):
        for mod, n_tot in ((toxicidad_protestas, 30), (toxicidad_constitucion, 30)):
            filas, info = self.convertir(mod)
            self.assertEqual(len(filas), n_tot)  # 32 filas, 2 con desacuerdo
            self.assertEqual(info["desacuerdo_descartadas"], 2)
            # i múltiplo de 3 → ambos codificadores = 1 → tóxico (incluso con consensus = NA)
            self.assertEqual(collections.Counter(f["etiqueta"] for f in filas), {"false": 20, "true": 10})
            self.assertTrue(all(f["anotadores"] == 2 and f["blanda"][f["etiqueta"]] == 1.0 for f in filas))
        filas, _ = toxicidad_protestas.convertir(FIX / "toxicidad_protestas")
        self.assertEqual({f["variedad"] for f in filas}, {"ar", "cl"})

    def test_goemociones_primera_etiqueta_y_splits_de_origen(self):
        filas, info = self.convertir(goemociones)
        self.assertEqual(por_split(filas), {"train": 16, "dev": 3, "test": 3})
        self.assertEqual(len(filas[0]["opciones"]), 28)
        self.assertEqual(set(filas[0]["opciones"]), set(filas[0]["descripciones"]))
        self.assertGreater(info["multietiqueta"], 0)
        # fila 0 de train: labels = [len('train') % 27, 27] → primera etiqueta, no «neutral»
        self.assertEqual(filas[0]["etiqueta"], goemociones.NOMBRES[len("train")])
        self.assertTrue(filas[0]["texto"].startswith("Texto inventado"))  # text_es, no el inglés

    def test_spam_sin_repetidos(self):
        filas, info = self.convertir(spam_tanaos)
        self.assertEqual(len(filas), 30)
        self.assertEqual(info["descartadas_repetidas_o_invalidas"], 1)
        self.assertEqual(len({f["texto"] for f in filas}), 30)

    def test_soporte_ti_idioma_y_categorias(self):
        filas, info = self.convertir(soporte_ti)
        self.assertEqual(len(filas), 24)
        self.assertEqual(len(filas[0]["opciones"]), 7)
        self.assertEqual({f["idioma"] for f in filas}, {"en", "pt", "de", "es"})
        self.assertEqual(soporte_ti.idioma_de("Zugriff auf Netzlaufwerk bitte freigeben"), "de")
        self.assertEqual(soporte_ti.idioma_de("1234"), "en")
        for p in {f["plantilla"] for f in filas}:  # misma plantilla, mismo split
            self.assertEqual(len({f["split"] for f in filas if f["plantilla"] == p}), 1)

    def test_ciberacoso_dedup_entre_conjuntos_y_menciones(self):
        filas, info = self.convertir(ciberacoso)
        self.assertEqual(info["repetidas_descartadas"], 1)
        self.assertEqual(info["sin_etiqueta_valida"], 2)
        self.assertTrue(all(f["idioma"] == "es-CO" for f in filas))
        self.assertFalse([f for f in filas if "@vecino" in f["texto"] or "@amigo" in f["texto"]])
        self.assertTrue(all("author" not in f for f in filas))

    def test_clima_licencia_contradictoria_todo_a_test(self):
        filas, info = self.convertir(clima)
        self.assertEqual(por_split(filas), {"test": 12})  # 18 filas, 6 repetidas entre train y test
        self.assertTrue(all(not f["uso_comercial"] and f["licencia"].startswith("contradictoria") for f in filas))

    def test_riesgo_suicida_no_disponible(self):
        with self.assertRaises(FuenteAusente):
            riesgo_suicida.convertir(FIX / "riesgo_suicida")

    def test_licencia_estricta_ignora_nc_que_no_habla_de_licencia(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "README.md").write_text("---\nlicense: mit\n---\nSpam is non-commercial proselytizing.\n")
            self.assertEqual(libres.licencia_estricta(d, ("mit",), "mit"), ("mit", True))
            (Path(d) / "README.md").write_text("---\nlicense: mit\n---\n## License\nCC-BY-NC 4.0\n")
            self.assertFalse(libres.licencia_estricta(d, ("mit",), "mit")[1])
            (Path(d) / "README.md").write_text("---\nlicense: apache-2.0\n---\nx\n")
            self.assertFalse(libres.licencia_estricta(d, ("mit",), "mit")[1])  # la tarjeta no confirma lo esperado


class TestPQRS(Base):
    def test_gb9w_mapeo_y_licencia_sa(self):
        filas, info = self.convertir(pqrs_gb9w)
        self.assertEqual(len(filas), 24)  # 28 tipos menos 4 felicitaciones; «Agenda tu cita» descartada
        self.assertEqual(info["sin_mapeo_descartadas"], {"agenda tu cita": 1})
        self.assertEqual(collections.Counter(f["etiqueta"] for f in filas)["peticion"], 8)  # «Solicitud de información» → petición
        self.assertEqual(filas[0]["licencia"], "cc-by-sa-4.0")
        self.assertTrue(all(f["uso_comercial"] and f["tarea"] == "pqrs" and f["idioma"] == "es-CO" for f in filas))
        self.assertEqual(filas[0]["opciones"], ["peticion", "queja", "reclamo", "sugerencia", "denuncia", "felicitacion"])

    def test_e86p_descarta_ambiguos(self):
        filas, info = self.convertir(pqrs_e86p)
        self.assertEqual(collections.Counter(f["etiqueta"] for f in filas), {"peticion": 8, "queja": 4, "sugerencia": 4})
        self.assertEqual(info["sin_mapeo_descartadas"], {"queja - reclamo": 4, "entes de control (10)": 4, "(vacio)": 4})

    def test_xtj2_columnas_si_no(self):
        filas, info = self.convertir(pqrs_xtj2)
        self.assertEqual((info["sin_tipo_descartadas"], info["varios_tipos_descartadas"]), (1, 1))
        self.assertEqual(collections.Counter(f["etiqueta"] for f in filas)["felicitacion"], 4)
        # el nombre del peticionario (columna aparte) se enmascara en el resumen
        self.assertTrue(all("Gómez" not in f["texto"] and "Herrera" not in f["texto"] for f in filas))
        self.assertTrue(any("[NOMBRE]" in f["texto"] for f in filas))

    def test_enrutamiento_clases_y_otra(self):
        filas, info = self.convertir(pqrs_enrutamiento)
        self.assertEqual(len(filas), 60)
        self.assertEqual(info["sin_dependencia_descartadas"], 1)
        self.assertIn("otra", filas[0]["opciones"])
        self.assertLessEqual(len(filas[0]["opciones"]), 31)
        self.assertEqual(filas[0]["licencia"], "cc-by-4.0")
        self.assertEqual(set(f["etiqueta"] for f in filas) - set(filas[0]["opciones"]), set())

    def test_ninguna_fila_conserva_datos_personales_del_fixture(self):
        for mod in (pqrs_gb9w, pqrs_e86p, pqrs_xtj2):
            filas, info = self.convertir(mod)
            for f in filas:
                for malo in ("1032456789", "3001234567", "@ejemplo.com", "calle 45", "Pedro", "María Rodríguez", "Luis Herrera", "Ana Torres"):
                    self.assertNotIn(malo.lower(), f["texto"].lower(), mod.__name__)
            if mod is not pqrs_xtj2:  # el texto de xtj2 solo trae nombres
                self.assertTrue({"DOC", "TEL", "CORREO", "DIR"} <= set(info["reemplazos"]), info["reemplazos"])

    def test_test_estratificado_por_tipo(self):
        for mod in (pqrs_gb9w, pqrs_e86p, pqrs_xtj2):
            filas, _ = self.convertir(mod)
            tipos = {f["etiqueta"] for f in filas}
            self.assertEqual({f["etiqueta"] for f in filas if f["split"] == "test"}, tipos, mod.__name__)

    def test_reparto_estratificado_es_estable_y_sin_partir_grupos(self):
        grupos = [("g%d" % i, "a" if i < 30 else "b", 1 + i % 3) for i in range(60)]
        r1, r2 = libres.reparto_estratificado(grupos), libres.reparto_estratificado(list(reversed(grupos)))
        self.assertEqual(r1, r2)
        for estrato in ("a", "b"):
            filas = collections.Counter()
            for c, e, n in grupos:
                if e == estrato:
                    filas[r1[c]] += n
            tot = sum(filas.values())
            self.assertAlmostEqual(filas["test"] / float(tot), 0.1, delta=0.08)
            self.assertAlmostEqual(filas["train"] / float(tot), 0.8, delta=0.12)
        self.assertEqual(libres.reparto_estratificado([("solo", "x", 5)]), {"solo": "train"})


class TestAnonimizar(unittest.TestCase):
    def a(self, texto, **kw):
        return anonimizar.anonimizar(texto, **kw)

    def test_listas_con_al_menos_300_nombres(self):
        self.assertGreaterEqual(anonimizar.N_NOMBRES + anonimizar.N_APELLIDOS, 300)

    def test_correo_telefono_documento_placa_direccion(self):
        t, c = self.a("Escríbame a juan.perez@ejemplo.com o llame al 3001234567; cédula 1.032.456.789; placa ABC123; "
                      "vivo en la carrera 45 # 12-34 apto 302.")
        for malo in ("ejemplo.com", "3001234567", "1.032", "ABC123", "carrera 45", "12-34"):
            self.assertNotIn(malo, t)
        for etq in ("[CORREO]", "[TEL]", "[DOC]", "[PLACA]", "[DIR]"):
            self.assertIn(etq, t)
        self.assertEqual({k: c[k] for k in ("CORREO", "TEL", "DOC", "PLACA", "DIR")}, dict(CORREO=1, TEL=1, DOC=1, PLACA=1, DIR=1))

    def test_telefonos_en_otros_formatos_y_numeros_largos(self):
        t, _ = self.a("Mi teléfono: 604 321 4567, el celular 310-123-4567, radicado 20201234567.")
        self.assertNotRegex(t, r"\d{4}")
        t, _ = self.a("Cédula de ciudadanía No. 52123456 y NIT 900.123.456")
        self.assertNotRegex(t, r"\d{5}")

    def test_no_toca_importes_ni_numeros_cortos(self):
        t, c = self.a("Me cobraron $1.500.000 en 2 cuotas el 15 de marzo; llevo 3 años esperando.")
        self.assertIn("$1.500.000", t)
        self.assertFalse(c)

    def test_nombres_por_disparador(self):
        t, _ = self.a("Atentamente, Pedro Gómez. Habla el señor Rodrigo Pachón sobre mi caso. Me llamo Yamile Uribe.")
        for malo in ("Pedro", "Gómez", "Rodrigo", "Pachón", "Yamile", "Uribe"):
            self.assertNotIn(malo, t)
        self.assertEqual(t.count("[NOMBRE]"), 3)

    def test_nombres_por_lista_incluso_en_mayusculas(self):
        t, _ = self.a("SOLICITO AL SEÑOR LUIS HERRERA REVISAR; hable con María Torres de la oficina")
        self.assertNotIn("HERRERA", t)
        self.assertNotIn("Torres", t)
        self.assertIn("SOLICITO", t)

    def test_no_enmascara_lugares_ni_palabras_corrientes(self):
        t, c = self.a("Hospital San José, barrio Santa Marta; la queja por la mora en el pago y el amparo de tutela.")
        self.assertEqual(t, "Hospital San José, barrio Santa Marta; la queja por la mora en el pago y el amparo de tutela.")
        t, c = self.a("Yo solicito la devolución. Yo Quiero saber el estado.")
        self.assertNotIn("[NOMBRE]", t)

    def test_nombres_extra_de_la_fila(self):
        t, c = self.a("La solicitud de zuleima quintero llegó tarde; QUINTERO insiste.", nombres_extra=["Zuleima Quintero"])
        self.assertNotRegex(t.lower(), r"zuleima|quintero")
        self.assertEqual(t.count("[NOMBRE]"), 2)  # «zuleima quintero» (junto) y «QUINTERO»

    def test_rachas_desconocidas_con_vocabulario(self):
        voc = anonimizar.vocabulario_de(["la alcaldía respondió a la solicitud del vecino", "pedimos copia del contrato"])
        t, _ = self.a("Mi vecino Arnulf Milton Zorrilla hizo la solicitud a la Alcaldía.", vocabulario=voc)
        self.assertNotIn("Arnulf", t)
        self.assertIn("Alcaldía", t)
        t, _ = self.a("Mi vecino Arnulf Milton Zorrilla hizo la solicitud.")  # sin vocabulario no hay regla de rachas
        self.assertIn("Arnulf", t)

    def test_nombres_contiguos_se_funden(self):
        t, c = self.a("Firma: Juan Carlos de la Torres y Ana María Gómez")
        self.assertEqual(c["NOMBRE"], t.count("[NOMBRE]"))
        self.assertNotIn("Torres", t)

    VOC = anonimizar.vocabulario_de([
        "la alcaldía responde a la solicitud del ciudadano que pide la copia del contrato y el certificado",
        "solicito información sobre el trámite y envío cordialmente la firma de la salud del municipio"])

    def test_mayusculas_con_nombre_de_la_lista(self):
        t, _ = self.a("SOLICITO COPIA. ATENTAMENTE: HECTOR FABIO ZULUAGA BEDOYA", vocabulario=self.VOC)
        for malo in ("HECTOR", "ZULUAGA", "BEDOYA"):
            self.assertNotIn(malo, t)
        self.assertIn("SOLICITO COPIA", t)
        t, _ = self.a("PETICION DE LA SEÑORA ROSALBA QUIÑONEZ RAMIREZ SOBRE EL CONTRATO", vocabulario=self.VOC)
        self.assertNotRegex(t, "ROSALBA|QUIÑONEZ|RAMIREZ")
        self.assertIn("SOBRE EL CONTRATO", t)

    def test_tildes_y_minusculas(self):
        t, _ = self.a("habla jerónimo pérez sobre la salud del barrio")
        self.assertNotRegex(t, "(?i)jer[óo]nimo|p[ée]rez")
        t, _ = self.a("ÁNGELA MARÍA NIÑO MUÑOZ pide copia", vocabulario=self.VOC)
        self.assertNotRegex(t, "ÁNGELA|MUÑOZ|NIÑO")
        t, _ = self.a("la mora del pago y la rosa del jardín")  # palabras corrientes sueltas
        self.assertNotIn("[NOMBRE]", t)

    def test_nombres_compuestos(self):
        t, _ = self.a("JUAN CARLOS DE LA TORRES Y MARIA DEL PILAR GARCIA RESTREPO escribieron", vocabulario=self.VOC)
        self.assertNotRegex(t, "JUAN|TORRES|PILAR|GARCIA|RESTREPO")
        self.assertIn("escribieron", t)
        t, _ = self.a("Habla Ana María de Jesús Pardo López", vocabulario=self.VOC)
        self.assertNotRegex(t, "Ana|Jesús|Pardo|López")

    def test_contextos_documento_y_ciudadano(self):
        t, _ = self.a("Yo, Yesenia Cuesta Mena, identificada con C.C. 52.123.456 solicito copia.", vocabulario=self.VOC)
        self.assertNotRegex(t, "Yesenia|Cuesta|Mena|52")
        self.assertIn("solicito copia", t)
        t, _ = self.a("OSCAR LIBREROS PINZON C.C. 79.123.456 SOLICITA CERTIFICADO", vocabulario=self.VOC)
        self.assertNotRegex(t, "OSCAR|LIBREROS|PINZON|79")
        self.assertIn("SOLICITA CERTIFICADO", t)
        t, _ = self.a("El ciudadano WILMER ORTIZ pide ayuda; la ciudadana Zoila Vera también.", vocabulario=self.VOC)
        self.assertNotRegex(t, "WILMER|ORTIZ|Zoila|Vera")
        t, _ = self.a("CORDIALMENTE, MARTHA LUCIA ECHAVARRIA", vocabulario=self.VOC)
        self.assertNotRegex(t, "MARTHA|LUCIA|ECHAVARRIA")

    def test_no_rompe_nombres_de_entidades(self):
        for ent in ("ALCALDÍA DE FLANDES", "SECRETARÍA DE SALUD", "ALCALDÍA MUNICIPAL DE FLANDES",
                    "Hospital San José", "CONCEJO DE PEREIRA", "SANIDAD MILITAR"):
            t, _ = self.a("SOLICITO A LA %s COPIA DEL CONTRATO" % ent, vocabulario=self.VOC)
            self.assertIn(ent, t)
        t, _ = self.a("ENVIADO A SECRETARÍA DE SALUD POR JULIAN ANDRES CASTRO", vocabulario=self.VOC)
        self.assertIn("SECRETARÍA DE SALUD", t)
        self.assertNotRegex(t, "JULIAN|CASTRO")
        t, _ = self.a("ALCALDÍA DE FLANDES JUAN PEREZ", vocabulario=self.VOC)
        self.assertIn("ALCALDÍA DE FLANDES", t)
        self.assertNotRegex(t, "JUAN|PEREZ")

    def test_nombres_pegados_a_una_etiqueta_y_ambiguos(self):
        v = anonimizar.vocabulario_de(["el señor franco habla con la alcaldía", "la luz del barrio y el socorro tardío, gracias"])
        t, _ = self.a("Radicada por la SRA LUZ MARINA DEL SOCORRO ARBOLEDA, solicitud", vocabulario=v)
        self.assertNotRegex(t, "LUZ|MARINA|SOCORRO|ARBOLEDA")
        t, _ = self.a("Sucesión del Sr. Mario NOSSA TELLO Ricaurte, por ello solicito", vocabulario=v)
        self.assertNotRegex(t, "Mario|NOSSA|TELLO|Ricaurte")
        t, _ = self.a("las personas Gloria Pinzón y Mario Franco con CC 12.345.678 que me vendieron", vocabulario=v)
        self.assertNotIn("Franco", t)
        t, _ = self.a("paz y salvo a nombre de osvaldo pinzon zuluaga gracias", vocabulario=v, estricto=v)
        self.assertNotRegex(t, "osvaldo|pinzon|zuluaga")
        self.assertIn("gracias", t)
        t, _ = self.a("la luz del barrio y el socorro tardío", vocabulario=v)
        self.assertNotIn("[NOMBRE]", t)

    def test_firmas_y_apellidos_sueltos_tras_la_etiqueta(self):
        v = anonimizar.vocabulario_de(["solicito copia del recibo", "gracias por la colaboración, quedo atenta", "el predial"])
        t, _ = self.a("Cordial saludo, [NOMBRE] Quintanilla celular 3001234567", vocabulario=v, estricto=v)
        self.assertNotIn("Quintanilla", t)
        t, _ = self.a("renuncia de la señora Elvia [NOMBRE] zapateiro c.c 52123456", vocabulario=v, estricto=v)
        self.assertNotIn("zapateiro", t)
        t, _ = self.a("recibo a nombre de gilma yaneth cc 52123456", vocabulario=v, estricto=v)
        self.assertNotRegex(t, "gilma|yaneth")
        t, _ = self.a("Solicito copia del recibo, gracias por la colaboración QUINTILIANO", vocabulario=v, estricto=v)
        self.assertNotIn("QUINTILIANO", t)
        t, _ = self.a("SOLICITO COPIA DEL RECIBO", vocabulario=v, estricto=v)  # todo en mayúsculas: no es una firma
        self.assertEqual(t, "SOLICITO COPIA DEL RECIBO")

    def test_firmas_sin_mayusculas_y_nombres_pegados(self):
        v = anonimizar.vocabulario_de(["la niña pide el recibo", "por favor gracias", "descuento del impuesto", "la norma general de usos del suelo", "nueva propietaria del predio"])
        t, _ = self.a("pagar con descuento ana elvia chauta martinez nueva propietaria, cc 52123456", vocabulario=v, estricto=v)
        self.assertNotRegex(t, "ana|elvia|chauta|martinez")
        self.assertIn("nueva propietaria", t)
        t, _ = self.a("pagar con descuento ana elvia chaparro", vocabulario=v, estricto=v)
        self.assertNotRegex(t, "ana|elvia|chaparro")
        t, _ = self.a("certificado de la niña danna [NOMBRE] delega", vocabulario=v, estricto=v)
        self.assertNotRegex(t, "danna|delega")
        t, _ = self.a("agradezco su colaboración Eufemia [NOMBRE]", vocabulario=v, estricto=v)
        self.assertNotIn("Eufemia", t)
        t, _ = self.a("conocer la Norma General de Usos del Suelo", vocabulario=v, estricto=v)
        self.assertNotIn("[NOMBRE]", t)

    def test_portadora_dentro_de_una_palabra_no_es_un_rotulo(self):
        v = anonimizar.vocabulario_de(["una transportadora", "el traslado"])
        t, _ = self.a("con una transportadora especialista en trasteos", estricto=v)
        self.assertEqual(t, "con una transportadora especialista en trasteos")

    def test_saludo_con_nombre_propio(self):
        v = anonimizar.vocabulario_de(["buenas tardes, señores de la alcaldía, le envío el recibo"])
        t, _ = self.a("BUENAS TARDES, JANNETH, LE ENVÍO ESTE CORREO", vocabulario=v)
        self.assertNotIn("JANNETH", t)
        t, _ = self.a("Buenas tardes, Alcaldía, le envío el recibo", vocabulario=v)
        self.assertIn("Alcaldía", t)

    def test_vocabulario_con_min_df_ignora_palabras_de_una_sola_fila(self):
        v = anonimizar.vocabulario_de(["pidió osvaldo copia", "pidió copia"], min_df=2)
        self.assertEqual(v, {"pidio", "copia"})

    def test_sospechosas_cuenta_nombres_aparentes_sin_etiquetas(self):
        voc = anonimizar.vocabulario_de(["hola solicito copia"])
        self.assertEqual(anonimizar.sospechosas("Hola, [NOMBRE] pidió copia. Habló Zenobio Querubín.", voc), ["Zenobio", "Querubín"])
        self.assertEqual(anonimizar.sospechosas("Solicito copia del contrato", voc), [])


if __name__ == "__main__":
    unittest.main()
