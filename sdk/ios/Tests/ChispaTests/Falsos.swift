import Foundation
@testable import Chispa

/// JSON de una capa, con la forma de chispamovil.
func json(_ respuesta: String?, _ conf: Double = 0, _ probs: [String: Double] = [:]) -> String {
    guard let r = respuesta else { return #"{"ok":true,"opina":false,"answer":"","conf":0,"probs":{}}"# }
    let o: [String: Any] = ["ok": true, "opina": true, "answer": r, "conf": conf, "probs": probs]
    return String(decoding: try! JSONSerialization.data(withJSONObject: o), as: UTF8.self)
}

/// JSON de una capa `multi`: `answers` siempre (vacía si ninguna activa) y `answer` = la activa más probable o "".
func jsonMulti(_ activas: [String], _ conf: Double, _ probs: [String: Double]) -> String {
    let o: [String: Any] = ["ok": true, "opina": true, "answer": activas.first ?? "", "conf": conf, "probs": probs, "answers": activas]
    return String(decoding: try! JSONSerialization.data(withJSONObject: o), as: UTF8.self)
}

/// Un motor falso: cada capa devuelve lo que se le diga y se anotan las llamadas.
final class MotorFalso: Motor {
    var presentes = ["L0", "L1", "L2"]
    var calib = false
    var tau = 0.0
    var l0: () -> String = { json(nil) }
    var l1: () -> String = { json(nil) }
    var torres = true
    var l2: () -> String = { json(nil) }
    /// La marca `esquema_nuevo` que el motor real pone en las respuestas de L2 (ESQUEMAS no traía las torres): no depende de la
    /// caché de torres al vuelo (tras instalarlas, `torres` da true). `marcaForzada` no nulo la fija a mano.
    var marcaForzada: Bool?
    private var sinTorresAlInicio: Bool?
    private func marcar(_ js: String) -> String {
        guard var o = (try? JSONSerialization.jsonObject(with: Data(js.utf8))) as? [String: Any],
              (o["opina"] as? Bool) == true else { return js }
        o["esquema_nuevo"] = marcaForzada ?? sinTorresAlInicio ?? !torres
        return String(decoding: try! JSONSerialization.data(withJSONObject: o), as: UTF8.self)
    }
    var conj = false
    var cabeza: () -> String = { json(nil) }
    var idsE5: Data?
    var ultimoSimsJson: String?
    var llamadas: [String] = []
    var ultimasRanuras: Data?
    var ultimoK = -1
    var cerrado = false
    /// Zero-shot: mientras `torres` sea false el motor pide estos textos; al instalarlas, `torres` pasa a true (caché).
    var textosTorre: [String] = []
    var torresInstaladas: Data?
    var nInstaladas = 0
    /// false = `instalarTorresL2` rechaza las torres (y no las cachea).
    var aceptaTorres = true
    var tauConj = -1.0
    var tauL2: Double?
    /// `tau_l2_esquema_nuevo` de CALIB (−1 = falta).
    var tauNuevo = -1.0
    var hashes: [Int: String] = [:]
    /// Qué hace `extraerL2`: escribe en el destino que se le da (por defecto, nada).
    var alExtraer: (String) throws -> Void = { _ in }
    var extracciones = 0

    func capas() -> [String] { presentes }
    func tieneCalib() -> Bool { calib }
    func tauEscalate() -> Double { tau }
    func decidirL0(_ texto: String, _ preguntaJson: String) -> String { llamadas.append("L0"); return l0() }
    func decidirL1(_ texto: String, _ preguntaJson: String) -> String { llamadas.append("L1"); return l1() }
    func torresL2(_ preguntaJson: String) -> Bool { torres }
    func puntuarL2(_ preguntaJson: String, ranuras: Data, k: Int) -> String {
        llamadas.append("L2"); ultimasRanuras = ranuras; ultimoK = k; return marcar(l2())
    }
    func extraerL2(a destino: String) throws { extracciones += 1; try alExtraer(destino) }
    func tauEscalateL2() -> Double { tauL2 ?? tau }
    func tauL2c() -> Double { tauConj }
    func tauL2EsquemaNuevo() -> Double { tauNuevo }
    func hashSeccion(_ tipo: Int) -> String { hashes[tipo] ?? "" }
    func tieneConj() -> Bool { conj }
    func cabezaConjunta(_ simsJson: String) -> String { llamadas.append("CONJ"); ultimoSimsJson = simsJson; return marcar(cabeza()) }
    /// TORR: `onnxDeTorre` no nulo = el fichero la trae; `idsDePasaje` da los ids (int32 LE) de cada texto de torre.
    var onnxDeTorre: Data?
    var idsDePasaje: (String) -> Data? = { _ in nil }
    func tieneTorre() -> Bool { onnxDeTorre != nil }
    func onnxTorre() -> Data? { onnxDeTorre }
    func idsPasaje(_ texto: String) -> Data? { idsDePasaje(texto) }
    func tieneTokenizadorE5() -> Bool { idsE5 != nil }
    func tokenizarE5(_ texto: String) -> Data? { idsE5 }
    /// Texto largo con `trozos`: lo que devuelve `trozosE5` (`[n][len][ids…]…`); nil = el motor no trocea.
    var trozos: Data?
    var ultimosKs: String?
    func trozosE5(_ texto: String) -> Data? { trozos }
    func puntuarL2Trozos(_ preguntaJson: String, ranuras: Data, ksJson: String) -> String {
        llamadas.append("L2T"); ultimasRanuras = ranuras; ultimosKs = ksJson; return marcar(l2())
    }
    func textosTorreL2(_ preguntaJson: String) -> [String] { torres ? [] : textosTorre }
    func instalarTorresL2(_ preguntaJson: String, torres bytes: Data, n: Int) -> Bool {
        llamadas.append("TORRES")
        if !aceptaTorres { return false }
        if sinTorresAlInicio == nil { sinTorresAlInicio = !torres }
        torresInstaladas = bytes; nInstaladas = n; torres = true; return true
    }
    func cerrar() { cerrado = true }
}

final class SesionFalsa: SesionRanuras {
    var devuelve = Ranuras(datos: [1, 2, 3, 4, 5, 6], k: 2)
    var llamadas = 0
    var ultimosIds: [Int64]?
    func ranuras(_ ids: [Int64]) throws -> Ranuras {
        llamadas += 1
        ultimosIds = ids
        return devuelve
    }
}

struct TokenizadorFalso: Tokenizador {
    var devuelve: [Int64] = [1]
    var alTokenizar: () -> Void = {}
    func ids(_ texto: String) throws -> [Int64] { alTokenizar(); return devuelve }
}

let pregunta = Pregunta(
    "¿Qué quiere el cliente?",
    opciones: [Opcion("compra", descripcion: "quiere comprar"), Opcion("soporte", descripcion: "pide ayuda"), Opcion("saludo")]
)

/// Una pregunta con un esquema que ningún `.chispa` trae.
let preguntaNueva = Pregunta(
    "¿Qué tipo de incidencia es?",
    opciones: [Opcion("fraude", descripcion: "cargo no reconocido"), Opcion("tarjeta", descripcion: "tarjeta bloqueada o perdida")]
)

let preguntaMulti = Pregunta(
    "¿Qué temas toca el mensaje?",
    opciones: [Opcion("cobro", descripcion: "habla de un cobro"), Opcion("atencion", descripcion: "se queja de la atención"),
               Opcion("fraude", descripcion: "sospecha de fraude")],
    tipo: "multi"
)
