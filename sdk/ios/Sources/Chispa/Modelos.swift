import Foundation

/// Una opción de respuesta; `descripcion` ayuda a L1 (entra en el texto de la torre).
public struct Opcion: Equatable {
    public let id: String
    public let descripcion: String?
    public init(_ id: String, descripcion: String? = nil) {
        self.id = id
        self.descripcion = descripcion
    }
}

/// Una pregunta, con la misma forma que la del servidor: `question`, `kind` (`choice`, `score`, `noul` o `multi`) y `options`.
public struct Pregunta: Equatable {
    public let texto: String
    public let opciones: [Opcion]
    public let tipo: String
    public init(_ texto: String, opciones: [Opcion], tipo: String = "choice") {
        self.texto = texto
        self.opciones = opciones
        self.tipo = tipo
    }

    public func json() -> String {
        let ops: [[String: String]] = opciones.map { o in
            var d = ["id": o.id]
            if let desc = o.descripcion, !desc.isEmpty { d["description"] = desc }
            return d
        }
        let obj: [String: Any] = ["question": texto, "kind": tipo, "options": ops]
        let datos = try! JSONSerialization.data(withJSONObject: obj, options: [.sortedKeys])
        return String(decoding: datos, as: UTF8.self)
    }
}

public struct ErrorChispa: Error, Equatable, CustomStringConvertible {
    public let mensaje: String
    public init(_ mensaje: String) { self.mensaje = mensaje }
    public var description: String { mensaje }
}

/// Lo que dice una capa. `confianza` 0 significa «sin opinión».
public struct SalidaCapa: Equatable {
    public let respuesta: String
    public let confianza: Double
    public let probs: [String: Double]
    /// L2 puntuó con torres al vuelo (la pregunta no estaba en ESQUEMAS; lo marca el motor, `esquema_nuevo`): la cascada usa `tauL2EsquemaNuevo`.
    public let esquemaNuevo: Bool
    /// Solo en `multi` (el motor manda `answers`): las opciones activas en el orden de la pregunta, vacía si ninguna; nil en los
    /// demás tipos. En `multi`, `respuesta` es la activa más probable o "" y `confianza` es la de la opción más dudosa.
    public let respuestas: [String]?

    public init(respuesta: String, confianza: Double, probs: [String: Double], esquemaNuevo: Bool = false,
                respuestas: [String]? = nil) {
        self.respuesta = respuesta
        self.confianza = confianza
        self.probs = probs
        self.esquemaNuevo = esquemaNuevo
        self.respuestas = respuestas
    }

    public static let sinOpinion = SalidaCapa(respuesta: "", confianza: 0, probs: [:])

    /// En `multi`, «ninguna activa» (respuesta vacía, `respuestas` vacía) es una opinión válida si hay confianza.
    public var opina: Bool { confianza > 0 && (!respuesta.isEmpty || respuestas != nil) }

    /// Lee el JSON de chispamovil (`{"ok":…,"opina":…,"answer":…,"conf":…,"probs":{…}}`).
    public static func desdeJson(_ js: String) throws -> SalidaCapa {
        guard let datos = js.data(using: .utf8),
              let o = (try? JSONSerialization.jsonObject(with: datos)) as? [String: Any]
        else { throw ErrorChispa("respuesta de la capa ilegible") }
        guard (o["ok"] as? Bool) == true else {
            throw ErrorChispa((o["error"] as? String) ?? "error sin mensaje")
        }
        guard (o["opina"] as? Bool) == true else { return .sinOpinion }
        var probs: [String: Double] = [:]
        for (k, v) in (o["probs"] as? [String: Any]) ?? [:] {
            if let d = (v as? NSNumber)?.doubleValue { probs[k] = d }
        }
        return SalidaCapa(
            respuesta: (o["answer"] as? String) ?? "",
            confianza: (o["conf"] as? NSNumber)?.doubleValue ?? 0,
            probs: probs,
            esquemaNuevo: (o["esquema_nuevo"] as? Bool) ?? false,
            respuestas: (o["answers"] as? [Any])?.compactMap { $0 as? String }
        )
    }
}

/// La decisión final de una pregunta. `escalar` es true si ninguna capa llegó a su τ (`respuesta` es la pista).
/// `respuestas` solo se llena en `multi` (las activas; vacía si ninguna): `respuesta` es la más probable de ellas o "".
public struct Respuesta: Equatable {
    public let respuesta: String
    public let confianza: Double
    public let probs: [String: Double]
    public let capa: String
    public let escalar: Bool
    public let ms: Double
    public var respuestas: [String] = []
}
