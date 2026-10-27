"""CLINC150 (clinc/clinc_oos): 150 intenciones en 10 dominios y `oos` -> `escalate`. Texto en inglés.

Formatos documentados: HF `plus/{train,validation,test}-*.parquet` con `text,intent` (intent entero, nombres
en la tarjeta o ya en texto) o el `data_full.json` original (`train/val/test` y `oos_train/oos_val/oos_test`
con pares `[texto, intención]`).
"""
from pathlib import Path

from .comun import etiqueta_de, leer_split, leer_tabla, licencia_fuente, nombres_de_clase, numerar, raiz_hf

REPO = "clinc/clinc_oos"
CORTO = "clinc150"
LICENCIAS_OK = ("cc-by-3.0",)
PREGUNTA = "¿Qué quiere el usuario del asistente?"
ESCALATE = "escalate"

DESCRIPCIONES = {
    # banca
    "transfer": "hacer una transferencia entre cuentas", "transactions": "ver los últimos movimientos de la cuenta",
    "balance": "consultar el saldo", "freeze_account": "congelar o bloquear la cuenta",
    "pay_bill": "pagar una factura", "bill_balance": "consultar el importe de una factura",
    "bill_due": "consultar cuándo vence una factura", "interest_rate": "preguntar por el tipo de interés",
    "routing": "pedir el número de ruta bancaria", "min_payment": "consultar el pago mínimo",
    "order_checks": "pedir un talonario de cheques", "pin_change": "cambiar el PIN",
    "report_fraud": "denunciar un fraude", "account_blocked": "preguntar por qué la cuenta está bloqueada",
    "spending_history": "ver el historial de gastos",
    # tarjetas de crédito
    "credit_score": "consultar la puntuación de crédito", "report_lost_card": "informar de una tarjeta perdida",
    "credit_limit": "consultar el límite de crédito", "rewards_balance": "consultar los puntos de recompensa",
    "new_card": "solicitar una tarjeta nueva", "application_status": "estado de una solicitud de tarjeta",
    "card_declined": "preguntar por qué se rechazó la tarjeta", "international_fees": "comisiones por uso en el extranjero",
    "apr": "preguntar por la TAE de la tarjeta", "redeem_rewards": "canjear puntos de recompensa",
    "credit_limit_change": "pedir un cambio del límite de crédito", "damaged_card": "tarjeta dañada",
    "replacement_card_duration": "plazo de entrega de una tarjeta de reemplazo",
    "improve_credit_score": "cómo mejorar la puntuación de crédito", "expiration_date": "fecha de caducidad de la tarjeta",
    # cocina y restaurantes
    "recipe": "pedir una receta", "restaurant_reviews": "ver reseñas de un restaurante",
    "calories": "preguntar las calorías de un alimento", "nutrition_info": "información nutricional",
    "restaurant_suggestion": "pedir sugerencias de restaurantes", "ingredients_list": "lista de ingredientes de un plato",
    "ingredient_substitution": "sustituir un ingrediente", "cook_time": "tiempo de cocción",
    "food_last": "cuánto dura un alimento antes de estropearse", "meal_suggestion": "pedir sugerencias de comida",
    "restaurant_reservation": "reservar mesa en un restaurante", "confirm_reservation": "confirmar una reserva",
    "how_busy": "preguntar cuánta gente hay en un restaurante", "cancel_reservation": "cancelar una reserva",
    "accept_reservations": "preguntar si un restaurante admite reservas",
    # coche y trayectos
    "current_location": "preguntar la ubicación actual", "oil_change_when": "cuándo cambiar el aceite",
    "oil_change_how": "cómo cambiar el aceite", "uber": "pedir un coche con conductor",
    "traffic": "estado del tráfico", "tire_pressure": "presión de los neumáticos",
    "schedule_maintenance": "programar el mantenimiento del coche", "gas": "nivel de combustible o gasolineras cercanas",
    "mpg": "consumo de combustible del coche", "distance": "distancia hasta un lugar",
    "directions": "pedir indicaciones para llegar", "last_maintenance": "fecha del último mantenimiento",
    "gas_type": "tipo de combustible que usa el coche", "tire_change": "cómo cambiar un neumático",
    "jump_start": "cómo arrancar el coche con pinzas",
    # viajes
    "plug_type": "tipo de enchufe en otro país", "travel_notification": "avisar al banco de un viaje",
    "translate": "traducir una frase a otro idioma", "flight_status": "estado de un vuelo",
    "international_visa": "requisitos de visado", "timezone": "zona horaria de un lugar",
    "exchange_rate": "tipo de cambio entre monedas", "travel_suggestion": "sugerencias de viaje",
    "travel_alert": "alertas de seguridad de un destino", "vaccines": "vacunas necesarias para viajar",
    "lost_luggage": "equipaje perdido", "book_flight": "reservar un vuelo", "book_hotel": "reservar un hotel",
    "carry_on": "equipaje de mano permitido", "car_rental": "alquilar un coche",
    # hogar
    "shopping_list": "consultar la lista de la compra", "shopping_list_update": "modificar la lista de la compra",
    "next_song": "pasar a la siguiente canción", "play_music": "poner música",
    "update_playlist": "modificar una lista de reproducción", "todo_list": "consultar la lista de tareas",
    "todo_list_update": "modificar la lista de tareas", "calendar": "consultar el calendario",
    "calendar_update": "modificar el calendario", "what_song": "preguntar qué canción suena",
    "order": "hacer un pedido", "order_status": "estado de un pedido", "reminder": "consultar un recordatorio",
    "reminder_update": "crear o modificar un recordatorio", "smart_home": "controlar un dispositivo del hogar inteligente",
    # utilidades
    "alarm": "gestionar una alarma", "flip_coin": "lanzar una moneda", "spelling": "deletrear una palabra",
    "time": "preguntar la hora", "timer": "poner un temporizador",
    "measurement_conversion": "convertir unidades de medida", "date": "preguntar la fecha",
    "calculator": "hacer un cálculo", "definition": "definición de una palabra",
    "find_phone": "encontrar el teléfono", "make_call": "hacer una llamada", "text": "enviar un mensaje de texto",
    "share_location": "compartir la ubicación", "weather": "preguntar por el tiempo", "roll_dice": "lanzar un dado",
    # trabajo
    "direct_deposit": "datos del ingreso de la nómina", "pto_request": "solicitar días libres",
    "taxes": "preguntar por los impuestos retenidos", "payday": "cuándo se cobra", "w2": "pedir el certificado de retenciones",
    "pto_balance": "saldo de días libres", "pto_request_status": "estado de una solicitud de días libres",
    "next_holiday": "próximo día festivo", "insurance": "información del seguro médico",
    "insurance_change": "cambiar el seguro médico", "schedule_meeting": "programar una reunión",
    "pto_used": "días libres ya usados", "meeting_schedule": "consultar las reuniones programadas",
    "rollover_401k": "traspasar un plan de pensiones", "income": "consultar el salario",
    # meta (control del asistente)
    "change_accent": "cambiar el acento del asistente", "change_user_name": "cambiar el nombre del usuario",
    "change_language": "cambiar el idioma", "user_name": "preguntar cómo llama el asistente al usuario",
    "cancel": "cancelar lo que se está haciendo", "whisper_mode": "activar o desactivar el modo susurro",
    "yes": "responder que sí", "no": "responder que no", "repeat": "repetir lo último que dijo el asistente",
    "change_volume": "cambiar el volumen", "change_ai_name": "cambiar el nombre del asistente",
    "sync_device": "sincronizar un dispositivo", "maybe": "responder que quizá",
    "reset_settings": "restablecer los ajustes", "change_speed": "cambiar la velocidad de habla",
    # charla
    "greeting": "saludar", "goodbye": "despedirse", "tell_joke": "pedir un chiste",
    "where_are_you_from": "preguntar de dónde es el asistente", "how_old_are_you": "preguntar la edad del asistente",
    "what_is_your_name": "preguntar el nombre del asistente", "who_made_you": "preguntar quién creó al asistente",
    "thank_you": "dar las gracias", "what_can_i_ask_you": "preguntar qué se le puede pedir al asistente",
    "what_are_your_hobbies": "preguntar las aficiones del asistente", "do_you_have_pets": "preguntar si el asistente tiene mascotas",
    "are_you_a_bot": "preguntar si es una máquina", "meaning_of_life": "preguntar el sentido de la vida",
    "who_do_you_work_for": "preguntar para quién trabaja el asistente", "fun_fact": "pedir un dato curioso",
}
DESCRIPCIONES_TODAS = dict(DESCRIPCIONES)
DESCRIPCIONES_TODAS[ESCALATE] = "fuera de ámbito: no es ninguna de las anteriores, pasa a una persona"


def _filas_origen(raiz, origen):
    """[(texto, etiqueta-de-clinc)] de un split original, en cualquiera de los dos formatos."""
    json_full = Path(raiz) / "data_full.json"
    if json_full.is_file():
        d = leer_tabla(json_full)
        clave = {"train": "train", "validation": "val", "test": "test"}[origen]
        return [tuple(p) for p in d[clave] + d["oos_" + clave]], "data_full.json"
    sub = "plus" if (Path(raiz) / "plus").is_dir() else ""
    nombres = nombres_de_clase(raiz, "intent")
    return [(r["text"], etiqueta_de(r, nombres)) for r in leer_split(raiz, {"validation": "dev"}.get(origen, origen), sub)], sub or "."


def convertir(raiz=None):
    raiz = raiz or raiz_hf(REPO)
    lic, com = licencia_fuente(raiz, LICENCIAS_OK, "cc-by-3.0")
    opciones = sorted(DESCRIPCIONES) + [ESCALATE]
    items = []
    for split, origen in (("train", "train"), ("dev", "validation"), ("test", "test")):
        pares, _ = _filas_origen(raiz, origen)
        for texto, et in pares:
            et = ESCALATE if et == "oos" else et
            if et not in DESCRIPCIONES_TODAS:
                raise KeyError("CLINC150: intención sin descripción en español: " + et)
            items.append((split, dict(
                tarea="intencion", tipo="choice", pregunta=PREGUNTA, texto=texto, opciones=opciones,
                descripciones=DESCRIPCIONES_TODAS, etiqueta=et, idioma="en",
                fuente="%s %s" % (REPO, origen), licencia=lic, uso_comercial=com)))
    filas, desc = numerar(CORTO, items)
    return filas, {"descartadas_nc": desc, "licencia": lic}
