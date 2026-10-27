"""Banking77 (PolyAI/banking77): 77 intenciones bancarias, texto en inglés, descripciones en español.

Formato documentado: `train.csv`/`test.csv` con `text,category` (PolyAI) o parquet con `text,label`
(label entero, nombres en la tarjeta). Solo trae train y test: `dev` sale del 10 % de train por hash del texto.
"""
from .comun import etiqueta_de, leer_split, licencia_fuente, nombres_de_clase, numerar, raiz_hf, split_por_clave

REPO = "PolyAI/banking77"
CORTO = "banking77"
LICENCIAS_OK = ("cc-by-4.0",)
PREGUNTA = "¿Qué necesita el cliente del banco?"

DESCRIPCIONES = {
    "activate_my_card": "activar una tarjeta nueva",
    "age_limit": "edad mínima para abrir una cuenta",
    "apple_pay_or_google_pay": "usar Apple Pay o Google Pay",
    "atm_support": "cajeros automáticos compatibles",
    "automatic_top_up": "recarga automática de la cuenta",
    "balance_not_updated_after_bank_transfer": "el saldo no se actualiza tras una transferencia bancaria",
    "balance_not_updated_after_cheque_or_cash_deposit": "el saldo no se actualiza tras ingresar un cheque o efectivo",
    "beneficiary_not_allowed": "el beneficiario no está permitido en una transferencia",
    "cancel_transfer": "cancelar una transferencia",
    "card_about_to_expire": "la tarjeta está a punto de caducar",
    "card_acceptance": "dónde se acepta la tarjeta",
    "card_arrival": "seguimiento de la llegada de una tarjeta",
    "card_delivery_estimate": "plazo estimado de entrega de la tarjeta",
    "card_linking": "vincular una tarjeta existente a la cuenta",
    "card_not_working": "la tarjeta no funciona",
    "card_payment_fee_charged": "comisión cobrada en un pago con tarjeta",
    "card_payment_not_recognised": "pago con tarjeta que el cliente no reconoce",
    "card_payment_wrong_exchange_rate": "tipo de cambio incorrecto en un pago con tarjeta",
    "card_swallowed": "el cajero se tragó la tarjeta",
    "cash_withdrawal_charge": "comisión por retirar efectivo",
    "cash_withdrawal_not_recognised": "retirada de efectivo que el cliente no reconoce",
    "change_pin": "cambiar el PIN de la tarjeta",
    "compromised_card": "tarjeta comprometida o con uso sospechoso",
    "contactless_not_working": "el pago sin contacto no funciona",
    "country_support": "países en los que está disponible el servicio",
    "declined_card_payment": "pago con tarjeta rechazado",
    "declined_cash_withdrawal": "retirada de efectivo rechazada",
    "declined_transfer": "transferencia rechazada",
    "direct_debit_payment_not_recognised": "domiciliación que el cliente no reconoce",
    "disposable_card_limits": "límites de las tarjetas desechables",
    "edit_personal_details": "modificar los datos personales",
    "exchange_charge": "comisión por cambio de divisa",
    "exchange_rate": "consultar el tipo de cambio",
    "exchange_via_app": "cambiar divisas desde la aplicación",
    "extra_charge_on_statement": "cargo extra en el extracto",
    "failed_transfer": "transferencia fallida",
    "fiat_currency_support": "monedas tradicionales admitidas",
    "get_disposable_virtual_card": "obtener una tarjeta virtual desechable",
    "get_physical_card": "obtener una tarjeta física",
    "getting_spare_card": "conseguir una tarjeta adicional",
    "getting_virtual_card": "conseguir una tarjeta virtual",
    "lost_or_stolen_card": "tarjeta perdida o robada",
    "lost_or_stolen_phone": "teléfono perdido o robado",
    "order_physical_card": "pedir una tarjeta física",
    "passcode_forgotten": "olvidó la contraseña o código de acceso",
    "pending_card_payment": "pago con tarjeta pendiente",
    "pending_cash_withdrawal": "retirada de efectivo pendiente",
    "pending_top_up": "recarga pendiente",
    "pending_transfer": "transferencia pendiente",
    "pin_blocked": "PIN bloqueado",
    "receiving_money": "recibir dinero en la cuenta",
    "refund_not_showing_up": "el reembolso no aparece",
    "request_refund": "solicitar un reembolso",
    "reverted_card_payment?": "pago con tarjeta revertido",
    "supported_cards_and_currencies": "tarjetas y monedas admitidas",
    "terminate_account": "cerrar la cuenta",
    "top_up_by_bank_transfer_charge": "comisión al recargar por transferencia bancaria",
    "top_up_by_card_charge": "comisión al recargar con tarjeta",
    "top_up_by_cash_or_cheque": "recargar con efectivo o cheque",
    "top_up_failed": "la recarga falló",
    "top_up_limits": "límites de recarga",
    "top_up_reverted": "recarga revertida",
    "topping_up_by_card": "recargar la cuenta con tarjeta",
    "transaction_charged_twice": "operación cobrada dos veces",
    "transfer_fee_charged": "comisión cobrada en una transferencia",
    "transfer_into_account": "hacer una transferencia a la cuenta",
    "transfer_not_received_by_recipient": "el destinatario no recibió la transferencia",
    "transfer_timing": "plazos de una transferencia",
    "unable_to_verify_identity": "no se puede verificar la identidad",
    "verify_my_identity": "verificar la identidad",
    "verify_source_of_funds": "verificar el origen de los fondos",
    "verify_top_up": "verificar una recarga",
    "virtual_card_not_working": "la tarjeta virtual no funciona",
    "visa_or_mastercard": "elegir entre Visa o Mastercard",
    "why_verify_identity": "por qué hay que verificar la identidad",
    "wrong_amount_of_cash_received": "cantidad de efectivo recibida incorrecta",
    "wrong_exchange_rate_for_cash_withdrawal": "tipo de cambio incorrecto al retirar efectivo",
}


def convertir(raiz=None):
    raiz = raiz or raiz_hf(REPO)
    lic, com = licencia_fuente(raiz, LICENCIAS_OK, "cc-by-4.0")
    nombres = nombres_de_clase(raiz, "label")
    opciones = sorted(DESCRIPCIONES)
    items = []
    for origen in ("train", "test"):
        for r in leer_split(raiz, origen):
            et = etiqueta_de(r, nombres).lower()
            if et not in DESCRIPCIONES:
                raise KeyError("Banking77: intención sin descripción en español: " + et)
            split = "test" if origen == "test" else split_por_clave(r["text"], 0.1, 0.0, "banking77")
            items.append((split, dict(
                tarea="banca", tipo="choice", pregunta=PREGUNTA, texto=r["text"], opciones=opciones,
                descripciones=DESCRIPCIONES, etiqueta=et, idioma="en", fuente="%s %s" % (REPO, origen),
                licencia=lic, uso_comercial=com)))
    filas, desc = numerar(CORTO, items)
    return filas, {"descartadas_nc": desc, "licencia": lic}
