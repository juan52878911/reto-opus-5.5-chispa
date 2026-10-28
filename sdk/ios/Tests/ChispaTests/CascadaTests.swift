import XCTest
@testable import Chispa

final class CascadaTests: XCTestCase {
    private func cascada(_ m: MotorFalso, l2: Capa? = nil) throws -> Cascada { try Cascada.armar(motor: m, l2: l2) }

    func testL0SeguroNoLlamaAL1() throws {
        let m = MotorFalso()
        m.l0 = { json("compra", 0.95, ["compra": 0.95, "soporte": 0.05]) }
        let r = try cascada(m).decidir("quiero una camiseta", pregunta)
        XCTAssertEqual(r.respuesta, "compra")
        XCTAssertEqual(r.capa, "L0")
        XCTAssertFalse(r.escalar)
        XCTAssertEqual(m.llamadas, ["L0"])
        XCTAssertEqual(r.probs["soporte"] ?? -1, 0.05, accuracy: 1e-12)
    }

    func testL0DudosoPasaAL1() throws {
        let m = MotorFalso()
        m.l0 = { json("queja", 0.5, ["queja": 0.5]) }
        m.l1 = { json("soporte", 0.9, ["soporte": 0.9]) }
        let r = try cascada(m).decidir("hola", pregunta)
        XCTAssertEqual(r.capa, "L1")
        XCTAssertEqual(r.respuesta, "soporte")
        XCTAssertEqual(m.llamadas, ["L0", "L1"])
    }

    func testLaConfianzaIgualAlTauAcepta() throws {
        let m = MotorFalso()
        m.l0 = { json("compra", 0.80, ["compra": 0.80]) }
        XCTAssertEqual(try cascada(m).decidir("x", pregunta).capa, "L0")
    }

    func testUnaCapaQueFallaOSinOpinionSeSalta() throws {
        let m = MotorFalso()
        m.l0 = { "esto no es json" }
        m.l1 = { #"{"ok":false,"error":"sin L1"}"# }
        m.l2 = { json("saludo", 0.99, ["saludo": 0.99]) }
        let l2 = CapaL2(motor: m, sesion: SesionFalsa(), tokenizador: TokenizadorFalso(devuelve: [1, 2]))
        let r = try cascada(m, l2: l2).decidir("hola", pregunta)
        XCTAssertEqual(r.capa, "L2")
        XCTAssertEqual(r.respuesta, "saludo")
    }

    func testSiNingunaLlegaEscalaConLaMejorPista() throws {
        let m = MotorFalso()
        m.l0 = { json("queja", 0.30, ["queja": 0.30]) }
        m.l1 = { json("compra", 0.60, ["compra": 0.60]) }
        m.l2 = { json("soporte", 0.50, ["soporte": 0.50]) }
        let l2 = CapaL2(motor: m, sesion: SesionFalsa(), tokenizador: TokenizadorFalso())
        let r = try cascada(m, l2: l2).decidir("x", pregunta)
        XCTAssertTrue(r.escalar)
        XCTAssertEqual(r.respuesta, "compra") // la de mayor confianza vista
        XCTAssertEqual(r.confianza, 0.60, accuracy: 1e-12)
        XCTAssertEqual(r.capa, "L2") // la última de la cascada
    }

    func testSiNadieOpinaEscalaSinRespuesta() throws {
        let m = MotorFalso()
        m.presentes = ["L0", "L1"]
        let r = try cascada(m).decidir("x", pregunta)
        XCTAssertTrue(r.escalar)
        XCTAssertEqual(r.respuesta, "")
        XCTAssertEqual(r.confianza, 0)
        XCTAssertEqual(r.capa, "L1")
    }

    func testTauDeCalibParaL1YL2PeroNoL0() throws {
        // 0,5 de L1 no llega a 0,80 por defecto, pero con CALIB τ = 0,4 sí
        let sin = MotorFalso()
        sin.presentes = ["L0", "L1"]
        sin.l1 = { json("compra", 0.5, ["compra": 0.5]) }
        XCTAssertTrue(try cascada(sin).decidir("x", pregunta).escalar)

        let con = MotorFalso()
        con.presentes = ["L0", "L1"]
        con.calib = true
        con.tau = 0.4
        con.l1 = { json("compra", 0.5, ["compra": 0.5]) }
        let r = try cascada(con).decidir("x", pregunta)
        XCTAssertFalse(r.escalar)
        XCTAssertEqual(r.capa, "L1")

        // L0 sigue en 0,80 aunque CALIB diga 0,4
        let l0 = MotorFalso()
        l0.presentes = ["L0", "L1"]
        l0.calib = true
        l0.tau = 0.4
        l0.l0 = { json("queja", 0.5, ["queja": 0.5]) }
        _ = try cascada(l0).decidir("x", pregunta)
        XCTAssertEqual(l0.llamadas, ["L0", "L1"])
    }

    func testTauPorDefectoDeL2EsMasBajoQueElDeL1() throws {
        let m = MotorFalso()
        m.presentes = ["L1", "L2"]
        m.l1 = { json("a", 0.75, ["a": 0.75]) }
        m.l2 = { json("b", 0.75, ["b": 0.75]) }
        let l2 = CapaL2(motor: m, sesion: SesionFalsa(), tokenizador: TokenizadorFalso())
        let r = try cascada(m, l2: l2).decidir("x", pregunta)
        XCTAssertEqual(r.capa, "L2") // 0,75 < 0,80 de L1 pero ≥ 0,70 de L2
        XCTAssertEqual(r.respuesta, "b")
    }

    func testSinL2MontadoLaCascadaNoLaUsa() throws {
        let m = MotorFalso()
        m.l2 = { json("x", 1, ["x": 1]) }
        let r = try cascada(m, l2: nil).decidir("hola", pregunta)
        XCTAssertEqual(m.llamadas, ["L0", "L1"])
        XCTAssertTrue(r.escalar)
    }

    func testSinCapasUtilizablesFalla() {
        let m = MotorFalso()
        m.presentes = ["L2"]
        XCTAssertThrowsError(try Cascada.armar(motor: m, l2: nil))
    }

    func testMideElTiempoConElRelojInyectado() {
        var t: UInt64 = 0
        let reloj: () -> UInt64 = { defer { t += 2_500_000 }; return t }
        let m = MotorFalso()
        m.l0 = { json("compra", 0.9, ["compra": 0.9]) }
        let r = Cascada([CapaConTau(capa: CapaL0(motor: m), tau: 0.8)], reloj: reloj).decidir("x", pregunta)
        XCTAssertEqual(r.ms, 2.5, accuracy: 1e-9)
    }
}
