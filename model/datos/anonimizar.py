"""Anonimizador de PQRS (T1.1c): reglas + listas de nombres comunes en Colombia, sin red ni modelos.

    texto, cuentas = anonimizar(texto, nombres_extra=())

Reemplaza (en este orden) correos `[CORREO]`, direcciones `[DIR]`, placas `[PLACA]`, teléfonos `[TEL]`,
documentos y números de 6+ dígitos `[DOC]` y nombres de persona `[NOMBRE]`. `cuentas` es un Counter por etiqueta.
`nombres_extra` son nombres conocidos de la fila (p. ej. el campo «peticionario» de la fuente): se enmascaran
en cualquier parte del texto, sin importar mayúsculas.

Los nombres se detectan con (a) listas escritas a mano de nombres y apellidos comunes y (b) una heurística de
mayúsculas tras «señor/a», «me llamo», «yo», «firma»… Los textos en MAYÚSCULAS solo se enmascaran por lista.
"""
import collections
import re
import unicodedata

# Nombres de pila comunes en Colombia (sin acentos, minúsculas). Sin palabras corrientes ambiguas (p. ej. «mora»).
NOMBRES = """
juan jose luis carlos jorge andres david miguel angel pedro pablo diego fernando alejandro daniel santiago
sebastian camilo felipe nicolas mauricio ricardo alberto alfredo alvaro armando arturo augusto bernardo
cesar cristian christian dario edgar edison edwin eduardo efrain eliecer elkin emilio enrique ernesto
esteban eugenio fabian fabio farid fidel francisco gabriel german gilberto gonzalo guillermo gustavo harold
hector henry hernan hernando hugo humberto ivan jaime javier jairo jefferson jesus joaquin john jhon johan
jonathan jhonatan julian julio leonardo leonel libardo lorenzo manuel marcos mario martin mateo nelson
nestor norberto octavio omar oscar osvaldo otoniel rafael ramiro raul reinaldo rene roberto rodolfo rodrigo
rolando ruben salvador samuel saul sergio tomas ulises victor vicente wilmar wilson wilfredo yesid maria ana
luisa carmen rosa sandra claudia patricia martha marta gloria liliana diana paola andrea carolina catalina
natalia viviana adriana alejandra angela beatriz blanca bibiana carmenza cecilia clara constanza cristina
dora doris edith elena elizabeth estella esther eugenia fanny gladys graciela helena herminia irene isabel
jackeline jeanette johana juana judith julieta karen katherine kelly laura leidy lucia lucero luisa lorena
magnolia margarita marcela mariela marisol marlene mary mayra mercedes mildred mireya monica nancy nelly
nidia nora olga omaira paula pilar rocio rosalba rosario ruth sara sofia stella susana tatiana teresa tania
ximena yamile yaneth yeimy yenny yolanda yudy zulma valentina daniela juliana isabella mariana manuela sofia
gabriela mayerli leidy brayan yeison deisy dayana kevin steven stiven duvan wilmer yuliana yurani liceth
nubia aura ligia lilia inés abel abelardo adan adolfo adrian agustin aldemar alexander alexis alirio alonso
amado anderson anibal anselmo antonio argemiro aristides arley aurelio baltazar bayron benjamin bernabe
bladimir brandon braulio calixto cristobal danilo deiby dilan dimas eder elias eliseo emerson evaristo
ezequiel fredy freddy gerardo gerson giovanni giovanny gregorio heriberto hildebrando ismael israel jhony
johnny joel jonny josue ovidio orlando alexandra alicia amalia anyela araceli aracely astrid belen berta
betty brigitte camila carlota celia clemencia concepcion damaris elsa emma erika erica evelyn fabiola
fernanda francia genoveva gisela hilda ingrid ines irma jacqueline jazmin jenny jennifer jessica johanna
jhoana katerine leticia lidia lina lisbeth lucila magaly maribel marina marlon matilde melissa miriam myriam
nohora noemi norma pastora piedad rebeca regina rosalia sonia soledad tulia vanessa vilma wendy yadira
yaritza yazmin yohana zoraida virginia jeronimo angelica geny jenifer yuri yury dolly gina erly nidya
saray shirley stefany stephany lizeth lizbeth marleny nayibe yuly yineth yulieth andrey hermes gildardo ferney
uriel ancizar anyi giovany geovanny yovany geovany
""".split()

# Apellidos comunes en Colombia (sin acentos, minúsculas).
APELLIDOS = """
huerta garcia rodriguez martinez lopez gonzalez gomez hernandez perez sanchez ramirez torres diaz vargas castro
rojas moreno jimenez ortiz gutierrez munoz romero alvarez ruiz suarez mendoza ramos florez cardenas herrera
medina aguirre aguilar acosta angulo arango arbelaez arias avila ayala baquero barrera bedoya benitez
bermudez bernal betancur betancourt bohorquez bolanos bonilla botero buitrago bustamante caballero cabrera
cadavid caicedo calderon camacho cano cardona carrillo carvajal castano castellanos cely cepeda chaparro
cifuentes collazos contreras cordoba correa cortes cortez cuellar cuervo duarte duque duran echeverry
escobar espinosa espitia estrada fajardo forero fuentes gaitan galeano galvis gallego garzon giraldo
granados guerrero guevara guzman henao hoyos henriquez hurtado jaramillo laverde leon lizarazo londono
lozano lugo macias maldonado marin marquez mejia millan molina montoya montes mosquera naranjo narvaez
navarro nieto nunez ocampo ochoa olarte orozco ospina ospino osorio otalora pabon pacheco padilla pardo
parra patino pedraza pena penaloza pineda pinilla pinto posada prada puentes quesada quiceno quintana
quintero quiroga rangel reyes restrepo riano rincon rivas rivera robles rocha rodas roldan rueda saavedra
salamanca salazar salcedo samper sandoval santamaria santana santos sarmiento serna serrano silva solano
soto tafur tamayo tellez trujillo uribe urrego valbuena valderrama valencia valero vanegas vasquez vega
velandia velasco velez venegas vera villamizar villegas zambrano zapata zuluaga zuniga aristizabal barbosa
bautista beltran enciso lara loaiza lemus mahecha mancera mantilla mayorga mojica monsalve monroy murcia
murillo naranjo orjuela oviedo pulido ramon renteria sepulveda toloza tovar triana ulloa urbina useche
vallejo varon villalba yepes zea abella acevedo aldana alfonso almanza andrade anaya aponte arellano arevalo
arteaga avendano bahamon baez ballesteros barragan barros bastidas becerra bejarano bello bernardo bocanegra
borja burbano bustos caceres camargo canizales carreno carreno casallas cassiani castaneda cespedes charry
chavarro chavez cobos corredor cuadros dangond davila diago donado escalante escamilla escudero esquivel
farfan ferrer figueroa fonseca fontalvo galindo gamboa garavito garay garces gaviria godoy 
guarin guio hidalgo higuita hinestroza izquierdo jacome jurado lancheros lasso
ledesma linares lombana loperena lopera lucumi malagon manrique marulanda mazo meneses merchan miranda
molano montanez montenegro morales moya munevar nino noguera nova obando olaya ordonez ortega ovalle pachon
paez palencia pelaez peralta pimentel pinzon portilla pulgarin quijano quintanilla ravelo realpe rengifo
riascos ricaurte rivero robledo rubiano sabogal saenz samudio sanabria santacruz sanz sastoque sosa tabares
tangarife tapias tejada tenorio terreros tobar trochez turriago urbano vacca valdes valenzuela
vallecilla velilla vergara viana vidal villalobos villareal yanguas zabala zarate zorro
arenas castilla riveros ceron cardozo ibarra lozada nossa ardila giron herran neira polania quimbaya salgado
tapia tello ussa vives zamora gil
""".split()

N_NOMBRES = len(set(NOMBRES))
N_APELLIDOS = len(set(APELLIDOS))


def sin_acentos(s):
    t = unicodedata.normalize("NFD", s)
    return "".join(c for c in t if unicodedata.category(c) != "Mn").casefold().replace("ñ", "n")


_NOM = {sin_acentos(x) for x in NOMBRES}
# Nombres que también son palabras corrientes («luz», «socorro»): solo valen junto a un disparador o a otro nombre.
_AMBIGUOS = {"luz", "socorro", "consuelo", "dolores", "amparo", "esperanza", "fatima", "angeles", "remedios", "mora",
             "rosa", "paz", "victoria", "gracia", "pilar", "cielo", "aurora"}
_APE = {sin_acentos(x) for x in APELLIDOS}
_TODOS = _NOM | _APE

# Palabras que preceden a topónimos o instituciones («San José», «Santa Marta», «Hospital Militar»): no son personas.
_NO_PERSONA_ANTES = {"san", "santa", "santo", "calle", "carrera", "avenida", "barrio", "hospital", "colegio",
                     "parque", "plaza", "vereda", "municipio", "alcaldia", "concejo", "fundacion", "clinica",
                     "centro", "instituto", "universidad", "puente", "ciudad", "villa"}
_CONECTORES = {"de", "del", "la", "las", "los", "y", "e"}

# Nombres de entidades («ALCALDÍA DE FLANDES», «SECRETARÍA DE SALUD»): la palabra cabeza protege lo que la sigue.
_CABEZAS_ENTIDAD = {sin_acentos(x) for x in """alcaldia secretaria concejo gobernacion ministerio hospital clinica colegio
institucion instituto universidad personeria contraloria procuraduria defensoria registraduria fiscalia policia ejercito
armada direccion oficina empresa fundacion corporacion departamento municipio unidad superintendencia comisaria
inspeccion juzgado tribunal corte eps ips esp caja cooperativa asociacion junta parroquia iglesia plaza parque
barrio vereda sanidad dispensario ese dian sena icbf""".split()}
_ENTIDAD_PALABRAS = _CABEZAS_ENTIDAD | {"colombia", "colombiano", "colombiana", "bogota", "medellin", "pereira", "cali"}
_ADJ_ENTIDAD = {"municipal", "nacional", "departamental", "distrital", "general", "local", "regional", "publica",
                "publico", "social", "militar", "central", "territorial", "educativa", "educativo"}

# Disparadores: fuertes (siguen nombres propios casi siempre) y débiles (exigen más pruebas).
_FUERTES = ("señor", "señora", "señores", "señorita", "sr", "sra", "srta", "don", "doña", "dr", "dra", "doctor",
            "doctora", "ingeniero", "ingeniera", "ing", "abogado", "abogada", "me llamo", "mi nombre es",
            "mi nombre completo es", "nombre", "a nombre de", "de parte de", "peticionario", "peticionaria",
            "solicitante", "ciudadano", "ciudadana", "usuario", "usuaria", "afiliado", "afiliada", "paciente",
            "madre", "padre", "hijo", "hija", "esposo", "esposa", "hermano", "hermana")
_DEBILES = ("yo", "soy", "firma", "firmado por", "atentamente", "cordialmente", "att", "cc")

_TOK = r"[A-ZÁÉÍÓÚÑÜ][A-Za-zÁÉÍÓÚÑÜáéíóúñü'’]+"
_PALABRA = re.compile(r"[A-Za-zÁÉÍÓÚÑÜáéíóúñü'’]+")


def _re_disparador(lista):
    alt = "|".join(re.escape(x).replace(r"\ ", r"\s+") for x in sorted(lista, key=len, reverse=True))
    return re.compile(r"(?<![\wÁÉÍÓÚÑáéíóúñ])(?:%s)\b\.?[:,]?\s+" % alt, re.I)


_RE_FUERTE = _re_disparador(_FUERTES)
_RE_DEBIL = _re_disparador(_DEBILES)

_RE_CORREO = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_CALLE = (r"(?:calle|cll?|carrera|cra|kra|kr|cr|avenida|av|avda|transversal|trans|tv|diagonal|diag|dg|circular|"
          r"autopista|manzana|mz|vereda)")
_RE_DIR = re.compile(
    r"(?<![\wáéíóú])" + _CALLE + r"\.?\s*#?\s*\d+\s*[A-Za-z]?(?:\s*(?:bis|sur|norte|este|oeste))*"
    r"(?:\s*(?:#|no\.?|nro\.?|n°|nº|con|entre)\s*\d+\s*[A-Za-z]?)?(?:\s*[-–]\s*\d+)*"
    r"(?:\s*(?:casa|apto|apartamento|torre|interior|int|local|piso)\.?\s*\d+[A-Za-z]?)*", re.I)
_RE_NUMERAL = re.compile(r"#\s*\d+\s*[A-Za-z]?(?:\s*[-–]\s*\d+)+")
_RE_PLACA = re.compile(r"(?<![\w])(?:[A-Z]{3}[\s-]?\d{3}|[A-Z]{3}[\s-]?\d{2}[A-Z])(?![\w])")
_RE_TEL_CTX = re.compile(r"((?:tel[ée]fono|tel|cel(?:ular)?|whatsapp|contacto|llamar(?:me)?(?: al)?)\.?:?\s*)"
                         r"(?:\+?57[\s.-]*)?[\d][\d\s.-]{5,14}\d", re.I)
_RE_TEL = re.compile(r"(?<![\d])(?:\+?57[\s.-]?)?(?:3\d{2}[\s.-]?\d{3}[\s.-]?\d{4}|\(?60\d\)?[\s.-]?\d{3}[\s.-]?\d{4}|"
                     r"\d{3}[\s.-]\d{2}[\s.-]\d{2}|\d{3}[\s-]\d{4})(?![\d])")
_RE_DOC_PUNTOS = re.compile(r"(?<![\d$])(?<!\$ )\d{1,3}(?:[.,]\d{3}){2,3}(?![\d])")
_RE_DOC_ROTULO = re.compile(r"((?:c\.?\s?c\.?|c[ée]dula(?: de ciudadan[ií]a)?|nit|t\.?\s?i\.?|pasaporte|documento|identificaci[óo]n)"
                            r"\s*(?:n[°ºo.]*\s*)?[:#]?\s*)\d[\d.\s-]{3,}\d", re.I)
_RE_DOC = re.compile(r"(?<![\d$])(?<!\$ )\d{6,}(?![\d])")


def _pon(cuentas, etiqueta):
    def f(m):
        cuentas[etiqueta] += 1
        return "[%s]" % etiqueta
    return f


def _es_titulo(w):
    return len(w) > 1 and w[0].isupper() and not w.isupper() and w[1:].islower()


def _es_mayus(w):
    return len(w) > 2 and w.isupper()


def _desconocida(w, vocabulario):
    """Palabra de 3+ letras (en cualquier caja) fuera del vocabulario, de las listas y de las entidades."""
    wl = sin_acentos(w)
    return bool(vocabulario) and len(w) > 2 and wl not in vocabulario and wl not in _ENTIDAD_PALABRAS


def _mayus_desconocida(w, vocabulario):
    return bool(vocabulario) and _es_mayus(w) and sin_acentos(w) not in vocabulario and sin_acentos(w) not in _ENTIDAD_PALABRAS


def _hasta_nombre(texto, ini, debil, vocabulario=None, estricto=None):
    """Longitud de la racha de palabras de nombre que empieza en `ini`; 0 si no parece un nombre.

    Con `vocabulario`, una palabra en MAYÚSCULAS fuera de él (y fuera de las listas) también cuenta como parte del nombre.
    `estricto` (vocabulario con `min_df` alto, p. ej. 5) decide qué palabras en minúsculas se suman a un nombre ya empezado."""
    pos, fin, n, listas, titulos, mayus = ini, ini, 0, 0, 0, 0
    while n < 5:
        m = _PALABRA.match(texto, pos)
        if not m:
            break
        w = m.group()
        wl = sin_acentos(w)
        if wl in _CONECTORES and n:
            sig = _PALABRA.match(texto, m.end() + 1) if m.end() < len(texto) else None
            if sig and (_es_titulo(sig.group()) or sin_acentos(sig.group()) in (_TODOS | _AMBIGUOS)
                        or _mayus_desconocida(sig.group(), vocabulario)) and texto[m.end()] == " ":
                pos = m.end() + 1
                continue
            break
        en_lista = wl in _TODOS
        ambiguo = wl in _AMBIGUOS and (w[0].isupper() or n)
        minuscula = w.islower() and (en_lista or (n and _desconocida(w, estricto)) or (n and wl in _AMBIGUOS))
        if not (_es_titulo(w) or (_es_mayus(w) and en_lista) or (en_lista and w[0].isupper())
                or _mayus_desconocida(w, vocabulario) or ambiguo or minuscula):
            break
        en_lista = en_lista or ambiguo
        n += 1
        listas += en_lista
        titulos += _es_titulo(w)
        mayus += not en_lista and _mayus_desconocida(w, vocabulario)
        fin = m.end()
        if m.end() < len(texto) and texto[m.end()] == " ":
            pos = m.end() + 1
        else:
            break
    if not n:
        return 0
    if debil and not (listas or titulos + mayus >= 2):
        return 0
    return fin - ini


def _enmascarar_disparadores(texto, regex, debil, cuentas, vocabulario=None, estricto=None):
    out, i = [], 0
    for m in regex.finditer(texto):
        if m.start() < i:
            continue
        # «la señora de arriba»: solo si el disparador va tras inicio/puntuación o minúscula; igual se mira el nombre
        largo = _hasta_nombre(texto, m.end(), debil, vocabulario, estricto)
        if not largo:
            continue
        out.append(texto[i:m.end()])
        out.append("[NOMBRE]")
        cuentas["NOMBRE"] += 1
        i = m.end() + largo
    out.append(texto[i:])
    return "".join(out)


def _protegidas(toks, texto):
    """Índices de token dentro de nombres de entidad («ALCALDÍA DE FLANDES»): cabeza + conectores + 1-2 palabras."""
    prot = set()
    k = 0
    while k < len(toks):
        if sin_acentos(toks[k].group()) not in _CABEZAS_ENTIDAD:
            k += 1
            continue
        fin, j, cuerpo = k, k + 1, 0
        while j < len(toks) and cuerpo < 2 and texto[toks[j - 1].end():toks[j].start()] == " ":
            w = sin_acentos(toks[j].group())
            if w in _CONECTORES:
                j += 1
                continue
            con_conector = sin_acentos(toks[j - 1].group()) in _CONECTORES
            if w in _ADJ_ENTIDAD:
                fin = j
            elif w in _TODOS and not con_conector and cuerpo:
                break
            elif _es_titulo(toks[j].group()) or toks[j].group().isupper() or con_conector:
                if w in _TODOS and not con_conector:
                    break
                cuerpo += 1
                fin = j
            else:
                break
            j += 1
        prot.update(range(k, fin + 1))
        k = max(fin + 1, k + 1)
    return prot


def _enmascarar_lista(texto, cuentas):
    """Palabras de la lista de nombres/apellidos, sin importar mayúsculas ni tildes; funde rachas contiguas.

    Con inicial mayúscula (o todo mayúsculas) basta una palabra; en minúsculas hacen falta 2 o más seguidas y alguna
    que sea nombre de pila («juan perez»). Los nombres de entidad («Alcaldía de Flandes») no se tocan."""
    toks = list(_PALABRA.finditer(texto))
    prot = _protegidas(toks, texto)
    marcas = []
    for k, m in enumerate(toks):
        if sin_acentos(m.group()) not in _TODOS or k in prot:
            continue
        if k and sin_acentos(toks[k - 1].group()) in _NO_PERSONA_ANTES:
            continue
        marcas.append(k)
    if not marcas:
        return texto
    out, i, k = [], 0, 0
    while k < len(marcas):
        ini, fin = marcas[k], marcas[k]
        grupo = [marcas[k]]
        # une con la siguiente marca si solo las separa un espacio o un conector («de», «del»)
        while k + 1 < len(marcas):
            sig = marcas[k + 1]
            hueco = texto[toks[fin].end():toks[sig].start()]
            entre = [t for t in toks[fin + 1:sig]]
            if sig == fin + 1 and hueco == " " or (
                    sig == fin + 2 and sin_acentos(entre[0].group()) in _CONECTORES and hueco.strip() == entre[0].group()):
                fin = sig
                grupo.append(sig)
                k += 1
            else:
                break
        k += 1
        fuerte = any(toks[g].group()[0].isupper() for g in grupo)
        if not fuerte and not (len(grupo) >= 2 and any(sin_acentos(toks[g].group()) in _NOM for g in grupo)):
            continue
        out.append(texto[i:toks[ini].start()])
        out.append("[NOMBRE]")
        cuentas["NOMBRE"] += 1
        i = toks[fin].end()
    out.append(texto[i:])
    return "".join(out)


def _enmascarar_mayusculas(texto, vocabulario, cuentas):
    """Tramos en MAYÚSCULAS de 2 a 4 palabras con al menos un nombre o apellido de la lista: se enmascaran enteros
    (las vecinas desconocidas son casi siempre el resto del nombre). Sin tocar nombres de entidad."""
    toks = list(_PALABRA.finditer(texto))
    prot = _protegidas(toks, texto)
    out, i, k = [], 0, 0
    while k < len(toks):
        j = k
        while (j < len(toks) and j - k < 4 and j not in prot and len(toks[j].group()) > 1 and toks[j].group().isupper()
               and (j == k or texto[toks[j - 1].end():toks[j].start()] == " ")
               and (sin_acentos(toks[j].group()) in _TODOS
                    or (sin_acentos(toks[j].group()) not in (vocabulario or ()) and sin_acentos(toks[j].group()) not in _ENTIDAD_PALABRAS
                        and len(toks[j].group()) > 2))):
            j += 1
        if j - k >= 2 and any(sin_acentos(toks[x].group()) in _TODOS for x in range(k, j)):
            out.append(texto[i:toks[k].start()])
            out.append("[NOMBRE]")
            cuentas["NOMBRE"] += 1
            i = toks[j - 1].end()
            k = j
        else:
            k += 1
    out.append(texto[i:])
    return "".join(out)


_RE_ANTES_DOC = re.compile(r",?\s*(?:identificad[oa]|portador[a]?|(?:con\s+)?c\.?\s?c\.?\s*(?:n[°ºo.]*\s*)?\[DOC\]|c[ée]dula)", re.I)


def _enmascarar_antes_de_documento(texto, vocabulario, cuentas, estricto=None):
    """El nombre que precede a «identificado con», «C.C. [DOC]» o «cédula»: palabras con inicial mayúscula que son de la
    lista o no aparecen en minúsculas en el corpus, hacia atrás desde el rótulo (hasta 5)."""
    out, i = [], 0
    for m in _RE_ANTES_DOC.finditer(texto):
        toks = [t for t in _PALABRA.finditer(texto, max(i, m.start() - 80), m.start())]
        if not toks or texto[toks[-1].end():m.start()].strip(" "):
            continue
        prot = _protegidas(toks, texto)
        n, j = 0, len(toks)
        while j > 0 and n < 5:
            w = toks[j - 1].group()
            wl = sin_acentos(w)
            minus = w.islower() and n < 3 and (wl in _TODOS or _desconocida(w, estricto))
            ok = minus or w[0].isupper() and (wl in _TODOS or wl not in (vocabulario or ())
                                     or texto[:toks[j - 1].start()].rstrip().endswith("[NOMBRE]"))
            if wl in _CONECTORES and j > 1 and n and texto[toks[j - 2].end():toks[j - 1].start()] == " ":
                j -= 1
                continue
            if not ok or (j - 1) in prot or wl in _ENTIDAD_PALABRAS:
                break
            n += 1
            j -= 1
            if j and texto[toks[j - 1].end():toks[j].start()] != " ":
                break
        while j < len(toks) and sin_acentos(toks[j].group()) in _CONECTORES:
            j += 1
        if n == 0 or j >= len(toks):
            continue
        ini = toks[j].start()
        if ini < i:
            continue
        out.append(texto[i:ini])
        out.append("[NOMBRE]")
        cuentas["NOMBRE"] += 1
        i = toks[-1].end()
    out.append(texto[i:])
    return "".join(out)


def _enmascarar_extra(texto, extra, cuentas):
    for nombre in extra:
        for parte in re.split(r"\s+", (nombre or "").strip()):
            if len(sin_acentos(parte)) < 3 or sin_acentos(parte) in _CONECTORES:
                continue
            patron = re.compile(r"(?<![\wáéíóúñ])" + re.escape(parte) + r"(?![\wáéíóúñ])", re.I)
            texto, n = patron.subn("[NOMBRE]", texto)
            cuentas["NOMBRE"] += n
    return texto


def vocabulario_de(textos, min_df=1):
    """Palabras (sin acentos) que aparecen en minúsculas en `textos`: lo que NO es nombre propio en este corpus.

    Con `min_df` > 1 solo cuentan las que aparecen en ese número de textos distintos: un nombre escrito en minúsculas
    en una sola fila no debe colarse en el vocabulario."""
    df = collections.Counter()
    for t in textos:
        df.update({sin_acentos(w) for w in re.findall(r"(?<![\wÁÉÍÓÚÑ])[a-záéíóúñü]{2,}", t)})
    return {w for w, n in df.items() if n >= min_df}


_LUGARES_INSTITUCIONES = {"colombia", "bogota", "medellin", "antioquia", "tolima", "flandes", "pereira", "risaralda", "cali",
                          "barranquilla", "cartagena", "bucaramanga", "alcaldia", "secretaria", "concejo", "gobernacion",
                          "ministerio", "republica", "nacional", "municipal", "departamento", "instituto", "social"}


def _enmascarar_rachas(texto, vocabulario, cuentas):
    """Rachas de 2 a 4 palabras con inicial mayúscula (no al inicio de frase) que nunca aparecen en minúsculas en el
    corpus y no son lugares ni instituciones corrientes: casi siempre son un nombre y un apellido."""
    toks = list(_PALABRA.finditer(texto))
    prot = _protegidas(toks, texto)
    out, i, k = [], 0, 0
    while k < len(toks):
        j = k
        while (j < len(toks) and j not in prot and _es_titulo(toks[j].group()) and sin_acentos(toks[j].group()) not in vocabulario
               and sin_acentos(toks[j].group()) not in _LUGARES_INSTITUCIONES and j - k < 4
               and (j == k or texto[toks[j - 1].end():toks[j].start()] == " ")):
            j += 1
        if j - k >= 2:
            out.append(texto[i:toks[k].start()])
            out.append("[NOMBRE]")
            cuentas["NOMBRE"] += 1
            i = toks[j - 1].end()
            k = j
        else:
            k += 1
    out.append(texto[i:])
    return "".join(out)


_RE_ENTRE = re.compile(r"\[NOMBRE\]\s+([A-Za-zÁÉÍÓÚÑÜáéíóúñü'’]{3,})\s+\[NOMBRE\]")
_CUE = r"(?:cel|celular|tel|tel[eé]fono|cc|c\.c\.?|c[eé]dula|nit|correo|whatsapp)"
_RE_COLA = re.compile(r"\[NOMBRE\]\s+([A-Za-zÁÉÍÓÚÑÜáéíóúñü'’]{3,})(?=\s*(?:[.,;:]?\s*$|[.,;:]?\s+" + _CUE + r"\b|\s*\[(?:TEL|DOC|CORREO|DIR)\]))",
                      re.I)
_RE_VECINA_DESPUES = re.compile(r"\[NOMBRE\](?:\s+(?:de|del|de la|de los))?\s+([A-Za-zÁÉÍÓÚÑÜáéíóúñü'’]{3,})")
_RE_VECINA_ANTES = re.compile(r"([A-Za-zÁÉÍÓÚÑÜáéíóúñü'’]{3,})\s+(?:(?:de|del|de la|de los)\s+)?\[NOMBRE\]")


def _cola_es_nombre(w, ini, protegidas, vocabulario, con_cue):
    """Palabra tras [NOMBRE] y antes de «cel», «cc», un dato o el final: la firma sigue (apellido). Al final del texto
    solo si empieza con mayúscula (en minúsculas sería una palabra cualquiera)."""
    if ini in protegidas or not (con_cue or w[0].isupper()):
        return False
    return sin_acentos(w) in _TODOS or _desconocida(w, vocabulario)


def _absorber_vecinas(texto, vocabulario):  # `vocabulario`: el estricto (min_df=2) si hay
    """Palabras pegadas a una etiqueta [NOMBRE] que siguen siendo nombre: de la lista (en cualquier caja), de nombres
    ambiguos («Socorro») o con inicial mayúscula y desconocidas («[NOMBRE] MELO»)."""
    def es_nombre(w, ini, entre=False):
        if ini in protegidas:
            return False
        wl = sin_acentos(w)
        if wl in _TODOS or wl in _AMBIGUOS:
            return True
        return entre and w[0].isupper() and _desconocida(w, vocabulario)
    for _ in range(8):
        toks = list(_PALABRA.finditer(texto))
        protegidas = {toks[k].start() for k in _protegidas(toks, texto)}
        nuevo = _RE_ENTRE.sub(lambda m: "[NOMBRE] [NOMBRE]" if es_nombre(m.group(1), m.start(1), True) else m.group(0), texto)
        if nuevo == texto:
            nuevo = _RE_COLA.sub(lambda m: "[NOMBRE]" if _cola_es_nombre(
                m.group(1), m.start(1), protegidas, vocabulario, texto[m.end(1):].strip(" .,;:") != "") else m.group(0), texto)
        if nuevo == texto:
            nuevo = _RE_VECINA_DESPUES.sub(lambda m: "[NOMBRE]" if es_nombre(m.group(1), m.start(1)) else m.group(0), texto)
        if nuevo == texto:  # las posiciones solo valen para el texto sin cambiar
            nuevo = _RE_VECINA_ANTES.sub(lambda m: "[NOMBRE]" if es_nombre(m.group(1), m.start(1)) else m.group(0), texto)
        if nuevo == texto:
            break
        texto = nuevo
    return texto


def _enmascarar_firma_final(texto, vocabulario, cuentas):
    """Texto que acaba en UNA palabra en MAYÚSCULAS desconocida tras una en minúsculas: es la firma («… colaboración RAUQEL»)."""
    m = re.search(r"([A-ZÁÉÍÓÚÑ]{4,})[.\s]*$", texto)
    if not m or not _desconocida(m.group(1), vocabulario):
        return texto
    antes = _PALABRA.findall(texto[:m.start()])
    if not antes or antes[-1].isupper():
        return texto
    cuentas["NOMBRE"] += 1
    return texto[:m.start()] + "[NOMBRE]" + texto[m.end(1):]


def anonimizar(texto, nombres_extra=(), vocabulario=None, estricto=None):
    """(texto anonimizado, Counter de reemplazos por etiqueta).

    Con `vocabulario` (ver `vocabulario_de`) se añade la regla de rachas de 2+ palabras capitalizadas desconocidas."""
    cuentas = collections.Counter()
    t = texto
    t = _RE_CORREO.sub(_pon(cuentas, "CORREO"), t)
    t = _RE_DIR.sub(_pon(cuentas, "DIR"), t)
    t = _RE_NUMERAL.sub(_pon(cuentas, "DIR"), t)
    t = _RE_TEL_CTX.sub(lambda m: (cuentas.update(["TEL"]) or m.group(1) + "[TEL]"), t)
    t = _RE_TEL.sub(_pon(cuentas, "TEL"), t)
    t = _RE_PLACA.sub(_pon(cuentas, "PLACA"), t)
    t = _RE_DOC_ROTULO.sub(lambda m: (cuentas.update(["DOC"]) or m.group(1) + "[DOC]"), t)
    t = _RE_DOC_PUNTOS.sub(_pon(cuentas, "DOC"), t)
    t = _RE_DOC.sub(_pon(cuentas, "DOC"), t)
    t = _enmascarar_extra(t, nombres_extra, cuentas)
    t = _enmascarar_disparadores(t, _RE_FUERTE, False, cuentas, vocabulario, estricto)
    t = _enmascarar_disparadores(t, _RE_DEBIL, True, cuentas, vocabulario, estricto)
    t = _enmascarar_antes_de_documento(t, vocabulario, cuentas, estricto)
    t = _enmascarar_mayusculas(t, vocabulario, cuentas)
    t = _enmascarar_lista(t, cuentas)
    if vocabulario:
        t = _enmascarar_rachas(t, vocabulario, cuentas)
    if vocabulario:
        t = _enmascarar_firma_final(t, vocabulario, cuentas)
    t = _enmascarar_antes_de_documento(t, vocabulario, cuentas, estricto)  # otra vez: ahora las etiquetas ya están puestas
    t = _absorber_vecinas(t, estricto or vocabulario)
    t = re.sub(r"\[NOMBRE\](?:\s+(?:(?:de|del|la|los|y)\s+)?\[NOMBRE\])+", "[NOMBRE]", t)
    if cuentas["NOMBRE"]:
        cuentas["NOMBRE"] = t.count("[NOMBRE]")
    return t, cuentas


# --- informe -------------------------------------------------------------------------------------------------

_ETIQ = re.compile(r"\[(?:NOMBRE|DOC|TEL|CORREO|DIR|PLACA)\]")


def sospechosas(texto, vocabulario):
    """Palabras que aún parecen un nombre propio tras anonimizar: con inicial mayúscula (no al inicio de frase) o
    en MAYÚSCULAS, de 3+ letras y cuya forma en minúsculas no está en `vocabulario` (conjunto de palabras sin acentos).
    """
    t = _ETIQ.sub(" ", texto)
    out = []
    ini = True
    for m in _PALABRA.finditer(t):
        w = m.group()
        previo = t[:m.start()].rstrip()
        ini = (not previo) or previo[-1] in ".!?:;\n"
        if len(w) >= 3 and w[0].isupper() and not ini and sin_acentos(w) not in vocabulario:
            out.append(w)
        elif len(w) >= 4 and _es_mayus(w) and sin_acentos(w) not in vocabulario:
            out.append(w)
    return out
