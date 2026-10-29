import XCTest
@testable import Chispa

/// τ propio de L2 para esquemas con torres al vuelo (`tau_l2_esquema_nuevo`) y λ del soporte few-shot.
final class TauEsquemaNuevoTests: XCTestCase {
    final class Codificador: CodificadorTorre {
        func torre(_ texto: String) throws -> [Float] { [1, 2] }
    }

    func motor(torres: Bool, tauNuevo: Double, tau: Double = 0.9) -> MotorFalso {
        let m = MotorFalso()
        m.presentes = ["L2"]
        m.calib = true
        m.tau = tau
        m.torres = torres
        m.tauNuevo = tauNuevo
        m.textosTorre = ["passage: a", "passage: b"]
        m.l2 = { json("fraude", 0.7, ["fraude": 0.7]) }
        return m
    }

    func capa(_ m: MotorFalso) -> CapaL2 {
        CapaL2(motor: m, sesion: SesionFalsa(), tokenizador: TokenizadorFalso(devuelve: [1, 2]), codificador: Codificador())
    }

    func decidir(_ m: MotorFalso) throws -> Respuesta {
        try Cascada.armar(motor: m, l2: capa(m)).decidir("x", pregunta)
    }

    func testEsquemaConocidoUsaElTauDeSiempre() throws {
        XCTAssertTrue(try decidir(motor(torres: true, tauNuevo: 0.5)).escalar) // 0.7 < 0.9
    }

    func testEsquemaNuevoUsaElTauNuevo() throws {
        let r = try decidir(motor(torres: false, tauNuevo: 0.5))
        XCTAssertEqual(r.capa, "L2")
        XCTAssertFalse(r.escalar) // 0.7 ≥ 0.5
    }

    func testSiElTauNuevoEsMasAltoEsquemaNuevoEscala() throws {
        XCTAssertTrue(try decidir(motor(torres: false, tauNuevo: 0.95, tau: 0.6)).escalar)
    }

    func testSinTauNuevoNadaCambia() throws {
        XCTAssertTrue(try decidir(motor(torres: false, tauNuevo: -1)).escalar)
        XCTAssertFalse(try decidir(motor(torres: false, tauNuevo: -1, tau: 0.6)).escalar)
    }

    func testLasTorresCacheadasDeUnEsquemaNuevoSiguenSiendoNuevas() throws {
        let m = motor(torres: false, tauNuevo: 0.5)
        let c = try Cascada.armar(motor: m, l2: capa(m))
        XCTAssertFalse(c.decidir("x", pregunta).escalar)
        XCTAssertFalse(c.decidir("x", pregunta).escalar) // torresL2 ya da true, pero se instalaron al vuelo
        XCTAssertEqual(m.llamadas.filter { $0 == "TORRES" }.count, 1)
    }

    func testLaCapaMarcaEsquemaNuevoSoloConTorresAlVuelo() throws {
        XCTAssertTrue(try capa(motor(torres: false, tauNuevo: -1)).decidir("x", pregunta).esquemaNuevo)
        XCTAssertFalse(try capa(motor(torres: true, tauNuevo: -1)).decidir("x", pregunta).esquemaNuevo)
    }

    func testLambdaDelSoporteLlegaAlMotor() throws {
        let apagado = try XCTUnwrap(try Chispa.soporteDe(nil, nil))
        XCTAssertEqual(apagado.0, Chispa.lambdaApagado)
        XCTAssertEqual(apagado.1, Chispa.lambdaApagado)
        XCTAssertEqual(Chispa.lambdaSoporteL1PorDefecto, 4.0)
        XCTAssertEqual(try Chispa.soporteDe(3, 5)?.0, 3)
        XCTAssertEqual(try Chispa.soporteDe(3, 5)?.1, 5)
        XCTAssertEqual(try Chispa.soporteDe(3, nil)?.1, Chispa.lambdaApagado)
        XCTAssertEqual(try Chispa.soporteDe(nil, 0)?.0, Chispa.lambdaApagado)
        // +∞ ya no apaga: es «solo descripción» y llega tal cual al motor.
        XCTAssertEqual(try Chispa.soporteDe(Double.infinity, 0)?.0, Double.infinity)
    }

    /// Por defecto (centinela) = `Abrir` del puente (nil): λ de L1 lo decide el motor según el fichero; nil = apagado y número = explícito, ambos por `AbrirConSoporte`.
    func testLambdaPorDefectoLoDecideElMotor() throws {
        XCTAssertTrue(Chispa.soportePorDefecto.isNaN)
        XCTAssertNil(try Chispa.soporteDe(Chispa.soportePorDefecto, nil))
        XCTAssertEqual(try Chispa.soporteDe(nil, nil)?.0, Chispa.lambdaApagado)
        XCTAssertEqual(try Chispa.soporteDe(4, nil)?.0, 4)
        // Con L2 explícito el puente no ofrece «L1 por defecto»: L1 va con 4 explícito.
        XCTAssertEqual(try Chispa.soporteDe(Chispa.soportePorDefecto, 3)?.0, 4)
        XCTAssertEqual(try Chispa.soporteDe(Chispa.soportePorDefecto, 3)?.1, 3)
        XCTAssertEqual(try Chispa.soporteDe(nil, 3)?.0, Chispa.lambdaApagado)
    }

    /// R4 #15: un λ negativo o NaN es error al abrir (antes se apagaba el soporte sin avisar); nil sigue siendo apagado.
    func testLambdaNegativoONaNEsError() {
        XCTAssertThrowsError(try Chispa.soporteDe(-5, nil))
        XCTAssertThrowsError(try Chispa.soporteDe(nil, -0.5))
        XCTAssertThrowsError(try Chispa.soporteDe(2, Double.nan))
        XCTAssertThrowsError(try Chispa.soporteDe(Chispa.soportePorDefecto, Double.nan))
        XCTAssertThrowsError(try Chispa.soporteDe(-Double.infinity, 0))
        XCTAssertEqual(try Chispa.soporteDe(nil, nil)?.0, Chispa.lambdaApagado)
    }
}
