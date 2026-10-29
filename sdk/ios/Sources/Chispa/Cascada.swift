import Foundation

/// Una capa con su umbral: se acepta su respuesta si su confianza top-1 es ≥ `tau`.
struct CapaConTau {
    let capa: Capa
    let tau: Double
}

/// τ por defecto de cada capa (los de `ConfigPorDefecto` del servidor). Con CALIB, L1 y L2 usan `tau_escalate`.
enum TauPorDefecto {
    static let l0 = 0.80
    static let l1 = 0.80
    static let l2 = 0.70
}

/// La cascada de `server/decide/cascada.go`: pasa por las capas en orden mientras la confianza top-1 sea < τ (cada capa recibe lo que
/// dijeron las anteriores: L2c usa las probabilidades de L0). Si una
/// falla o no opina, sigue con la siguiente. Si ninguna alcanza su τ, escala: la respuesta es la de mayor confianza
/// vista (pista para quien reciba la escalada) y la capa es `capaEscalar`, como `CapaEscalar` del servidor.
final class Cascada {
    private let capas: [CapaConTau]
    private let reloj: () -> UInt64

    init(_ capas: [CapaConTau], reloj: @escaping () -> UInt64 = { DispatchTime.now().uptimeNanoseconds }) {
        precondition(!capas.isEmpty, "la cascada necesita al menos una capa")
        self.capas = capas
        self.reloj = reloj
    }

    /// La capa de una respuesta escalada (`CapaEscalar` en `server/decide/cascada.go`).
    static let capaEscalar = "escalar"

    func decidir(_ texto: String, _ pregunta: Pregunta) -> Respuesta {
        let t0 = reloj()
        func ms() -> Double { Double(reloj() &- t0) / 1e6 }
        var mejor = SalidaCapa.sinOpinion
        var previas: [String: SalidaCapa] = [:]
        for c in capas {
            let r = (try? c.capa.decidir(texto, pregunta, previas: previas)) ?? .sinOpinion
            previas[c.capa.nombre] = r
            if r.confianza > mejor.confianza { mejor = r }
            if r.opina && r.confianza >= c.tau {
                return Respuesta(respuesta: r.respuesta, confianza: r.confianza, probs: r.probs,
                                 capa: c.capa.nombre, escalar: false, ms: ms())
            }
        }
        return Respuesta(respuesta: mejor.respuesta, confianza: mejor.confianza, probs: mejor.probs,
                         capa: Cascada.capaEscalar, escalar: true, ms: ms())
    }

    /// Arma la cascada con las capas del motor (L0 y L1 si el fichero las trae) y L2 si además hay `l2`.
    /// Con CALIB, el τ de L1 y L2 es su `tau_escalate`.
    static func armar(motor: Motor, l2: Capa? = nil, tauL0: Double = TauPorDefecto.l0) throws -> Cascada {
        let presentes = motor.capas()
        let tauCalib: Double? = motor.tieneCalib() ? motor.tauEscalate() : nil
        var capas: [CapaConTau] = []
        if presentes.contains("L0") { capas.append(CapaConTau(capa: CapaL0(motor: motor), tau: tauL0)) }
        if presentes.contains("L1") { capas.append(CapaConTau(capa: CapaL1(motor: motor), tau: tauCalib ?? TauPorDefecto.l1)) }
        if presentes.contains("L2"), let l2 = l2 { capas.append(CapaConTau(capa: l2, tau: tauCalib ?? TauPorDefecto.l2)) }
        if capas.isEmpty { throw ErrorChispa("el fichero no trae ninguna capa utilizable (capas: \(presentes))") }
        return Cascada(capas)
    }
}
