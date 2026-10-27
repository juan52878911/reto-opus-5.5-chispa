"""MASSIVE es (mteb/amazon_massive_intent): 60 intenciones de asistente, texto en español."""
from .comun import leer_tabla, licencia_fuente, numerar, raiz_hf

REPO = "mteb/amazon_massive_intent"
CORTO = "massive"
# La tarjeta de mteb dice apache-2.0; MASSIVE original es CC-BY-4.0. Ambas permiten uso comercial.
LICENCIAS_OK = ("apache-2.0", "cc-by-4.0")
PREGUNTA = "¿Qué quiere hacer el usuario con el asistente?"
SPLIT_ORIGEN = {"train": "train", "dev": "validation", "test": "test"}

DESCRIPCIONES = {
    "alarm_query": "consultar las alarmas programadas",
    "alarm_remove": "borrar o cancelar una alarma",
    "alarm_set": "poner una alarma o un despertador",
    "audio_volume_down": "bajar el volumen",
    "audio_volume_mute": "silenciar el sonido",
    "audio_volume_other": "ajustar el volumen a un nivel concreto",
    "audio_volume_up": "subir el volumen",
    "calendar_query": "consultar eventos del calendario",
    "calendar_remove": "borrar un evento del calendario",
    "calendar_set": "crear un evento o recordatorio en el calendario",
    "cooking_query": "preguntar sobre cocina o tiempos de cocción",
    "cooking_recipe": "pedir una receta de cocina",
    "datetime_convert": "convertir una hora entre zonas horarias",
    "datetime_query": "preguntar la fecha o la hora",
    "email_addcontact": "añadir un contacto de correo",
    "email_query": "consultar los correos recibidos",
    "email_querycontact": "buscar los datos de un contacto de correo",
    "email_sendemail": "redactar o enviar un correo electrónico",
    "general_greet": "saludar al asistente",
    "general_joke": "pedir un chiste",
    "general_quirky": "conversación general o pregunta curiosa sin tarea concreta",
    "iot_cleaning": "mandar a limpiar al robot aspirador",
    "iot_coffee": "preparar café con la cafetera conectada",
    "iot_hue_lightchange": "cambiar el color de las luces",
    "iot_hue_lightdim": "atenuar las luces",
    "iot_hue_lightoff": "apagar las luces",
    "iot_hue_lighton": "encender las luces",
    "iot_hue_lightup": "aumentar la intensidad de las luces",
    "iot_wemo_off": "apagar un enchufe inteligente",
    "iot_wemo_on": "encender un enchufe inteligente",
    "lists_createoradd": "crear una lista o añadir un elemento a una lista",
    "lists_query": "consultar el contenido de una lista",
    "lists_remove": "quitar un elemento o borrar una lista",
    "music_dislikeness": "decir que no gusta la canción que suena",
    "music_likeness": "decir que gusta la canción que suena",
    "music_query": "preguntar qué canción o artista suena",
    "music_settings": "cambiar ajustes de la música, como repetir o mezclar",
    "news_query": "preguntar por las noticias",
    "play_audiobook": "reproducir un audiolibro",
    "play_game": "jugar a un juego",
    "play_music": "poner música",
    "play_podcasts": "reproducir un pódcast",
    "play_radio": "sintonizar una emisora de radio",
    "qa_currency": "preguntar por el cambio de moneda",
    "qa_definition": "preguntar el significado de una palabra",
    "qa_factoid": "hacer una pregunta de cultura general",
    "qa_maths": "pedir un cálculo matemático",
    "qa_stock": "preguntar por el precio de una acción",
    "recommendation_events": "pedir recomendaciones de eventos",
    "recommendation_locations": "pedir recomendaciones de lugares",
    "recommendation_movies": "pedir recomendaciones de películas",
    "social_post": "publicar en una red social",
    "social_query": "consultar una red social",
    "takeaway_order": "pedir comida a domicilio",
    "takeaway_query": "consultar el estado de un pedido de comida",
    "transport_query": "preguntar por rutas o medios de transporte",
    "transport_taxi": "pedir un taxi o un coche con conductor",
    "transport_ticket": "comprar o consultar billetes de transporte",
    "transport_traffic": "preguntar por el estado del tráfico",
    "weather_query": "preguntar por el tiempo o el pronóstico",
}


def convertir(raiz=None):
    raiz = raiz or raiz_hf(REPO)
    lic, com = licencia_fuente(raiz, LICENCIAS_OK, "apache-2.0 (tarjeta mteb; original CC-BY-4.0)")
    items = []
    for split, carpeta in SPLIT_ORIGEN.items():
        for r in leer_tabla(raiz / carpeta / "es.json.gz"):
            et = r["label_text"]
            if et not in DESCRIPCIONES:
                raise KeyError("MASSIVE: intención sin descripción en español: " + et)
            items.append((split, dict(
                tarea="intencion", tipo="choice", pregunta=PREGUNTA, texto=r["text"],
                opciones=sorted(DESCRIPCIONES), descripciones=DESCRIPCIONES, etiqueta=et, idioma="es",
                fuente="%s %s" % (REPO, carpeta), licencia=lic, uso_comercial=com)))
    filas, desc = numerar(CORTO, items)
    return filas, {"descartadas_nc": desc, "licencia": lic}
