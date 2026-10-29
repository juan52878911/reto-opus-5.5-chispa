import XCTest
@testable import Chispa

/// R12-H7: con CONJ, el respaldo de L2c (L2 base) se corta con `tau_escalate_l2` y no con `tau_l2c`, el τ de la cabeza.
final class RespaldoL2cTests: XCTestCase {
    func motor(l0Probs: Bool) -> MotorFalso {
        let m = MotorFalso()
        m.presentes = l0Probs ? ["L0", "L2"] : ["L2"]
        m.calib = true
        m.tau = 0.5
        m.conj = true
        m.l0 = { json("compra", 0.5, ["compra": 0.5, "soporte": 0.5]) }
        m.l2 = { json("compra", 0.8, ["compra": 0.8]) }
        m.cabeza = { json("compra", 0.8, ["compra": 0.8]) }
        m.tauL2 = 0.95 // tau_escalate_l2
        m.tauConj = 0.3 // tau_l2c
        return m
    }

    func capa(_ m: MotorFalso) -> CapaL2 {
        CapaL2(motor: m, sesion: SesionFalsa(), tokenizador: TokenizadorFalso(devuelve: [0, 7, 2]))
    }

    func testLaCabezaConjuntaSigueUsandoTauL2c() throws {
        let m = motor(l0Probs: true)
        let r = try Cascada.armar(motor: m, l2: capa(m)).decidir("hola", pregunta)
        XCTAssertEqual(r.capa, "L2")
        XCTAssertFalse(r.escalar) // 0.8 ≥ 0.3
    }

    func testElRespaldoDeL2BaseUsaTauEscalateL2() throws {
        let m = motor(l0Probs: false) // sin probabilidades de L0: L2c cae a L2 base
        XCTAssertTrue(try Cascada.armar(motor: m, l2: capa(m)).decidir("hola", pregunta).escalar) // 0.8 < 0.95
        XCTAssertEqual(m.llamadas, ["L2"])
    }

    func testLaCapaMarcaElRespaldoSoloConConj() throws {
        let m = motor(l0Probs: false)
        XCTAssertTrue(try capa(m).decidir("hola", pregunta).respaldo)
        m.conj = false
        XCTAssertFalse(try capa(m).decidir("hola", pregunta).respaldo)
    }
}
