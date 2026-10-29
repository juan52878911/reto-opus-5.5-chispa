import Foundation
import os

/// Una capa con su umbral: se acepta su respuesta si su confianza top-1 es ≥ `tau`.
struct CapaConTau {
    let capa: Capa
    let tau: Double
    /// τ de la capa cuando su salida trae `esquemaNuevo`; nil = el mismo `tau`.
    var tauEsquemaNuevo: Double? = nil
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
    /// Recibe el nombre de la capa y el error cuando una capa lanza (por defecto, `os_log`).
    private let alErrorCapa: (String, Error) -> Void

    init(_ capas: [CapaConTau], reloj: @escaping () -> UInt64 = { DispatchTime.now().uptimeNanoseconds },
         alErrorCapa: @escaping (String, Error) -> Void = Cascada.registrarErrorCapa) {
        precondition(!capas.isEmpty, "la cascada necesita al menos una capa")
        self.capas = capas
        self.reloj = reloj
        self.alErrorCapa = alErrorCapa
    }

    private static let registro = OSLog(subsystem: "com.chispa.sdk", category: "cascada")

    /// Registro por defecto de un error de capa.
    static func registrarErrorCapa(_ capa: String, _ error: Error) {
        os_log("la capa %{public}@ falló: %{public}@", log: registro, type: .error, capa, String(describing: error))
    }

    /// La capa de una respuesta escalada (`CapaEscalar` en `server/decide/cascada.go`).
    static let capaEscalar = "escalar"

    func decidir(_ texto: String, _ pregunta: Pregunta) -> Respuesta {
        let t0 = reloj()
        func ms() -> Double { Double(reloj() &- t0) / 1e6 }
        var mejor = SalidaCapa.sinOpinion
        var previas: [String: SalidaCapa] = [:]
        for c in capas {
            let r: SalidaCapa
            do {
                r = try c.capa.decidir(texto, pregunta, previas: previas)
            } catch {
                alErrorCapa(c.capa.nombre, error)
                r = .sinOpinion
            }
            previas[c.capa.nombre] = r
            if r.confianza > mejor.confianza { mejor = r }
            let tau = (r.esquemaNuevo ? c.tauEsquemaNuevo : nil) ?? c.tau
            if r.opina && r.confianza >= tau {
                return Respuesta(respuesta: r.respuesta, confianza: r.confianza, probs: r.probs,
                                 capa: c.capa.nombre, escalar: false, ms: ms())
            }
        }
        return Respuesta(respuesta: mejor.respuesta, confianza: mejor.confianza, probs: mejor.probs,
                         capa: Cascada.capaEscalar, escalar: true, ms: ms())
    }

    /// Arma la cascada con las capas del motor (L0 y L1 si el fichero las trae) y L2 si además hay `l2`.
    /// Con CALIB, el τ de L1 y L2 es su `tau_escalate`; con CONJ (L2c) el de L2 es `tau_l2c` si el fichero lo trae
    /// (`aplicarTauL2c` del servidor). Con `tau_l2_esquema_nuevo`, L2 lo usa en lugar de ese τ cuando sus torres salieron al vuelo.
    static func armar(motor: Motor, l2: Capa? = nil, tauL0: Double = TauPorDefecto.l0,
                      alErrorCapa: @escaping (String, Error) -> Void = Cascada.registrarErrorCapa) throws -> Cascada {
        let presentes = motor.capas()
        let tauCalib: Double? = motor.tieneCalib() ? motor.tauEscalate() : nil
        var capas: [CapaConTau] = []
        if presentes.contains("L0") { capas.append(CapaConTau(capa: CapaL0(motor: motor), tau: tauL0)) }
        if presentes.contains("L1") { capas.append(CapaConTau(capa: CapaL1(motor: motor), tau: tauCalib ?? TauPorDefecto.l1)) }
        let tauL2c: Double? = motor.tieneConj() && motor.tauL2c() >= 0 ? motor.tauL2c() : nil
        if presentes.contains("L2"), let l2 = l2 {
            let tauNuevo: Double? = motor.tieneCalib() && motor.tauL2EsquemaNuevo() >= 0 ? motor.tauL2EsquemaNuevo() : nil
            capas.append(CapaConTau(capa: l2, tau: tauL2c ?? tauCalib ?? TauPorDefecto.l2, tauEsquemaNuevo: tauNuevo))
        }
        if capas.isEmpty { throw ErrorChispa("el fichero no trae ninguna capa utilizable (capas: \(presentes))") }
        return Cascada(capas, alErrorCapa: alErrorCapa)
    }
}
