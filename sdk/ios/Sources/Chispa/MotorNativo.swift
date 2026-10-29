import Foundation
import Chispamovil

/// El motor real: el xcframework de `gomobile bind -target=ios` sobre sdk/movil/chispamovil.
///
/// Los nombres de `Chispamovil*` son los que genera gomobile para el paquete `chispamovil` (prefijo «Chispamovil»,
/// métodos en lowerCamel, `error` → `throws`/`NSError`). Es el único fichero que los toca: si gomobile los
/// generase distintos, se corrige aquí.
final class MotorNativo: Motor {
    private let go: ChispamovilChispa

    private init(_ go: ChispamovilChispa) { self.go = go }

    static func abrir(ruta: String) throws -> MotorNativo {
        var error: NSError?
        guard let go = ChispamovilAbrir(ruta, &error) else {
            throw ErrorChispa("no se pudo abrir \(ruta): \(error?.localizedDescription ?? "error desconocido")")
        }
        return MotorNativo(go)
    }

    func capas() -> [String] {
        guard let d = go.capas().data(using: .utf8),
              let a = (try? JSONSerialization.jsonObject(with: d)) as? [String] else { return [] }
        return a
    }

    func tieneCalib() -> Bool { go.tieneCalib() }
    func tauEscalate() -> Double { go.tauEscalate() }
    func decidirL0(_ texto: String, _ preguntaJson: String) -> String { go.decidirL0(texto, preguntaJSON: preguntaJson) }
    func decidirL1(_ texto: String, _ preguntaJson: String) -> String { go.decidir(texto, preguntaJSON: preguntaJson) }
    func torresL2(_ preguntaJson: String) -> Bool { go.torresL2(preguntaJson) }
    func puntuarL2(_ preguntaJson: String, ranuras: Data, k: Int) -> String {
        go.puntuarL2(preguntaJson, ranuras: ranuras, k: k)
    }
    func extraerL2(a destino: String) throws { try go.extraerL2(destino) }
    func tieneConj() -> Bool { go.tieneConj() }
    func cabezaConjunta(_ simsJson: String) -> String { go.cabezaConjunta(simsJson) }
    func textosTorreL2(_ preguntaJson: String) -> [String] {
        guard let d = go.textosTorreL2(preguntaJson).data(using: .utf8),
              let a = (try? JSONSerialization.jsonObject(with: d)) as? [String] else { return [] }
        return a
    }
    func instalarTorresL2(_ preguntaJson: String, torres: Data, n: Int) -> Bool {
        go.instalarTorresL2(preguntaJson, torres: torres, n: n)
    }
    func tieneTorre() -> Bool { go.tieneTorre() }
    func onnxTorre() -> Data? { go.onnxTorre() }
    func idsPasaje(_ texto: String) -> Data? { go.idsPasaje(texto) }
    func tieneTokenizadorE5() -> Bool { go.tieneTokenizadorE5() }
    func cargarTokenizadorE5(ruta: String) throws { try go.cargarTokenizadorE5(ruta) }
    func tokenizarE5(_ texto: String) -> Data? { go.tokenizarE5(texto) }
    func cerrar() { try? go.cerrar() }
}
