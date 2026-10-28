import Foundation
@testable import Chispa

/// JSON de una capa, con la forma de chispamovil.
func json(_ respuesta: String?, _ conf: Double = 0, _ probs: [String: Double] = [:]) -> String {
    guard let r = respuesta else { return #"{"ok":true,"opina":false,"answer":"","conf":0,"probs":{}}"# }
    let o: [String: Any] = ["ok": true, "opina": true, "answer": r, "conf": conf, "probs": probs]
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
    var llamadas: [String] = []
    var ultimasRanuras: Data?
    var ultimoK = -1
    var cerrado = false

    func capas() -> [String] { presentes }
    func tieneCalib() -> Bool { calib }
    func tauEscalate() -> Double { tau }
    func decidirL0(_ texto: String, _ preguntaJson: String) -> String { llamadas.append("L0"); return l0() }
    func decidirL1(_ texto: String, _ preguntaJson: String) -> String { llamadas.append("L1"); return l1() }
    func torresL2(_ preguntaJson: String) -> Bool { torres }
    func puntuarL2(_ preguntaJson: String, ranuras: Data, k: Int) -> String {
        llamadas.append("L2"); ultimasRanuras = ranuras; ultimoK = k; return l2()
    }
    func extraerL2(a destino: String) throws {}
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
    func ids(_ texto: String) -> [Int64] { alTokenizar(); return devuelve }
}

let pregunta = Pregunta(
    "¿Qué quiere el cliente?",
    opciones: [Opcion("compra", descripcion: "quiere comprar"), Opcion("soporte", descripcion: "pide ayuda"), Opcion("saludo")]
)
