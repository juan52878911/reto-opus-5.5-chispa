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
}

/// Una capa de la cascada. Devuelve `.sinOpinion` si no tiene nada que decir; lanza si falla.
public protocol Capa {
    var nombre: String { get }
    func decidir(_ texto: String, _ pregunta: Pregunta) throws -> SalidaCapa
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
/// pregunta no opina y no llega a tokenizar ni a llamar a ONNX.
struct CapaL2: Capa {
    let motor: Motor
    let sesion: SesionRanuras
    let tokenizador: Tokenizador
    var nombre: String { "L2" }

    func decidir(_ texto: String, _ pregunta: Pregunta) throws -> SalidaCapa {
        let pj = pregunta.json()
        guard motor.torresL2(pj) else { return .sinOpinion }
        let ids = tokenizador.ids(texto)
        guard !ids.isEmpty else { return .sinOpinion }
        let s = try sesion.ranuras(ids)
        return try SalidaCapa.desdeJson(motor.puntuarL2(pj, ranuras: s.aBytes(), k: s.k))
    }
}
