import Foundation

/// Lo que el SDK necesita del motor nativo (gomobile). Es un protocolo para poder probar la cascada con un motor
/// falso; `MotorNativo` es la implementación real.
public protocol Motor: AnyObject {
    /// Capas presentes en el fichero, p. ej. ["L0","L1","L2"].
    func capas() -> [String]
    func tieneCalib() -> Bool
    func tauEscalate() -> Double
    func decidirL0(_ texto: String, _ preguntaJson: String) -> String
    func decidirL1(_ texto: String, _ preguntaJson: String) -> String
    func torresL2(_ preguntaJson: String) -> Bool
    /// `ranuras`: K×d float32 little endian.
    func puntuarL2(_ preguntaJson: String, ranuras: Data, k: Int) -> String
    func extraerL2(a destino: String) throws
    func cerrar()

    /// El fichero trae CONJ (la cabeza conjunta, L2c).
    func tieneConj() -> Bool
    /// L2c: `simsJson` es la pregunta más `l0` (probabilidades de L0), `ranuras` (K×d aplanado) y `k`. Devuelve la
    /// misma forma que las demás capas; sin opinión si no hay cabeza para la pregunta.
    func cabezaConjunta(_ simsJson: String) -> String
    func cargarTokenizadorE5(ruta: String) throws
    /// Ids de e5 como int32 little endian (4 bytes por id), o nil si no se cargó el tokenizador.
    func tokenizarE5(_ texto: String) -> Data?
}

public extension Motor {
    func tieneConj() -> Bool { false }
    func cabezaConjunta(_ simsJson: String) -> String { #"{"ok":false,"error":"sin CONJ","probs":{}}"# }
    func cargarTokenizadorE5(ruta: String) throws { throw ErrorChispa("el motor no tiene tokenizador de e5") }
    func tokenizarE5(_ texto: String) -> Data? { nil }
}

/// Una capa de la cascada. Devuelve `.sinOpinion` si no tiene nada que decir; lanza si falla.
public protocol Capa {
    var nombre: String { get }
    func decidir(_ texto: String, _ pregunta: Pregunta) throws -> SalidaCapa
    /// Como `decidir`, con lo que dijeron las capas anteriores por nombre (L2c lee las probabilidades de L0).
    func decidir(_ texto: String, _ pregunta: Pregunta, previas: [String: SalidaCapa]) throws -> SalidaCapa
}

extension Capa {
    func decidir(_ texto: String, _ pregunta: Pregunta, previas: [String: SalidaCapa]) throws -> SalidaCapa {
        try decidir(texto, pregunta)
    }
}

struct CapaL0: Capa {
    let motor: Motor
    var nombre: String { "L0" }
    func decidir(_ texto: String, _ pregunta: Pregunta) throws -> SalidaCapa {
        try SalidaCapa.desdeJson(motor.decidirL0(texto, pregunta.json()))
    }
}

struct CapaL1: Capa {
    let motor: Motor
    var nombre: String { "L1" }
    func decidir(_ texto: String, _ pregunta: Pregunta) throws -> SalidaCapa {
        try SalidaCapa.desdeJson(motor.decidirL1(texto, pregunta.json()))
    }
}

/// Convierte un texto en los ids del tokenizador de e5 (con «query: » delante, tokens especiales y recorte a 128).
public protocol Tokenizador {
    func ids(_ texto: String) -> [Int64]
}

/// El tokenizador de e5 del propio motor (runtime/tok en Go): no hace falta que la app aporte uno.
struct TokenizadorMotor: Tokenizador {
    let motor: Motor
    func ids(_ texto: String) -> [Int64] {
        guard let d = motor.tokenizarE5(texto) else { return [] }
        return stride(from: 0, to: d.count - 3, by: 4).map { i in
            let v = UInt32(d[d.startIndex + i]) | UInt32(d[d.startIndex + i + 1]) << 8
                | UInt32(d[d.startIndex + i + 2]) << 16 | UInt32(d[d.startIndex + i + 3]) << 24
            return Int64(Int32(bitPattern: v))
        }
    }
}

/// El ONNX de L2: ids → S ∈ R^{K×d}, aplanado por filas.
public protocol SesionRanuras: AnyObject {
    func ranuras(_ ids: [Int64]) throws -> Ranuras
}

public struct Ranuras: Equatable {
    public let datos: [Float]
    public let k: Int

    public init(datos: [Float], k: Int) {
        precondition(k > 0 && datos.count % k == 0, "ranuras: \(datos.count) valores no caben en \(k) filas")
        self.datos = datos
        self.k = k
    }

    /// float32 little endian (iOS y macOS son little endian), que es lo que espera `puntuarL2`.
    public func aBytes() -> Data {
        datos.withUnsafeBufferPointer { Data(buffer: $0) }
    }
}

/// L2: ranuras del mensaje (ONNX Runtime) contra las torres de ESQUEMAS. Si el fichero no trae torres para la
/// pregunta no opina y no llega a tokenizar ni a llamar a ONNX. Si el fichero trae CONJ y L0 ya dio probabilidades,
/// es L2c: las similitudes salen de las mismas ranuras y la cabeza conjunta (en Go, la del servidor) decide; sin
/// cabeza para la pregunta, cae a L2 a secas.
struct CapaL2: Capa {
    let motor: Motor
    let sesion: SesionRanuras
    let tokenizador: Tokenizador
    var nombre: String { "L2" }

    func decidir(_ texto: String, _ pregunta: Pregunta) throws -> SalidaCapa {
        try decidir(texto, pregunta, previas: [:])
    }

    func decidir(_ texto: String, _ pregunta: Pregunta, previas: [String: SalidaCapa]) throws -> SalidaCapa {
        let pj = pregunta.json()
        guard motor.torresL2(pj) else { return .sinOpinion }
        let ids = tokenizador.ids(texto)
        guard !ids.isEmpty else { return .sinOpinion }
        let s = try sesion.ranuras(ids)
        if let l0 = previas["L0"]?.probs, !l0.isEmpty, motor.tieneConj() {
            let c = try SalidaCapa.desdeJson(motor.cabezaConjunta(try entradaConj(pj, l0, s)))
            if c.opina { return c }
        }
        return try SalidaCapa.desdeJson(motor.puntuarL2(pj, ranuras: s.aBytes(), k: s.k))
    }

    private func entradaConj(_ preguntaJson: String, _ l0: [String: Double], _ s: Ranuras) throws -> String {
        guard var o = (try JSONSerialization.jsonObject(with: Data(preguntaJson.utf8))) as? [String: Any] else {
            throw ErrorChispa("la pregunta no es un objeto JSON")
        }
        o["l0"] = l0
        o["ranuras"] = s.datos.map { Double($0) } // float → double es exacto; Go lo vuelve a float32
        o["k"] = s.k
        return String(decoding: try JSONSerialization.data(withJSONObject: o), as: UTF8.self)
    }
}
