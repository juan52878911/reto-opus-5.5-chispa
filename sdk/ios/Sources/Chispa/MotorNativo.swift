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

    /// `soporte`: (λ de L1, λ de L2c) del encogimiento few-shot (`ChispamovilAbrirConSoporte`); nil = `Abrir` del puente (λ de L1 según el fichero, L2 apagado).
    /// `textoLargo`: estrategia para textos que pasan del truncado (`ChispamovilAbrirConTextoLargo`; con `soporte` nil es `Abrir`: los λ se
    /// ignoran); nil = cabeza, sin llamar a ese constructor.
    static func abrir(ruta: String, soporte: (Double, Double)? = nil, textoLargo: TextoLargo? = nil) throws -> MotorNativo {
        var error: NSError?
        let abierto: ChispamovilChispa?
        if let tl = textoLargo {
            abierto = ChispamovilAbrirConTextoLargo(ruta, soporte?.0 ?? 0, soporte?.1 ?? 0, soporte != nil, tl.json(), &error)
        } else if let (l1, l2) = soporte {
            abierto = ChispamovilAbrirConSoporte(ruta, l1, l2, &error)
        } else {
            abierto = ChispamovilAbrir(ruta, &error)
        }
        guard let go = abierto else {
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
    func tauEscalateL2() -> Double { go.tauEscalateL2() }
    func tauL2c() -> Double { go.tauL2c() }
    func tauL2EsquemaNuevo() -> Double { go.tauL2EsquemaNuevo() }
    /// `true` = sin τ propio para esquemas nuevos (ni el de CALIB ni 0,846); llamar antes de construir la cascada.
    func sinTauL2EsquemaNuevo(_ apagar: Bool) { go.sinTauEsquemaNuevo(apagar) }
    func hashSeccion(_ tipo: Int) -> String { go.hashSeccion(tipo) }
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
    func textoTorre() -> String { go.textoTorre() }
    func instalarTorresL2(_ preguntaJson: String, torres: Data, n: Int) -> Bool {
        go.instalarTorresL2(preguntaJson, torres: torres, n: n)
    }
    func tieneTorre() -> Bool { go.tieneTorre() }
    func onnxTorre() -> Data? { go.onnxTorre() }
    func idsPasaje(_ texto: String) -> Data? { go.idsPasaje(texto) }
    func tieneTokenizadorE5() -> Bool { go.tieneTokenizadorE5() }
    func cargarTokenizadorE5(ruta: String) throws { try go.cargarTokenizadorE5(ruta) }
    func tokenizarE5(_ texto: String) -> Data? { go.tokenizarE5(texto) }
    func trozosE5(_ texto: String) -> Data? { go.trozosE5(texto) }
    func puntuarL2Trozos(_ preguntaJson: String, ranuras: Data, ksJson: String) -> String {
        go.puntuarL2Trozos(preguntaJson, ranuras: ranuras, ksJSON: ksJson)
    }
    /// Textos que pasaron del truncado de L1 o de la consulta de L2 desde que se abrió (`TextoLargoSuperados`).
    func textoLargoSuperados() -> Int { Int(go.textoLargoSuperados()) }
    func cerrar() { try? go.cerrar() }
}
